"""Transactional PBDB ingestion; normal full-Florida writes require a verified checkpoint."""

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine
from app.ingestion.metrics import peak_memory_bytes
from app.ingestion.pbdb import (
    ADAPTER_VERSION,
    DATASET,
    POLICY_VERSION,
    PROVIDER,
    SERVICE,
    Snapshot,
    digest,
    identifier,
    is_florida_context,
    normalize_collection,
    normalize_material,
    normalize_measurement,
    normalize_opinion,
    normalize_reference,
    normalize_taxon_name,
    optional_identifier,
    stable_id,
)
from app.models import (
    CollectionEvent,
    CollectionReferenceEvidence,
    IdentificationEvidence,
    IngestionRun,
    Locality,
    MaterialEvidence,
    NormalizedSourceRevision,
    Occurrence,
    OpinionReferenceEvidence,
    ProviderAgeEvidence,
    ResearchReference,
    Source,
    SourceDataset,
    SourceNormalizationCurrent,
    SourceRecord,
    SourceRecordDependency,
    SourceRecordRevision,
    Taxon,
    event_evidence,
    locality_evidence,
    occurrence_evidence,
    taxon_evidence,
)

DATASET_UUID = stable_id("dataset", DATASET)
SOURCE_UUID = stable_id("source", PROVIDER)


def upsert(
    session: Session, table: Table, rows: Iterable[dict[str, Any]], *, immutable: bool = False
) -> int:
    keys = [column.name for column in table.primary_key]
    batches = 0
    iterator = iter(rows)
    while True:
        from itertools import islice

        unique = {tuple(row[key] for key in keys): row for row in islice(iterator, 500)}
        values = list(unique.values())
        if not values:
            break
        statement = insert(table).values(values)
        if immutable:
            statement = statement.on_conflict_do_nothing(index_elements=keys)
        else:
            statement = statement.on_conflict_do_update(
                index_elements=keys,
                set_={
                    key: getattr(statement.excluded, key)
                    for key in values[0]
                    if key not in {*keys, "created_at", "first_seen_at"}
                },
            )
        session.execute(statement)
        batches += 1
    return batches


def json_value(value: Any) -> Any:
    """Exact decimals remain strings in retained normalized evidence, not rounded floats."""
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def record_id(kind: str, external_id: str) -> UUID:
    return stable_id("record", f"{kind}:{external_id}")


def validate_disposable_target(
    name: str, host: str | None, port: int | None, user: str | None, *, ci: bool = False
) -> None:
    allowed = {
        ("paleograph_test", 55432),
        ("paleograph_pbdb_canary", 58432),
        ("paleograph_browser", 56432),
    }
    if ci:
        allowed.add(("paleograph_test", 5432))
    if host not in {"localhost", "127.0.0.1"} or (name, port) not in allowed or user != name:
        raise ValueError(
            "Phase 4B PBDB writes require the dedicated disposable test/canary database"
        )


def disposable_guard(session: Session) -> None:
    url = session.get_bind().engine.url
    name = str(session.scalar(text("SELECT current_database()")))
    if name != url.database:
        raise ValueError("Connected database differs from the disposable target")
    validate_disposable_target(
        name, url.host, url.port, url.username, ci=os.environ.get("GITHUB_ACTIONS") == "true"
    )


def validate_normal_checkpoint(
    name: str,
    host: str | None,
    port: int | None,
    user: str | None,
    checkpoint: Path,
    *,
    full_scope: bool,
) -> None:
    if not full_scope:
        raise ValueError("Normal PBDB import requires complete full Florida scope")
    if (
        name != "paleograph"
        or host not in {"localhost", "127.0.0.1"}
        or port != 5432
        or user != name
    ):
        raise ValueError("Unsupported normal target for Phase 4C checkpoint")
    evidence = json.loads(checkpoint.read_bytes())
    baseline = evidence.get("baseline", {})
    restored = evidence.get("restore", {})
    if (
        evidence.get("status") != "verified"
        or evidence.get("label") != "pre-4c"
        or baseline.get("database_name") != name
        or baseline.get("migration") != "0009_time_policy_cover"
        or restored.get("migration") != baseline.get("migration")
        or any(
            baseline.get(key) != 462280 or restored.get(key) != 462280
            for key in ("occurrences", "specimens", "current_records", "revisions", "catalog")
        )
    ):
        raise ValueError("Missing restore-verified pre-4C checkpoint")
    dump = Path(evidence["path"])
    with dump.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != evidence.get("sha256"):
            raise ValueError("Changed Phase 4C checkpoint bytes")


def plan(
    snapshot: Snapshot,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], set[tuple[str, str]]]]:
    """Validate bounded populations; retain explicit unresolved taxonomy identifiers."""
    occurrences = snapshot.occurrences()
    records: dict[tuple[str, str], dict[str, Any]] = {}
    dependencies: dict[tuple[str, str], set[tuple[str, str]]] = {}

    def add(kind: str, external: str, raw: dict[str, Any], normalized: Any = None) -> None:
        key = (kind, external)
        if key in records and records[key]["raw"] != raw:
            raise ValueError(f"Conflicting repeated PBDB {kind} record {external}")
        records[key] = {
            "raw": raw,
            "normalized": json_value(normalized if normalized is not None else raw),
            "hash": digest(raw),
        }
        dependencies.setdefault(key, set())

    fields = {
        "collections": ("collection", "collection_no", "col"),
        "materials": ("material", "specimen_no", "spm"),
        "measurements": ("measurement", "measurement_no", "mea"),
        "intervals": ("interval", "interval_no", "int"),
        "timescales": ("timescale", "scale_no", "tsc"),
        "references": ("reference", "reference_no", "ref"),
    }
    opinion_views: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in snapshot.records("opinions"):
        views = opinion_views[identifier(raw.get("opinion_no"), "opn")]
        if raw not in views:
            views.append(raw)
    for external, views in opinion_views.items():
        raw = views[0]
        if len(views) > 1:
            # Exact concept exports contextualize a single provider opinion. Preserve all
            # views; do not treat contextual labels as a second identity or a later revision.
            contextual = {"orig_no", "taxon_name", "child_name", "opinion_type"}
            common = {key: value for key, value in raw.items() if key not in contextual}
            if any(
                {key: value for key, value in view.items() if key not in contextual} != common
                for view in views
            ):
                raise ValueError(f"Conflicting substantive PBDB opinion record {external}")
            raw = {**common, "export_views": sorted(views, key=digest)}
        add("opinion", external, raw, asdict(normalize_opinion(raw)))
    for response_kind, (kind, field, prefix) in fields.items():
        for raw in snapshot.records(response_kind):
            normalizers: dict[str, Callable[[dict[str, Any]], Any]] = {
                "collection": normalize_collection,
                "material": normalize_material,
                "measurement": normalize_measurement,
                "opinion": normalize_opinion,
                "reference": normalize_reference,
            }
            normalized = asdict(normalizers[kind](raw)) if kind in normalizers else raw
            add(kind, identifier(raw.get(field), prefix), raw, normalized)
    for raw in snapshot.records("taxa"):
        identifier(raw.get("taxon_no"), "txn")
        add("taxon", str(raw["taxon_no"]), raw, asdict(normalize_taxon_name(raw)))
    material_membership: dict[str, list[str]] = defaultdict(list)
    for raw in snapshot.records("materials"):
        occ = optional_identifier(raw.get("occurrence_no"), "occ")
        if occ:
            material_membership[occ].append(identifier(raw["specimen_no"], "spm"))
    for occurrence in occurrences:
        add(
            "occurrence",
            occurrence.id,
            occurrence.latest.raw,
            {
                "occurrence_id": occurrence.id,
                "collection_id": occurrence.collection_id,
                "history_complete": occurrence.complete_history,
                "original_identification": occurrence.original.raw,
                "latest_identification": occurrence.latest.raw,
                "identification_history": [ident.raw for ident in occurrence.identifications],
                "material_membership": sorted(material_membership[occurrence.id]),
            },
        )
        dependencies[("occurrence", occurrence.id)].add(("collection", occurrence.collection_id))
        for ident in occurrence.identifications:
            ident_id = f"{occurrence.id}:{ident.id}"
            # Latest/original role is versioned on occurrence normalization.
            add("identification", ident_id, ident.raw)
            dependencies[("occurrence", occurrence.id)].add(("identification", ident_id))

    wanted_collections = (
        set(snapshot.manifest["scope"]["collection_ids"])
        if snapshot.manifest["scope"]["mode"] == "full-florida"
        else {occ.collection_id for occ in occurrences}
    )
    if {key[1] for key in records if key[0] == "collection"} != wanted_collections:
        raise ValueError("Incomplete collection dependencies")
    interval_names: dict[str, set[tuple[str, str]]] = defaultdict(set)
    taxa: dict[str, set[tuple[str, str]]] = defaultdict(set)
    opinions: dict[str, set[tuple[str, str]]] = defaultdict(set)
    measurements: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for key, value in records.items():
        raw = value["raw"]
        if key[0] == "interval":
            interval_names[raw["interval_name"]].add(key)
        if key[0] in {"taxon", "opinion"}:
            index = taxa if key[0] == "taxon" else opinions
            id_fields = (
                ("orig_no", "taxon_no") if key[0] == "taxon" else ("orig_no", "child_spelling_no")
            )
            for view in raw.get("export_views", [raw]):
                for field in id_fields:
                    if number := optional_identifier(view.get(field), "txn"):
                        index[number].add(key)
        if key[0] == "measurement":
            measurements[identifier(raw.get("specimen_no"), "spm")].add(key)
    for kind, external in list(records):
        raw = records[(kind, external)]["raw"]
        links = dependencies[(kind, external)]
        if kind != "reference" and (ref := optional_identifier(raw.get("reference_no"), "ref")):
            links.add(("reference", ref))
        if kind == "collection":
            if not is_florida_context(raw):
                raise ValueError("Non-Florida collection in bounded snapshot")
            names = {raw.get("early_interval"), raw.get("late_interval")} - {None, ""}
            for name in names:
                links.update(interval_names[name])
            if names - {
                records[key]["raw"]["interval_name"] for key in links if key[0] == "interval"
            }:
                raise ValueError("Missing provider interval dependency")
        if kind == "interval" and raw.get("scale_no"):
            links.add(("timescale", identifier(raw["scale_no"], "tsc")))
        if kind in {"identification", "material"}:
            taxon_ids = {
                identifier(raw[field], "txn")
                for field in ("identified_no", "accepted_no")
                if optional_identifier(raw.get(field), "txn")
            }
            for taxon in taxon_ids:
                links.update(taxa[taxon])
            # Name variants can resolve to the provider's original concept; retain the exact
            # requested namespace and returned name independently, without matching by name.
            for taxon in taxon_ids:
                links.update(opinions[taxon])
        if kind == "material":
            occ = optional_identifier(raw.get("occurrence_no"), "occ")
            if occ is None or ("occurrence", occ) not in records:
                raise ValueError("Material outside bounded occurrence population")
            dependencies[("occurrence", occ)].add((kind, external))
            dependencies[(kind, external)].update(measurements[external])
        if kind == "measurement":
            if ("material", identifier(raw.get("specimen_no"), "spm")) not in records:
                raise ValueError("Measurement missing explicit material dependency")
        missing = {key for key in links if key not in records}
        if missing:
            raise ValueError(f"Missing typed PBDB dependencies: {sorted(missing)}")
    # Flatten the transitive frame so a changed context/reference/taxonomic dependency
    # suppresses its old projection even when the occurrence's own bytes are unchanged.
    for key in dependencies:
        seen: set[tuple[str, str]] = set()
        pending = list(dependencies[key])
        while pending:
            dependency = pending.pop()
            if dependency in seen or dependency == key:
                continue
            seen.add(dependency)
            pending.extend(dependencies[dependency] - seen)
        dependencies[key] = seen
    return records, dependencies


def persist(session: Session, snapshot: Snapshot, run_id: UUID, now: datetime) -> dict[str, Any]:
    started = time.perf_counter()
    records, dependencies = plan(snapshot)
    normalization_seconds = time.perf_counter() - started
    full = snapshot.manifest["scope"]["mode"] == "full-florida"
    if full:
        print(
            json.dumps(
                {
                    "stage": "normalized",
                    "records": len(records),
                    "seconds": normalization_seconds,
                    "dependencies": sum(len(frame) for frame in dependencies.values()),
                    "peak_memory_bytes": peak_memory_bytes(),
                }
            ),
            flush=True,
        )
    persistence_started = time.perf_counter()
    previous: dict[UUID, str | None] = {
        source_id: content_hash
        for source_id, content_hash in session.execute(
            select(SourceRecord.id, SourceRecord.content_hash).where(
                SourceRecord.source_dataset_id == DATASET_UUID
            )
        ).all()
    }
    rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "source",
            "revision",
            "normalized",
            "current",
            "dependency",
            "reference",
            "locality",
            "event",
            "taxon",
            "occurrence",
            "identification",
            "material",
            "provider_age",
            "collection_reference",
            "opinion_reference",
            "taxon_link",
            "locality_link",
            "event_link",
            "occurrence_link",
        )
    }
    inserted = updated = 0
    identity = {"created_at": now, "updated_at": now}
    occurrences = snapshot.occurrences()
    for key, value in records.items():
        kind, external = key
        source_id = record_id(kind, external)
        raw, content_hash = value["raw"], value["hash"]
        inserted += source_id not in previous
        updated += source_id in previous and previous[source_id] != content_hash
        frame = sorted((str(record_id(*dep)), records[dep]["hash"]) for dep in dependencies[key])
        normalized_payload = {
            "record_type": kind,
            "external_id": external,
            "evidence": value["normalized"],
            "dependencies": frame,
        }
        normalization_hash = digest({"adapter": ADAPTER_VERSION, "payload": normalized_payload})
        rows["source"].append(
            {
                "id": source_id,
                "source_dataset_id": DATASET_UUID,
                "ingestion_run_id": run_id,
                "source_record_id": external,
                "record_type": kind,
                "source_url": SERVICE,
                "basis_of_record": f"PBDB {kind} assertion",
                "license": "CC0 1.0",
                "raw_payload": raw,
                "content_hash": content_hash,
                "source_modified_at": None,
                "first_seen_at": now,
                "last_seen_at": now,
                "ingested_at": now,
                "is_current": True,
                **identity,
            }
        )
        rows["revision"].append(
            {
                "source_record_id": source_id,
                "content_hash": content_hash,
                "raw_payload": raw,
                "observed_at": now,
                "ingestion_run_id": run_id,
            }
        )
        rows["normalized"].append(
            {
                "source_record_id": source_id,
                "content_hash": content_hash,
                "normalization_hash": normalization_hash,
                "adapter_version": ADAPTER_VERSION,
                "payload": normalized_payload,
                "ingestion_run_id": run_id,
            }
        )
        rows["current"].append(
            {
                "source_record_id": source_id,
                "content_hash": content_hash,
                "normalization_hash": normalization_hash,
            }
        )
        ref = optional_identifier(raw.get("reference_no"), "ref")
        ref_id = stable_id("reference", ref) if ref else None
        if kind == "reference":
            rows["reference"].append(
                {
                    "id": stable_id("reference", external),
                    "source_record_id": source_id,
                    "source_dataset_id": DATASET_UUID,
                    "title": raw.get("reftitle"),
                    "doi": raw.get("doi"),
                    "published_year": str(raw["pubyr"]) if raw.get("pubyr") else None,
                    "bibliography": raw,
                    **identity,
                }
            )
        if kind == "collection":
            context = normalize_collection(raw)
            locality_id, event_id = stable_id("locality", external), stable_id("event", external)
            rows["locality"].append(
                {
                    "id": locality_id,
                    "name": context.name,
                    "description": json.dumps(
                        {
                            "country": raw.get("cc"),
                            "stateProvince": raw.get("state"),
                            "county": raw.get("county"),
                        }
                    ),
                    "geom": None,
                    "original_latitude": str(raw["lat"]) if raw.get("lat") is not None else None,
                    "original_longitude": str(raw["lng"]) if raw.get("lng") is not None else None,
                    "geodetic_datum": None,
                    "coordinate_precision": None,
                    "coordinate_uncertainty_m": None,
                    "location_is_generalized": raw.get("latlng_basis") == "based on political unit",
                    "location_is_withheld": False,
                    **identity,
                }
            )
            rows["event"].append(
                {
                    "id": event_id,
                    "locality_id": locality_id,
                    "name": context.name,
                    "context": raw.get("geogcomments"),
                    "stratigraphy": raw.get("stratcomments"),
                    "older_ma": None,
                    "younger_ma": None,
                    **identity,
                }
            )
            rows["provider_age"].append(
                {
                    "source_record_id": source_id,
                    "content_hash": content_hash,
                    "policy_version": POLICY_VERSION,
                    "older_ma": context.older_ma,
                    "younger_ma": context.younger_ma,
                    "evidence": value["normalized"],
                }
            )
            rows["locality_link"].append(
                {"locality_id": locality_id, "source_record_id": source_id}
            )
            rows["event_link"].append(
                {"collection_event_id": event_id, "source_record_id": source_id}
            )
            if ref_id:
                rows["collection_reference"].append(
                    {
                        "source_record_id": source_id,
                        "content_hash": content_hash,
                        "collection_event_id": event_id,
                        "reference_id": ref_id,
                    }
                )
        if kind == "opinion" and ref_id:
            rows["opinion_reference"].append(
                {
                    "source_record_id": source_id,
                    "content_hash": content_hash,
                    "reference_id": ref_id,
                }
            )
        if kind == "material":
            rows["material"].append(
                {
                    "source_record_id": source_id,
                    "content_hash": content_hash,
                    "occurrence_id": stable_id(
                        "occurrence", identifier(raw["occurrence_no"], "occ")
                    ),
                    "reference_id": ref_id,
                    "catalog_label": raw.get("specimen_id"),
                    "evidence": raw,
                }
            )
    for occurrence in occurrences:
        occ_id = stable_id("occurrence", occurrence.id)
        for ident in occurrence.identifications:
            external = f"{occurrence.id}:{ident.id}"
            # Explicit source occurrence/identification key scopes taxon identity.
            taxon_id = stable_id("identification-taxon", external)
            rows["taxon"].append(
                {
                    "id": taxon_id,
                    "scientific_name": ident.name,
                    "rank": ident.raw.get("identified_rank"),
                    "source_dataset_id": DATASET_UUID,
                    "parent_taxon_id": None,
                    **identity,
                }
            )
            source_id = record_id("identification", external)
            rows["identification"].append(
                {
                    "source_record_id": source_id,
                    "content_hash": digest(ident.raw),
                    "occurrence_id": occ_id,
                    "taxon_id": taxon_id,
                    "provider_identification_id": ident.id,
                    "evidence": ident.raw,
                    "reference_id": stable_id("reference", ident.reference_id)
                    if ident.reference_id
                    else None,
                }
            )
            rows["taxon_link"].append({"taxon_id": taxon_id, "source_record_id": source_id})
        rows["occurrence"].append(
            {
                "id": occ_id,
                "taxon_id": stable_id(
                    "identification-taxon", f"{occurrence.id}:{occurrence.latest.id}"
                ),
                "collection_event_id": stable_id("event", occurrence.collection_id),
                "specimen_id": None,
                "notes": occurrence.latest.raw.get("comments"),
                **identity,
            }
        )
        rows["occurrence_link"].append(
            {"occurrence_id": occ_id, "source_record_id": record_id("occurrence", occurrence.id)}
        )
    tables = [
        ("source", SourceRecord),
        ("revision", SourceRecordRevision),
        ("reference", ResearchReference),
        ("locality", Locality),
        ("event", CollectionEvent),
        ("taxon", Taxon),
        ("occurrence", Occurrence),
        ("normalized", NormalizedSourceRevision),
        ("dependency", SourceRecordDependency),
        ("provider_age", ProviderAgeEvidence),
        ("identification", IdentificationEvidence),
        ("material", MaterialEvidence),
        ("collection_reference", CollectionReferenceEvidence),
        ("opinion_reference", OpinionReferenceEvidence),
        ("current", SourceNormalizationCurrent),
    ]
    immutable = {
        "revision",
        "normalized",
        "dependency",
        "provider_age",
        "identification",
        "material",
        "collection_reference",
        "opinion_reference",
    }

    def dependency_rows() -> Iterable[dict[str, Any]]:
        for normalized in rows["normalized"]:
            for dep, dep_hash in normalized["payload"]["dependencies"]:
                yield {
                    "source_record_id": normalized["source_record_id"],
                    "content_hash": normalized["content_hash"],
                    "normalization_hash": normalized["normalization_hash"],
                    "dependency_record_id": UUID(dep),
                    "dependency_content_hash": dep_hash,
                }

    batches = {}
    storage = []
    for name, model in tables:
        batch_started = time.perf_counter()
        batches[name] = upsert(
            session,
            cast(Table, model.__table__),
            dependency_rows() if name == "dependency" else rows[name],
            immutable=name in immutable,
        )
        if full:
            print(
                json.dumps(
                    {
                        "stage": "persisted",
                        "table": name,
                        "batches": batches[name],
                        "seconds": time.perf_counter() - batch_started,
                        "peak_memory_bytes": peak_memory_bytes(),
                    }
                ),
                flush=True,
            )
        if name in {"revision", "current"}:
            storage.append(
                {
                    "stage": "raw-source" if name == "revision" else "normalized-canonical",
                    "database_bytes": session.scalar(
                        text("SELECT pg_database_size(current_database())")
                    ),
                }
            )
    for name, table in [
        ("taxon_link", taxon_evidence),
        ("locality_link", locality_evidence),
        ("event_link", event_evidence),
        ("occurrence_link", occurrence_evidence),
    ]:
        batches[name] = upsert(session, table, rows[name], immutable=True)
    persistence_seconds = time.perf_counter() - persistence_started
    from app.discovery.pbdb import rebuild

    publication_started = time.perf_counter()
    projection = rebuild(session)
    publication_seconds = time.perf_counter() - publication_started
    storage.append(
        {
            "stage": "discovery",
            "database_bytes": session.scalar(text("SELECT pg_database_size(current_database())")),
        }
    )
    if full:
        print(
            json.dumps({"stage": "discovery-built", **projection, "seconds": publication_seconds}),
            flush=True,
        )
    return {
        "inserted": inserted,
        "updated": updated,
        "occurrences": len(occurrences),
        "source_records": len(records),
        "by_type": {
            kind: sum(key[0] == kind for key in records)
            for kind in sorted({key[0] for key in records})
        },
        "projection": projection,
        "normalization_seconds": round(normalization_seconds, 3),
        "persistence_seconds": round(persistence_seconds, 3),
        "publication_seconds": round(publication_seconds, 3),
        "database_batches": batches,
        "storage_stages": storage,
        "peak_memory_bytes": peak_memory_bytes(),
    }


def ingest_snapshot(
    session: Session, snapshot: Snapshot, *, normal_checkpoint: Path | None = None
) -> dict[str, Any]:
    snapshot = Snapshot.load(snapshot.path)
    if normal_checkpoint is None:
        disposable_guard(session)
    else:
        url = session.get_bind().engine.url
        name = str(session.scalar(text("SELECT current_database()")))
        if name != url.database:
            raise ValueError("Connected database differs from the checkpoint target")
        validate_normal_checkpoint(
            name,
            url.host,
            url.port,
            url.username,
            normal_checkpoint,
            full_scope=snapshot.manifest["scope"]["mode"] == "full-florida",
        )
    started = time.perf_counter()
    now, run_id = datetime.now(UTC), uuid4()
    session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
    upsert(
        session,
        cast(Table, Source.__table__),
        [
            {
                "id": SOURCE_UUID,
                "name": PROVIDER,
                "homepage_url": "https://paleobiodb.org/",
                "api_url": SERVICE,
            }
        ],
    )
    # Do not publish the incoming version before the complete transaction succeeds.
    session.execute(
        insert(SourceDataset)
        .values(
            id=DATASET_UUID,
            source_id=SOURCE_UUID,
            external_dataset_id=DATASET,
            title="PBDB public Florida",
            publisher=PROVIDER,
            dataset_url=SERVICE,
            license="CC0 1.0",
            retrieved_at=now,
            is_synthetic=False,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    session.add(
        IngestionRun(
            id=run_id,
            source_dataset_id=DATASET_UUID,
            started_at=now,
            status="running",
            source_version=snapshot.hash,
            importer_version=ADAPTER_VERSION,
            snapshot={
                "manifest": snapshot.manifest,
                "path": str(snapshot.path),
                "sha256": snapshot.hash,
            },
            scope="full-florida; complete_scope=true; no-deactivation"
            if snapshot.manifest["scope"]["mode"] == "full-florida"
            else "bounded-canary; complete_scope=false",
        )
    )
    session.flush()
    try:
        with session.begin_nested():
            # Dataset updates invalidate browse. Stage the version before the final
            # rebuild, inside the same rollback boundary, so commit leaves it ready.
            session.execute(
                update(SourceDataset)
                .where(SourceDataset.id == DATASET_UUID)
                .values(version=snapshot.hash, retrieved_at=now, title="PBDB public Florida")
            )
            result = persist(session, snapshot, run_id, now)
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="completed",
                completed_at=datetime.now(UTC),
                records_read=result["source_records"],
                records_inserted=result["inserted"],
                records_updated=result["updated"],
                records_accepted=result["source_records"],
            )
        )
        session.commit()
        return {
            "status": "completed",
            "run_id": str(run_id),
            "snapshot": snapshot.hash,
            **result,
            "seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as error:
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="failed",
                completed_at=datetime.now(UTC),
                records_failed=1,
                error_summary=f"{type(error).__name__}: {str(error)[:1000]}",
            )
        )
        session.commit()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--normal-checkpoint", type=Path)
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session:
            print(
                json.dumps(
                    ingest_snapshot(
                        session,
                        Snapshot.load(args.snapshot),
                        normal_checkpoint=args.normal_checkpoint,
                    )
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
