"""Batch persistence for the UFVP normalized boundary, with auditable lifecycle rules."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, Settings
from app.db import create_db_engine
from app.ingestion.ufvp import (
    DATASET_ID,
    IMPORTER_VERSION,
    IPT,
    RESOURCE_URL,
    Archive,
    NormalizedRecord,
    content_hash,
    fetch_archive,
    normalize,
    stable_id,
    text_value,
)
from app.models import (
    Collection,
    CollectionEvent,
    IngestionRun,
    Institution,
    Locality,
    Occurrence,
    Source,
    SourceDataset,
    SourceRecord,
    SourceRecordRevision,
    Specimen,
    Taxon,
    event_evidence,
    locality_evidence,
    occurrence_evidence,
    specimen_evidence,
    taxon_evidence,
)

SOURCE_ID = stable_id("source", "museum")
CANONICAL_DATASET_ID = stable_id("dataset", DATASET_ID)
INSTITUTION_ID = stable_id("institution", "UF")


def upsert(
    session: Session, table: Table, rows: list[dict[str, Any]], *, immutable: bool = False
) -> None:
    if not rows:
        return
    keys = [column.name for column in table.primary_key]
    unique = {tuple(row[key] for key in keys): row for row in rows}
    statement = insert(table).values(list(unique.values()))
    if immutable:
        statement = statement.on_conflict_do_nothing(index_elements=keys)
    else:
        statement = statement.on_conflict_do_update(
            index_elements=keys,
            set_={
                key: getattr(statement.excluded, key)
                for key in rows[0]
                if key not in {*keys, "created_at", "first_seen_at"}
            },
        )
    session.execute(statement)


def persist_batch(
    session: Session, records: list[NormalizedRecord], run_id: UUID, now: datetime
) -> tuple[int, int]:
    previous: dict[UUID, str | None] = {
        identifier: digest
        for identifier, digest in session.execute(
            select(SourceRecord.id, SourceRecord.content_hash).where(
                SourceRecord.id.in_([stable_id("record", record.source_id) for record in records])
            )
        ).all()
    }
    rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "collection",
            "taxon",
            "locality",
            "event",
            "specimen",
            "occurrence",
            "record",
            "revision",
            "taxon_link",
            "locality_link",
            "event_link",
            "specimen_link",
            "occurrence_link",
        )
    }
    inserted = updated = 0
    for record in records:
        raw = record.raw
        record_id = stable_id("record", record.source_id)
        if record_id not in previous:
            inserted += 1
        elif previous[record_id] != record.hash:
            updated += 1
        # A complete source classification + qualifier scopes the navigation concept.
        # A shared name alone is never a matching rule; no cross-source merging occurs.
        taxonomy = {
            key: raw.get(key, "")
            for key in (
                "scientificName",
                "kingdom",
                "phylum",
                "class",
                "order",
                "family",
                "genus",
                "subgenus",
                "specificEpithet",
                "infraspecificEpithet",
                "identificationQualifier",
            )
        }
        taxon_id = stable_id("taxon", content_hash(taxonomy))
        geographic = {
            key: raw.get(key, "")
            for key in (
                "locationID",
                "continent",
                "country",
                "stateProvince",
                "county",
                "locality",
                "decimalLatitude",
                "decimalLongitude",
                "geodeticDatum",
                "coordinateUncertaintyInMeters",
                "verbatimCoordinates",
                "coordinatePrecision",
                "informationWithheld",
                "dataGeneralizations",
            )
        }
        locality_id = stable_id("locality", content_hash(geographic))
        event_id = stable_id("event", record.source_id)
        occurrence_id = stable_id("occurrence", record.source_id)
        specimen_id = stable_id("specimen", record.source_id)
        collection_code = text_value(raw, "collectionCode")
        collection_id = stable_id("collection", collection_code) if collection_code else None
        identity = {"created_at": now, "updated_at": now}
        if collection_id:
            rows["collection"].append(
                {
                    "id": collection_id,
                    "institution_id": INSTITUTION_ID,
                    "code": collection_code,
                    "name": None,
                    **identity,
                }
            )
        qualifier = text_value(raw, "identificationQualifier")
        rows["taxon"].append(
            {
                "id": taxon_id,
                "scientific_name": f"{record.name} ({qualifier})" if qualifier else record.name,
                "rank": None,
                **identity,
            }
        )
        rows["locality"].append(
            {
                "id": locality_id,
                "name": text_value(raw, "locality")
                or text_value(raw, "locationID")
                or "Locality not supplied",
                "description": json.dumps(geographic, ensure_ascii=False),
                "geom": f"SRID=4326;POINT({record.longitude} {record.latitude})"
                if record.latitude is not None
                else None,
                "original_latitude": raw.get("decimalLatitude"),
                "original_longitude": raw.get("decimalLongitude"),
                "geodetic_datum": text_value(raw, "geodeticDatum"),
                "coordinate_uncertainty_m": record.uncertainty,
                "coordinate_precision": record.precision,
                "location_is_generalized": record.generalized,
                "location_is_withheld": record.withheld,
                "information_withheld": text_value(raw, "informationWithheld"),
                **identity,
            }
        )
        rows["event"].append(
            {
                "id": event_id,
                "locality_id": locality_id,
                "name": text_value(raw, "locationID") or "Source collection context",
                "context": json.dumps(
                    {key: raw.get(key, "") for key in ("eventDate", "recordedBy", "fieldNumber")},
                    ensure_ascii=False,
                ),
                "stratigraphy": json.dumps(record.geology, ensure_ascii=False)
                if record.geology
                else None,
                "older_ma": None,
                "younger_ma": None,
                "early_interval_name": text_value(raw, "earliestEpochOrLowestSeries")
                or text_value(raw, "earliestPeriodOrLowestSystem"),
                "late_interval_name": text_value(raw, "latestEpochOrHighestSeries"),
                **identity,
            }
        )
        rows["specimen"].append(
            {
                "id": specimen_id,
                "collection_id": collection_id,
                "institution_code": text_value(raw, "institutionCode"),
                "collection_code": collection_code,
                "catalog_number": text_value(raw, "catalogNumber"),
                "occurrence_identifier": raw.get("occurrenceID") or None,
                "material_entity_identifier": raw.get("materialEntityID") or None,
                "other_identifiers": {
                    key: raw.get(key, "") for key in ("id", "otherCatalogNumbers", "fieldNumber")
                },
                "preparations": text_value(raw, "preparations"),
                "individual_count": text_value(raw, "individualCount"),
                **identity,
            }
        )
        rows["occurrence"].append(
            {
                "id": occurrence_id,
                "taxon_id": taxon_id,
                "collection_event_id": event_id,
                "specimen_id": specimen_id,
                "notes": record.coordinate_status,
                **identity,
            }
        )
        rows["record"].append(
            {
                "id": record_id,
                "source_dataset_id": CANONICAL_DATASET_ID,
                "ingestion_run_id": run_id,
                "source_record_id": record.source_id,
                "record_type": "occurrence",
                "source_url": text_value(raw, "references"),
                "basis_of_record": text_value(raw, "basisOfRecord"),
                "license": text_value(raw, "license"),
                "rights_holder": text_value(raw, "rightsHolder"),
                "access_rights": text_value(raw, "accessRights"),
                "information_withheld": text_value(raw, "informationWithheld"),
                "data_generalizations": text_value(raw, "dataGeneralizations"),
                "raw_payload": raw,
                "source_modified_at": record.modified_at,
                "ingested_at": now,
                "content_hash": record.hash,
                "first_seen_at": now,
                "last_seen_at": now,
                "is_current": True,
                **identity,
            }
        )
        rows["revision"].append(
            {
                "source_record_id": record_id,
                "content_hash": record.hash,
                "ingestion_run_id": run_id,
                "raw_payload": raw,
                "observed_at": now,
            }
        )
        for kind, key, value in (
            ("taxon", "taxon_id", taxon_id),
            ("locality", "locality_id", locality_id),
            ("event", "collection_event_id", event_id),
            ("specimen", "specimen_id", specimen_id),
            ("occurrence", "occurrence_id", occurrence_id),
        ):
            rows[f"{kind}_link"].append({key: value, "source_record_id": record_id})
    for model, key in (
        (Collection, "collection"),
        (Taxon, "taxon"),
        (Locality, "locality"),
        (CollectionEvent, "event"),
        (Specimen, "specimen"),
        (Occurrence, "occurrence"),
        (SourceRecord, "record"),
    ):
        upsert(session, cast(Table, model.__table__), rows[key])
    upsert(session, cast(Table, SourceRecordRevision.__table__), rows["revision"], immutable=True)
    for table, key in (
        (taxon_evidence, "taxon"),
        (locality_evidence, "locality"),
        (event_evidence, "event"),
        (specimen_evidence, "specimen"),
        (occurrence_evidence, "occurrence"),
    ):
        # These links describe the current interpretation. Prior values survive in
        # immutable revisions and snapshots, not as misleading current evidence.
        session.execute(delete(table).where(table.c.source_record_id.in_(list(previous))))
        upsert(session, table, rows[f"{key}_link"], immutable=True)
    return inserted, updated


def ingest(
    session: Session,
    archive: Archive,
    *,
    limit: int | None = 1000,
    commit_batches: bool = False,
    raw_dir: Path | None = None,
) -> IngestionRun:
    if limit is not None and limit < 1:
        raise ValueError("Sample limit must be positive")
    retained = archive.retain(raw_dir or REPO_ROOT / "data/raw")
    now = datetime.now(UTC)
    metadata = archive.metadata
    # Session-level lock also covers batch commits. Never overlap two UFVP imports.
    session.execute(text("SELECT pg_advisory_lock(74003001)"))
    run = IngestionRun(
        id=uuid4(),
        source_dataset_id=CANONICAL_DATASET_ID,
        started_at=now,
        status="running",
        source_version=metadata.version,
        importer_version=IMPORTER_VERSION,
        scope="florida-complete" if limit is None else f"florida-sample:{limit}",
        snapshot={
            **metadata.snapshot(),
            "sha256": archive.digest,
            "raw_path": str(retained),
            "retrieved_at": datetime.fromtimestamp(retained.stat().st_mtime, UTC).isoformat(),
            "archive_url": f"{IPT}/archive.do?r=ufvp&v={metadata.version}",
        },
        records_read=0,
        records_accepted=0,
        records_inserted=0,
        records_updated=0,
        records_skipped=0,
        records_failed=0,
    )
    errors: list[str] = []
    try:
        upsert(
            session,
            cast(Table, Source.__table__),
            [
                {
                    "id": SOURCE_ID,
                    "name": "Florida Museum of Natural History",
                    "homepage_url": "https://www.floridamuseum.ufl.edu/",
                    "api_url": IPT,
                }
            ],
        )
        upsert(
            session,
            cast(Table, SourceDataset.__table__),
            [
                {
                    "id": CANONICAL_DATASET_ID,
                    "source_id": SOURCE_ID,
                    "external_dataset_id": DATASET_ID,
                    "title": metadata.title,
                    "publisher": metadata.publisher,
                    "dataset_url": RESOURCE_URL,
                    "citation": metadata.citation,
                    "doi": None,
                    "license": metadata.license,
                    "rights_holder": metadata.rights_holder,
                    "version": metadata.version,
                    "published_at": metadata.published_at,
                    "retrieved_at": now,
                    "is_synthetic": False,
                }
            ],
        )
        upsert(
            session,
            cast(Table, Institution.__table__),
            [
                {
                    "id": INSTITUTION_ID,
                    "name": metadata.publisher,
                    "code": "UF",
                    "website": "https://www.floridamuseum.ufl.edu/",
                }
            ],
        )
        session.add(run)
        session.flush()
        batch: list[NormalizedRecord] = []
        seen: set[str] = set()

        def flush() -> None:
            if not batch:
                return
            with session.begin_nested():
                inserted, updated = persist_batch(session, batch, run.id, now)
            run.records_inserted += inserted
            run.records_updated += updated
            run.records_accepted += len(batch)
            batch.clear()
            session.flush()
            if commit_batches:
                session.commit()

        for raw in archive.rows():
            run.records_read += 1
            if raw.get("stateProvince", "").strip().casefold() != "florida" or raw.get(
                "country", ""
            ).strip().casefold() not in {"usa", "united states", "united states of america"}:
                run.records_skipped += 1
                continue
            if limit is not None and run.records_accepted + len(batch) >= limit:
                run.records_skipped += 1
                continue
            try:
                record = normalize(raw)
                if record.source_id in seen:
                    raise ValueError("Repeated core identifier in snapshot")
                seen.add(record.source_id)
                batch.append(record)
            except ValueError as error:
                run.records_failed += 1
                if len(errors) < 20:
                    errors.append(f"{raw.get('id', 'unidentified')}: {error}")
            if len(batch) >= 200:
                flush()
        flush()
        run.status = "partial" if run.records_failed else "completed"
        if limit is None and run.status == "completed":
            session.execute(
                update(SourceRecord)
                .where(
                    SourceRecord.source_dataset_id == CANONICAL_DATASET_ID,
                    SourceRecord.ingestion_run_id != run.id,
                )
                .values(is_current=False, updated_at=now)
            )
    except Exception as error:
        # Savepoint rollback leaves completed batches intact; no unseen record deactivation.
        run.status = "failed"
        run.records_failed += 1
        errors.append(f"Import stopped: {type(error).__name__}: {error}")
    finally:
        run.completed_at = datetime.now(UTC)
        run.error_summary = "\n".join(errors) or None
        session.flush()
        if commit_batches:
            session.commit()
        session.execute(text("SELECT pg_advisory_unlock(74003001)"))
    return run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Noncommercial UFVP Florida import; preserves CC BY-NC attribution"
    )
    parser.add_argument(
        "--archive", type=Path, help="Use an existing official snapshot without networking"
    )
    parser.add_argument("--version", help="Pin an official IPT version for download")
    parser.add_argument(
        "--limit", type=int, default=1000, help="Maximum accepted Florida sample records"
    )
    parser.add_argument(
        "--full-florida",
        action="store_true",
        help="Complete Florida scope; may mark unseen records inactive only after success",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    path = args.archive or fetch_archive(REPO_ROOT / "data/raw", args.version)
    archive = Archive(path)
    engine = create_db_engine(Settings())
    with engine.connect() as connection, Session(connection, expire_on_commit=False) as session:
        run = ingest(
            session, archive, limit=None if args.full_florida else args.limit, commit_batches=True
        )
        print(
            json.dumps(
                {
                    "run_id": str(run.id),
                    "status": run.status,
                    "version": run.source_version,
                    "scope": run.scope,
                    "read": run.records_read,
                    "accepted": run.records_accepted,
                    "inserted": run.records_inserted,
                    "updated": run.records_updated,
                    "skipped": run.records_skipped,
                    "failed": run.records_failed,
                    "errors": run.error_summary,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            )
        )
        session.commit()
    engine.dispose()
    if run.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
