"""Versioned additional material evidence; source assertions are never rewritten."""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.pbdb import digest
from app.models import ReconciliationAssessment, ReconciliationEdge, ReconciliationGeneration

POLICY = "material-id-v1"
INSTITUTIONS = {"UF", "USNM", "MCZ", "FGS", "FMNH", "AMNH", "BIOPSI"}
COLLECTIONS = {"VP", "UF/FGS", "UF/PB", "UF/TRO"}


@dataclass(frozen=True, order=True)
class MaterialKey:
    institution: str
    collection: str
    catalog: str


@dataclass(frozen=True)
class Identifier:
    key: MaterialKey | None
    institution: str | None
    collection: str | None
    catalog: str | None
    state: str
    reason: str
    original: dict[str, str | None]


@dataclass(frozen=True)
class Target:
    specimen_id: UUID
    source_record_id: UUID
    content_hash: str
    institution: str
    collection: str
    catalog: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    targets: tuple[Target, ...]


def match_identifier(identifier: Identifier, targets: Sequence[Target]) -> Decision:
    if identifier.state not in {"complete", "partial"}:
        return Decision(
            "ambiguous" if identifier.state == "ambiguous" else "unresolved", identifier.reason, ()
        )
    exact = tuple(
        target
        for target in targets
        if identifier.key == MaterialKey(target.institution, target.collection, target.catalog)
    )
    if len({target.specimen_id for target in exact}) == 1:
        return Decision("deterministic", "unique-explicit-triplet", exact)
    if exact:
        return Decision("ambiguous", "multiple-materials", exact)
    partial = tuple(
        target
        for target in targets
        if identifier.institution
        and identifier.catalog
        and not identifier.collection
        and target.institution == identifier.institution
        and target.catalog == identifier.catalog
    )
    if partial:
        return Decision(
            "candidate" if len({target.specimen_id for target in partial}) == 1 else "ambiguous",
            "collection-not-supplied",
            partial,
        )
    return Decision(
        "unresolved", "unmatched" if identifier.catalog else "insufficient-evidence", ()
    )


def normalize_identifier(
    *,
    label: str | None = None,
    institution: str | None = None,
    collection: str | None = None,
    catalog: str | None = None,
) -> Identifier:
    original = dict(label=label, institution=institution, collection=collection, catalog=catalog)
    if label and not any((institution, collection, catalog)):
        match = re.fullmatch(r"\s*([A-Za-z]+)\s*[:| ]\s*([A-Za-z/]+)\s*[:| ]\s*(.+?)\s*", label)
        if (
            match
            and match.group(1).upper() in INSTITUTIONS
            and match.group(2).upper() in COLLECTIONS
        ):
            institution, collection, catalog = match.groups()
        else:
            partial = re.fullmatch(r"\s*(UF|USNM|MCZ|FGS|FMNH|BIOPSI)\s+(.+?)\s*", label, re.I)
            if partial:
                institution, catalog = partial.groups()
    institution = institution.strip() if institution else None
    collection = collection.strip() if collection else None
    institution = (
        institution.upper() if institution and institution.upper() in INSTITUTIONS else institution
    )
    collection = (
        collection.upper() if collection and collection.upper() in COLLECTIONS else collection
    )
    catalog = catalog.strip() if catalog else None
    if label and any(original[name] for name in ("institution", "collection", "catalog")):
        parsed = normalize_identifier(label=label)
        pairs = (
            (institution, parsed.institution),
            (collection, parsed.collection),
            (catalog, parsed.catalog),
        )
        if parsed.state in {"ambiguous", "malformed"} or any(a and b and a != b for a, b in pairs):
            return Identifier(
                None,
                institution,
                collection,
                catalog,
                "ambiguous",
                "conflicting-explicit-components",
                original,
            )
    if catalog and (re.search(r"[,;/]", catalog) or re.fullmatch(r"\d+\s*[-–—]\s*\d+", catalog)):
        return Identifier(
            None,
            institution,
            collection,
            catalog,
            "ambiguous",
            "identifier-list-or-range",
            original,
        )
    if catalog and not re.fullmatch(r"(?=.*\d)[A-Za-z0-9][A-Za-z0-9._-]*", catalog):
        return Identifier(
            None,
            institution,
            collection,
            catalog,
            "malformed",
            "unsupported-catalog-format",
            original,
        )
    key = (
        MaterialKey(institution, collection, catalog)
        if institution and collection and catalog
        else None
    )
    return Identifier(
        key,
        institution,
        collection,
        catalog,
        "complete" if key else "partial",
        "explicit-triplet" if key else "missing-components",
        original,
    )


@dataclass(frozen=True)
class Assessment:
    source_record_id: UUID
    content_hash: str
    normalization_hash: str
    occurrence_id: UUID
    identifier: Identifier
    decision: Decision
    diagnostics: tuple[dict[str, Any], ...]
    references: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Preview:
    subject_dataset_id: UUID
    target_dataset_id: UUID
    policy_version: str
    input_digest: str
    source_state: dict[str, Any]
    items: tuple[Assessment, ...]
    counts: dict[str, int]


def context_diagnostics(subject: dict[str, Any], target: Target) -> dict[str, Any]:
    context = target.context
    material_name, accepted = (
        subject["raw_payload"].get("identified_name"),
        subject["raw_payload"].get("accepted_name"),
    )
    original_evidence = subject.get("original_identification", {})
    original = original_evidence.get("identified_name")
    other_name = context.get("scientific_name")
    latest = subject.get("scientific_name")
    taxonomy = bool(latest and other_name and latest != other_name)
    source_place = subject["collection_context"].get("collection_name")
    other_place = context.get("locality_name")
    locality = bool(source_place and other_place and source_place != other_place)
    bounds = [
        subject.get("older_ma"),
        subject.get("younger_ma"),
        context.get("older_ma"),
        context.get("younger_ma"),
    ]
    temporal = None
    if (
        bounds[0] is not None
        and bounds[1] is not None
        and bounds[2] is not None
        and bounds[3] is not None
    ):
        temporal = bounds[0] < bounds[3] or bounds[2] < bounds[1]
    source_coordinates = [subject["collection_context"].get(k) for k in ("lng", "lat")]
    target_coordinates = [context.get(k) for k in ("longitude", "latitude")]
    coordinate_difference = None
    if all(v is not None for v in source_coordinates + target_coordinates):
        from decimal import Decimal, InvalidOperation

        try:
            coordinate_difference = any(
                Decimal(str(a)) != Decimal(str(b))
                for a, b in zip(source_coordinates, target_coordinates, strict=True)
            )
        except InvalidOperation:
            pass
    subject_generalized = subject.get("location_is_generalized")
    target_generalized = context.get("location_is_generalized")
    geology = {
        k: {
            "subject": subject["collection_context"].get(k),
            "target": context.get("source_values", {}).get(k),
        }
        for k in ("group", "formation", "member")
    }
    return {
        "target_specimen_id": str(target.specimen_id),
        "institution": target.institution,
        "collection": target.collection,
        "catalog": target.catalog,
        "original_identification": original,
        "original_identification_evidence": original_evidence,
        "material_identification": material_name,
        "accepted_identification": accepted,
        "latest_identification": latest,
        "target_context": context,
        "subject_context": {
            "locality_id": str(subject.get("locality_id")),
            "collection": subject["collection_context"],
            "older_ma": str(subject.get("older_ma")),
            "younger_ma": str(subject.get("younger_ma")),
            "age_policy": subject.get("policy_version"),
            "occurrence_source_record_id": str(subject.get("occurrence_source_record_id")),
            "occurrence_content_hash": subject.get("occurrence_content_hash"),
            "occurrence_normalization_hash": subject.get("occurrence_normalization_hash"),
        },
        "taxonomic_disagreement": taxonomy if latest and other_name else None,
        "original_name_disagreement": original != other_name if original and other_name else None,
        "material_name_disagreement": material_name != other_name
        if material_name and other_name
        else None,
        "accepted_name_disagreement": accepted != other_name if accepted and other_name else None,
        "locality_disagreement": locality if source_place and other_place else None,
        "coordinate_difference": coordinate_difference,
        "coordinate_comparison": (
            "exact numeric source pairs only; PBDB datum unverified; no spatial identity"
        ),
        "subject_coordinate_generalized": subject_generalized,
        "target_coordinate_generalized": target_generalized,
        "generalized_coordinate_difference": coordinate_difference
        if subject_generalized or target_generalized
        else None,
        "stratigraphic_context": geology,
        "stratigraphic_context_disagreement": any(
            v["subject"] != v["target"] for v in geology.values() if v["subject"] and v["target"]
        )
        if any(v["subject"] and v["target"] for v in geology.values())
        else None,
        "temporal_disagreement": temporal,
        "temporal_comparison": "disjoint-inclusive-envelopes; distinct source policies",
        "locality_comparison": "exact source labels only; no place identity asserted",
    }


def preview_reconciliation(
    session: Session, subject_dataset_id: UUID, target_dataset_id: UUID
) -> Preview:
    """Read material evidence and constrained exact target keys, never a Cartesian product."""
    if subject_dataset_id == target_dataset_id:
        raise ValueError("Reconciliation requires independent source datasets")
    source_state = _source_state(session, subject_dataset_id, target_dataset_id)
    subjects = [
        dict(row)
        for row in session.execute(
            text("""SELECT
      sr.id source_record_id,sr.content_hash,nc.normalization_hash,me.occurrence_id,me.reference_id,
      me.catalog_label,coalesce(sr.raw_payload,mn.payload#>'{evidence,raw}') raw_payload,
      ce.locality_id,ce.scientific_name,ce.older_ma,ce.younger_ma,
      ce.policy_version,os.id occurrence_source_record_id,os.content_hash occurrence_content_hash,
      oc.normalization_hash occurrence_normalization_hash,
      nr.payload->'evidence'->'original_identification' original_identification,
      loc.location_is_generalized,
      coalesce(context.raw_payload,cn.payload#>'{evidence,raw}') collection_context
      FROM material_evidence me
      JOIN source_record sr ON sr.id=me.source_record_id
        AND sr.content_hash=me.content_hash AND sr.is_current
      JOIN source_dataset sd ON sd.id=sr.source_dataset_id AND NOT sd.is_synthetic
      JOIN source_normalization_current nc ON nc.source_record_id=sr.id
        AND nc.content_hash=sr.content_hash
      JOIN normalized_source_revision mn ON mn.source_record_id=sr.id
        AND mn.content_hash=sr.content_hash AND mn.normalization_hash=nc.normalization_hash
      JOIN catalog_entry ce ON ce.occurrence_id=me.occurrence_id AND ce.evidence_kind='occurrence'
      JOIN source_record os ON os.id=ce.source_record_id
        AND os.is_current AND os.content_hash=ce.content_hash
      JOIN source_normalization_current oc ON oc.source_record_id=os.id
        AND oc.normalization_hash=ce.normalization_hash AND oc.content_hash=os.content_hash
      JOIN normalized_source_revision nr ON nr.source_record_id=os.id
        AND nr.content_hash=os.content_hash AND nr.normalization_hash=oc.normalization_hash
      LEFT JOIN locality loc ON loc.id=ce.locality_id
      JOIN source_dependency_frame membership ON membership.source_record_id=os.id
        AND membership.content_hash=os.content_hash
        AND membership.normalization_hash=oc.normalization_hash
        AND membership.dependency_record_id=sr.id
        AND membership.dependency_content_hash=sr.content_hash
      JOIN source_record context ON context.id=ce.provider_age_source_record_id
      JOIN source_normalization_current cc ON cc.source_record_id=context.id
        AND cc.content_hash=context.content_hash
      JOIN normalized_source_revision cn ON cn.source_record_id=context.id
        AND cn.content_hash=cc.content_hash AND cn.normalization_hash=cc.normalization_hash
      WHERE sr.source_dataset_id=:subject AND os.source_dataset_id=:subject
      AND NOT EXISTS (SELECT 1 FROM source_normalization_invalid i
        WHERE i.source_record_id=sr.id AND i.content_hash=sr.content_hash
          AND i.normalization_hash=nc.normalization_hash)
      AND NOT EXISTS (SELECT 1 FROM source_normalization_invalid i
        WHERE i.source_record_id=os.id AND i.content_hash=os.content_hash
          AND i.normalization_hash=oc.normalization_hash)
      ORDER BY sr.id"""),
            {"subject": subject_dataset_id},
        ).mappings()
    ]
    identifiers = [normalize_identifier(label=row["catalog_label"]) for row in subjects]
    catalogs = sorted(
        {
            value.catalog
            for value in identifiers
            if value.catalog and value.state in {"complete", "partial"}
        }
    )
    institutions = sorted({value.institution for value in identifiers if value.institution})
    targets = []
    target_rows = (
        session.execute(
            text("""SELECT s.id specimen_id,sr.id source_record_id,sr.content_hash,
      s.institution_code,s.collection_code,s.catalog_number,sr.raw_payload,
      ce.scientific_name,ce.locality_id,l.name locality_name,
      ce.older_ma,ce.younger_ma,ce.age_basis,ce.policy_version,
      CASE WHEN NOT l.location_is_withheld THEN ST_X(l.geom) END longitude,
      CASE WHEN NOT l.location_is_withheld THEN ST_Y(l.geom) END latitude,
      l.location_is_withheld,l.location_is_generalized FROM specimen s
      JOIN specimen_evidence se ON se.specimen_id=s.id
      JOIN source_record sr ON sr.id=se.source_record_id AND sr.is_current
      JOIN source_dataset sd ON sd.id=sr.source_dataset_id AND NOT sd.is_synthetic
      JOIN catalog_entry ce ON ce.source_record_id=sr.id AND ce.content_hash=sr.content_hash
        AND ce.specimen_id=s.id AND ce.evidence_kind='material'
      LEFT JOIN locality l ON l.id=ce.locality_id
      WHERE sr.source_dataset_id=:target AND s.institution_code=ANY(:institutions)
      AND s.catalog_number=ANY(:catalogs) ORDER BY s.id,sr.id"""),
            {"target": target_dataset_id, "institutions": institutions, "catalogs": catalogs},
        )
        .mappings()
        .all()
    )
    for target_row in target_rows:
        row = dict(target_row)
        key = normalize_identifier(
            institution=row["institution_code"],
            collection=row["collection_code"],
            catalog=row["catalog_number"],
        ).key
        if key:
            context = {
                name: row[name]
                for name in (
                    "scientific_name",
                    "locality_id",
                    "locality_name",
                    "older_ma",
                    "younger_ma",
                    "age_basis",
                    "policy_version",
                    "longitude",
                    "latitude",
                    "location_is_withheld",
                    "location_is_generalized",
                )
            }
            context["source_values"] = {
                name: row["raw_payload"].get(name)
                for name in (
                    "institutionCode",
                    "collectionCode",
                    "catalogNumber",
                    "scientificName",
                    "locality",
                    "locationID",
                    "county",
                    "stateProvince",
                    "group",
                    "formation",
                    "member",
                    "earliestEpochOrLowestSeries",
                    "earliestPeriodOrLowestSystem",
                    "otherCatalogNumbers",
                    "fieldNumber",
                )
            }
            targets.append(
                Target(
                    row["specimen_id"],
                    row["source_record_id"],
                    row["content_hash"],
                    key.institution,
                    key.collection,
                    key.catalog,
                    context,
                )
            )
    references = {
        row["id"]: dict(row)
        for row in session.execute(
            text("""SELECT r.id,r.source_record_id,
      sr.content_hash,r.title,r.doi,r.published_year FROM research_reference r
      JOIN source_record sr ON sr.id=r.source_record_id
      WHERE sr.is_current AND r.id=ANY(:references)"""),
            {"references": list({row["reference_id"] for row in subjects if row["reference_id"]})},
        ).mappings()
    }
    items = []
    for row, identifier in zip(subjects, identifiers, strict=True):
        decision = match_identifier(identifier, targets)
        refs = (references[row["reference_id"]],) if row["reference_id"] in references else ()
        items.append(
            Assessment(
                row["source_record_id"],
                row["content_hash"],
                row["normalization_hash"],
                row["occurrence_id"],
                identifier,
                decision,
                tuple(context_diagnostics(row, target) for target in decision.targets),
                refs,
            )
        )
    counts = dict(Counter(item.decision.status for item in items))
    counts.update(
        material_records=len(items),
        occurrences_with_material=len({item.occurrence_id for item in items}),
        deterministic_material_records=counts.get("deterministic", 0),
        candidate_material_records=counts.get("candidate", 0),
        ambiguous_material_records=counts.get("ambiguous", 0),
        unresolved_material_records=counts.get("unresolved", 0),
        complete_identifiers=sum(item.identifier.state == "complete" for item in items),
        candidate_edges=sum(
            len(item.decision.targets) for item in items if item.decision.status != "deterministic"
        ),
        deterministic_edges=sum(
            len(item.decision.targets) for item in items if item.decision.status == "deterministic"
        ),
        target_records_considered=len(targets),
    )
    payload = {
        "subject": str(subject_dataset_id),
        "target": str(target_dataset_id),
        "policy": POLICY,
        "source_state": source_state,
        "items": asdict_items(items),
    }
    return Preview(
        subject_dataset_id,
        target_dataset_id,
        POLICY,
        digest(payload),
        source_state,
        tuple(items),
        counts,
    )


def asdict_items(items: Sequence[Assessment]) -> list[dict[str, Any]]:
    """JSON-safe deterministic evidence, including exact decimals and typed identities."""
    import json

    result: list[dict[str, Any]] = json.loads(
        json.dumps([asdict(item) for item in items], default=str)
    )
    return result


def _source_state(session: Session, subject: UUID, target: UUID) -> dict[str, Any]:
    rows = (
        session.execute(
            text("""SELECT sd.id,sd.version,sd.license,sd.is_synthetic,
      count(sr.id) records,
      md5(coalesce(string_agg(sr.id::text||sr.content_hash||sr.is_current::text,
        '' ORDER BY sr.id),'')) record_fingerprint FROM source_dataset sd
      LEFT JOIN source_record sr ON sr.source_dataset_id=sd.id
      WHERE sd.id=ANY(:datasets) GROUP BY sd.id ORDER BY sd.id"""),
            {"datasets": [subject, target]},
        )
        .mappings()
        .all()
    )
    if len(rows) != 2 or any(row["is_synthetic"] for row in rows):
        raise ValueError("Reconciliation requires two retained non-synthetic source datasets")
    return {str(row["id"]): dict(row, id=str(row["id"])) for row in rows}


def _guard_write(session: Session, checkpoint: Path | None) -> None:
    name = session.scalar(text("SELECT current_database()"))
    if name in {"paleograph_test", "paleograph_pbdb_canary"}:
        return
    if name != "paleograph" or checkpoint is None:
        raise ValueError("Normal reconciliation requires the verified pre-4D checkpoint")
    url = session.connection().engine.url
    if (
        url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
        or url.username != "paleograph"
    ):
        raise ValueError("Reconciliation checkpoint is scoped to the known local database")
    import hashlib
    import json

    evidence = json.loads(checkpoint.read_bytes())
    baseline = evidence["baseline"]
    if (
        evidence["status"] != "verified"
        or evidence["label"] != "pre-4d"
        or baseline["migration"] != "0010_pbdb_evidence"
    ):
        raise ValueError("Invalid pre-4D restore checkpoint")
    with Path(evidence["path"]).open("rb") as dump:
        if hashlib.file_digest(dump, "sha256").hexdigest() != evidence["sha256"]:
            raise ValueError("Checkpoint dump hash changed")


def _derived_id(value: object) -> UUID:
    return UUID(bytes=bytes.fromhex(digest(value)[:32]), version=4)


def reconcile(
    session: Session,
    subject_dataset_id: UUID,
    target_dataset_id: UUID,
    *,
    expected_input_digest: str,
    normal_checkpoint: Path | None = None,
) -> dict[str, Any]:
    """Atomically append evidence and publish its frame after validating the reviewed dry run."""
    _guard_write(session, normal_checkpoint)
    with session.begin_nested():
        session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
        session.execute(
            text(
                "LOCK TABLE source_record,source_dataset,source_normalization_current,"
                "catalog_entry,specimen_evidence,material_evidence IN SHARE MODE"
            )
        )
        preview = preview_reconciliation(session, subject_dataset_id, target_dataset_id)
        if preview.input_digest != expected_input_digest:
            raise ValueError("Source state changed since dry run; inspect a new complete preview")
        assessments, edges = [], []
        for item, serialized in zip(preview.items, asdict_items(preview.items), strict=True):
            assessment_id = _derived_id(
                [
                    "assessment",
                    str(item.source_record_id),
                    item.content_hash,
                    item.normalization_hash,
                    str(target_dataset_id),
                    POLICY,
                    preview.input_digest,
                ]
            )
            assessments.append(
                {
                    "id": assessment_id,
                    "subject_dataset_id": subject_dataset_id,
                    "target_dataset_id": target_dataset_id,
                    "source_record_id": item.source_record_id,
                    "content_hash": item.content_hash,
                    "normalization_hash": item.normalization_hash,
                    "occurrence_id": item.occurrence_id,
                    "policy_version": POLICY,
                    "input_digest": preview.input_digest,
                    "creation_method": "automatic",
                    "status": item.decision.status,
                    "reason": item.decision.reason,
                    "normalized_identifier": {
                        key: value
                        for key, value in serialized["identifier"].items()
                        if key != "original"
                    },
                    "original_values": serialized["identifier"]["original"],
                    "evidence": {
                        "kind": "explicit-material-identifier",
                        "references": serialized["references"],
                    },
                }
            )
            for target, diagnostic in zip(
                item.decision.targets, serialized["diagnostics"], strict=True
            ):
                edge_id = _derived_id(
                    [
                        "edge",
                        str(assessment_id),
                        str(target.specimen_id),
                        str(target.source_record_id),
                        target.content_hash,
                    ]
                )
                edges.append(
                    {
                        "id": edge_id,
                        "assessment_id": assessment_id,
                        "target_specimen_id": target.specimen_id,
                        "target_source_record_id": target.source_record_id,
                        "target_content_hash": target.content_hash,
                        "relationship_type": "material_identifier_matches"
                        if item.decision.status == "deterministic"
                        else "candidate_same_specimen",
                        "status": item.decision.status,
                        "diagnostics": diagnostic,
                        "supporting_reference_id": item.references[0]["id"]
                        if item.references
                        else None,
                    }
                )
        inserted = []
        for model, rows in ((ReconciliationAssessment, assessments), (ReconciliationEdge, edges)):
            count = 0
            for offset in range(0, len(rows), 500):
                statement = (
                    insert(model)
                    .values(rows[offset : offset + 500])
                    .on_conflict_do_nothing()
                    .returning(model.id)
                )
                count += len(session.scalars(statement).all())
            inserted.append(count)
        pointer = insert(ReconciliationGeneration).values(
            subject_dataset_id=subject_dataset_id,
            target_dataset_id=target_dataset_id,
            policy_version=POLICY,
            input_digest=preview.input_digest,
            source_state=preview.source_state,
        )
        session.execute(
            pointer.on_conflict_do_update(
                index_elements=["subject_dataset_id", "target_dataset_id", "policy_version"],
                set_={
                    "input_digest": preview.input_digest,
                    "source_state": preview.source_state,
                    "published_at": text("now()"),
                },
                where=ReconciliationGeneration.input_digest != preview.input_digest,
            )
        )
    return {
        "input_digest": preview.input_digest,
        "inserted_assessments": inserted[0],
        "inserted_edges": inserted[1],
        "counts": preview.counts,
    }


def reconciliation_records(
    session: Session,
    subject_dataset_id: UUID,
    target_dataset_id: UUID,
    *,
    include_history: bool = False,
    policy_version: str = POLICY,
) -> list[dict[str, Any]]:
    """Present reconciliation as current only while its complete source frame is current."""
    generation = (
        session.execute(
            text(
                "SELECT * FROM reconciliation_generation WHERE "
                "subject_dataset_id=:subject AND target_dataset_id=:target "
                "AND policy_version=:policy"
            ),
            {"subject": subject_dataset_id, "target": target_dataset_id, "policy": policy_version},
        )
        .mappings()
        .one_or_none()
    )
    if not include_history and (
        not generation
        or generation["source_state"]
        != _source_state(session, subject_dataset_id, target_dataset_id)
    ):
        return []
    params = {
        "subject": subject_dataset_id,
        "target": target_dataset_id,
        "policy": policy_version,
        "frame": generation["input_digest"] if generation else "",
    }
    rows = [
        dict(row)
        for row in session.execute(
            text(
                "SELECT * FROM reconciliation_assessment "
                "WHERE subject_dataset_id=:subject AND target_dataset_id=:target "
                "AND policy_version=:policy "
                + ("" if include_history else "AND input_digest=:frame ")
                + "ORDER BY id"
            ),
            params,
        ).mappings()
    ]
    edges = [
        dict(row)
        for row in session.execute(
            text(
                "SELECT e.*,r.decision review_decision,"
                "r.reviewer,r.reason review_reason,r.reviewed_at FROM reconciliation_edge e "
                "LEFT JOIN reconciliation_review r ON r.edge_id=e.id "
                "WHERE e.assessment_id=ANY(:ids) ORDER BY e.id"
            ),
            {"ids": [row["id"] for row in rows]},
        ).mappings()
    ]
    grouped: dict[UUID, list[dict[str, Any]]] = {}
    for edge in edges:
        grouped.setdefault(edge["assessment_id"], []).append(edge)
    for row in rows:
        row["edges"] = grouped.get(row["id"], [])
    return rows


def review_edge(
    session: Session,
    edge_id: UUID,
    *,
    decision: str,
    reviewer: str,
    reason: str,
    normal_checkpoint: Path | None = None,
) -> dict[str, Any]:
    """Annotate review; an accepted candidate is not promoted to automatic identity."""
    from app.models import ReconciliationReview

    _guard_write(session, normal_checkpoint)
    if (
        decision not in {"accept", "reject", "unresolved"}
        or not reviewer.strip()
        or not reason.strip()
    ):
        raise ValueError("Review requires a valid decision and reviewer/reason provenance")
    statement = insert(ReconciliationReview).values(
        edge_id=edge_id, decision=decision, reviewer=reviewer, reason=reason
    )
    result = (
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["edge_id"],
                set_={
                    "decision": decision,
                    "reviewer": reviewer,
                    "reason": reason,
                    "reviewed_at": text("now()"),
                },
            ).returning(
                ReconciliationReview.edge_id,
                ReconciliationReview.decision,
                ReconciliationReview.reviewer,
                ReconciliationReview.reason,
            )
        )
        .mappings()
        .one()
    )
    return dict(result)


def rebuild_reconciliation(
    session: Session,
    subject_dataset_id: UUID,
    target_dataset_id: UUID,
    *,
    expected_input_digest: str,
    normal_checkpoint: Path | None = None,
) -> dict[str, Any]:
    """Replace unreviewed automatic evidence atomically; reviewed/manual evidence survives."""
    _guard_write(session, normal_checkpoint)
    with session.begin_nested():
        session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
        removed = session.scalars(
            text("""DELETE FROM reconciliation_assessment a
          WHERE a.subject_dataset_id=:subject AND a.target_dataset_id=:target
            AND a.policy_version=:policy AND a.creation_method='automatic'
            AND NOT EXISTS (SELECT 1 FROM reconciliation_edge e
              JOIN reconciliation_review r ON r.edge_id=e.id WHERE e.assessment_id=a.id)
          RETURNING a.id"""),
            {"subject": subject_dataset_id, "target": target_dataset_id, "policy": POLICY},
        ).all()
        result = reconcile(
            session,
            subject_dataset_id,
            target_dataset_id,
            expected_input_digest=expected_input_digest,
            normal_checkpoint=normal_checkpoint,
        )
    return {**result, "removed_unreviewed_assessments": len(removed)}
