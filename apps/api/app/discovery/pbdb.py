"""Internal, bounded PBDB discovery. No public routes or cross-source reconciliation."""

from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Table, text
from sqlalchemy.orm import Session

from app.discovery.queries import JOINS, decode_cursor, encode_cursor, matching
from app.discovery.schemas import CatalogItem, CatalogPage, ContextQuery
from app.ingestion.pbdb import ADAPTER_VERSION, DATASET, POLICY_VERSION, PROVIDER, digest, stable_id

DATASET_UUID = stable_id("dataset", DATASET)
ELIGIBLE = """ce.evidence_kind='occurrence' AND ce.specimen_id IS NULL
    AND ce.policy_version=:pbdb_policy AND EXISTS (
      SELECT 1 FROM source_record sr JOIN source_dataset sd ON sd.id=sr.source_dataset_id
      JOIN source_normalization_current nc ON nc.source_record_id=sr.id
      WHERE sr.id=ce.source_record_id AND sr.source_dataset_id=:pbdb_dataset
        AND sr.is_current AND NOT sd.is_synthetic AND sr.content_hash=ce.content_hash
        AND nc.content_hash=ce.content_hash AND nc.normalization_hash=ce.normalization_hash)
    AND NOT EXISTS (
      SELECT 1 FROM source_record_dependency d
      JOIN source_record dep ON dep.id=d.dependency_record_id
      JOIN source_dataset ds ON ds.id=dep.source_dataset_id
      WHERE d.source_record_id=ce.source_record_id AND d.content_hash=ce.content_hash
        AND d.normalization_hash=ce.normalization_hash
        AND (NOT dep.is_current OR ds.is_synthetic
          OR dep.content_hash<>d.dependency_content_hash))"""


def parameters() -> dict[str, Any]:
    return {"pbdb_policy": POLICY_VERSION, "pbdb_dataset": DATASET_UUID}


def rebuild(session: Session, *, summaries: bool = True) -> dict[str, Any]:
    """Rebuild from retained normalized evidence in the caller's transaction."""
    session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
    params = parameters()
    scope = "SELECT id FROM source_record WHERE source_dataset_id=:pbdb_dataset"
    session.execute(
        text(
            "DELETE FROM catalog_term WHERE occurrence_id IN "
            f"(SELECT occurrence_id FROM catalog_entry WHERE source_record_id IN ({scope}))"
        ),
        params,
    )
    session.execute(text(f"DELETE FROM catalog_entry WHERE source_record_id IN ({scope})"), params)
    session.execute(
        text("""
      INSERT INTO catalog_entry (occurrence_id,specimen_id,taxon_id,locality_id,collection_id,
        institution_id,source_record_id,content_hash,policy_version,evidence_kind,
        material_evidence_count,normalization_hash,interpretation_policy_version,
        provider_age_source_record_id,provider_age_content_hash,provider_age_policy_version,
        label,scientific_name,search_text,older_ma,younger_ma,age_basis)
      SELECT o.id,NULL,o.taxon_id,e.locality_id,NULL,NULL,sr.id,sr.content_hash,:pbdb_policy,
        'occurrence',coalesce(material.count,0),nc.normalization_hash,NULL,
        context.id,context.content_hash,:pbdb_policy,
        'PBDB occurrence ' || sr.source_record_id,t.scientific_name,
        lower(concat_ws(' ',sr.source_record_id,t.scientific_name,l.name,
          nr.payload->'evidence'->'latest_identification'->>'accepted_name')),
        CASE WHEN pa.older_ma IS NOT NULL AND pa.younger_ma IS NOT NULL THEN pa.older_ma END,
        CASE WHEN pa.older_ma IS NOT NULL AND pa.younger_ma IS NOT NULL THEN pa.younger_ma END,
        CASE WHEN pa.older_ma IS NOT NULL AND pa.younger_ma IS NOT NULL THEN 'provider-envelope'
          WHEN pa.older_ma IS NOT NULL OR pa.younger_ma IS NOT NULL THEN 'provider-partial'
          ELSE 'absent' END
      FROM source_record sr JOIN occurrence_evidence oe ON oe.source_record_id=sr.id
      JOIN occurrence o ON o.id=oe.occurrence_id JOIN taxon t ON t.id=o.taxon_id
      JOIN collection_event e ON e.id=o.collection_event_id
      LEFT JOIN locality l ON l.id=e.locality_id
      JOIN collection_event_evidence ee ON ee.collection_event_id=e.id
      JOIN source_record context ON context.id=ee.source_record_id AND context.is_current
      JOIN provider_age_evidence pa ON pa.source_record_id=context.id
        AND pa.content_hash=context.content_hash
        AND pa.policy_version=:pbdb_policy
      JOIN source_normalization_current nc ON nc.source_record_id=sr.id
        AND nc.content_hash=sr.content_hash
      JOIN normalized_source_revision nr ON nr.source_record_id=nc.source_record_id
        AND nr.content_hash=nc.content_hash AND nr.normalization_hash=nc.normalization_hash
      LEFT JOIN (SELECT me.occurrence_id,count(*) count FROM material_evidence me
        JOIN source_record mr ON mr.id=me.source_record_id AND mr.content_hash=me.content_hash
        JOIN occurrence_evidence mo ON mo.occurrence_id=me.occurrence_id
        JOIN source_normalization_current mc ON mc.source_record_id=mo.source_record_id
        JOIN source_record_dependency md ON md.source_record_id=mc.source_record_id
          AND md.content_hash=mc.content_hash AND md.normalization_hash=mc.normalization_hash
          AND md.dependency_record_id=mr.id AND md.dependency_content_hash=mr.content_hash
        WHERE mr.is_current GROUP BY me.occurrence_id) material ON material.occurrence_id=o.id
      WHERE sr.source_dataset_id=:pbdb_dataset AND sr.record_type='occurrence' AND sr.is_current
        AND context.source_dataset_id=:pbdb_dataset
    """),
        params,
    )
    # PBDB identifications are self-membership only; source opinions remain evidence, not phylogeny.
    session.execute(
        text("""INSERT INTO taxon_path SELECT t.id,t.id FROM taxon t
        WHERE t.source_dataset_id=:pbdb_dataset ON CONFLICT DO NOTHING"""),
        params,
    )
    contexts = (
        session.execute(
            text(f"""SELECT ce.occurrence_id,pa.evidence->'raw' raw
        {JOINS} JOIN provider_age_evidence pa
          ON pa.source_record_id=ce.provider_age_source_record_id
          AND pa.content_hash=ce.provider_age_content_hash
          AND pa.policy_version=ce.provider_age_policy_version
        WHERE {ELIGIBLE}"""),
            params,
        )
        .mappings()
        .all()
    )
    from app.ingestion.import_pbdb import upsert
    from app.models import CatalogTerm, ContextTerm

    terms, links = [], []
    for row in contexts:
        for field in ("formation", "stratgroup", "member", "early_interval", "late_interval"):
            label = row["raw"].get(field)
            if not label:
                continue
            term_id = stable_id("term", digest({"field": field, "label": label}))
            terms.append(
                {
                    "id": term_id,
                    "source_dataset_id": DATASET_UUID,
                    "field": field,
                    "namespace": "PBDB-provider-interval"
                    if field.endswith("interval")
                    else "PBDB-stratigraphy",
                    "label": label,
                    "search_text": str(label).lower(),
                }
            )
            links.append({"occurrence_id": row["occurrence_id"], "term_id": term_id})
    upsert(session, cast(Table, ContextTerm.__table__), terms, immutable=True)
    upsert(session, cast(Table, CatalogTerm.__table__), links, immutable=True)
    if summaries:
        from app.discovery.browse import rebuild as rebuild_browse

        rebuild_browse(session)
    return {"occurrences": len(contexts), "terms": len({term["id"] for term in terms})}


def occurrence_catalog(session: Session, query: ContextQuery) -> CatalogPage:
    where, params = matching(query, eligibility=ELIGIBLE)
    params.update(parameters())
    namespace = f"pbdb-catalog:{DATASET}:{POLICY_VERSION}"
    total = int(session.scalar(text(f"SELECT count(*) {JOINS} WHERE {where}"), params) or 0)
    cursor = decode_cursor(query, namespace)
    if cursor:
        try:
            params["after"] = UUID(cursor)
        except ValueError as error:
            raise HTTPException(422, "Invalid PBDB catalog cursor") from error
        where += " AND ce.occurrence_id > :after"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(f"""
        WITH page AS MATERIALIZED (SELECT ce.occurrence_id {JOINS} WHERE {where}
          ORDER BY ce.occurrence_id LIMIT :limit)
        SELECT ce.occurrence_id id,ce.specimen_id,ce.evidence_kind,ce.material_evidence_count,
          ce.label,ce.scientific_name,ce.taxon_id,ce.locality_id,l.name locality_name,
          NULL::float8 longitude,NULL::float8 latitude,ce.older_ma,ce.younger_ma,ce.age_basis,
          pa.evidence->'raw'->>'early_interval' source_age_label
        FROM page JOIN catalog_entry ce ON ce.occurrence_id=page.occurrence_id
        LEFT JOIN locality l ON l.id=ce.locality_id JOIN provider_age_evidence pa
          ON pa.source_record_id=ce.provider_age_source_record_id
          AND pa.content_hash=ce.provider_age_content_hash
          AND pa.policy_version=ce.provider_age_policy_version
        ORDER BY ce.occurrence_id
    """),
            params,
        )
        .mappings()
        .all()
    )
    items = [CatalogItem.model_validate(row) for row in rows[: query.limit]]
    return CatalogPage(
        items=items,
        total=total,
        limit=query.limit,
        next_cursor=encode_cursor(query, namespace, str(items[-1].id))
        if len(rows) > query.limit
        else None,
    )


def inspect_occurrence(session: Session, occurrence_id: UUID) -> dict[str, Any]:
    params = {**parameters(), "occurrence": occurrence_id}
    row = (
        session.execute(
            text(f"""SELECT nr.payload,pa.evidence,pa.older_ma,pa.younger_ma,
        ce.source_record_id,ce.content_hash,ce.normalization_hash,ce.material_evidence_count,
        e.older_ma source_older_ma,e.younger_ma source_younger_ma,sr.source_record_id external_id
        {JOINS} JOIN occurrence o ON o.id=ce.occurrence_id
        JOIN collection_event e ON e.id=o.collection_event_id
        JOIN source_record sr ON sr.id=ce.source_record_id
        JOIN normalized_source_revision nr ON nr.source_record_id=ce.source_record_id
          AND nr.content_hash=ce.content_hash AND nr.normalization_hash=ce.normalization_hash
        JOIN provider_age_evidence pa ON pa.source_record_id=ce.provider_age_source_record_id
          AND pa.content_hash=ce.provider_age_content_hash
          AND pa.policy_version=ce.provider_age_policy_version
        WHERE ce.occurrence_id=:occurrence AND {ELIGIBLE}"""),
            params,
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "No current complete PBDB occurrence evidence")
    references = (
        session.execute(
            text("""SELECT d.dependency_record_id source_record_id,
        d.dependency_content_hash content_hash,rr.id reference_id,rr.bibliography
        FROM source_record_dependency d
        JOIN research_reference rr ON rr.source_record_id=d.dependency_record_id
        WHERE d.source_record_id=:source AND d.content_hash=:hash
          AND d.normalization_hash=:normalization"""),
            {
                "source": row["source_record_id"],
                "hash": row["content_hash"],
                "normalization": row["normalization_hash"],
            },
        )
        .mappings()
        .all()
    )
    materials = (
        session.execute(
            text("""SELECT me.evidence,me.catalog_label,me.reference_id,
        me.source_record_id,me.content_hash FROM material_evidence me JOIN source_record sr
        ON sr.id=me.source_record_id AND sr.content_hash=me.content_hash
        JOIN catalog_entry ce ON ce.occurrence_id=me.occurrence_id
        JOIN source_record_dependency d ON d.source_record_id=ce.source_record_id
          AND d.content_hash=ce.content_hash AND d.normalization_hash=ce.normalization_hash
          AND d.dependency_record_id=sr.id AND d.dependency_content_hash=sr.content_hash
        WHERE me.occurrence_id=:occurrence AND sr.is_current"""),
            params,
        )
        .mappings()
        .all()
    )
    return {
        **row["payload"]["evidence"],
        "source": {
            "dataset_id": DATASET_UUID,
            "external_dataset_id": DATASET,
            "provider": PROVIDER,
            "license": "CC0 1.0",
            "adapter_version": ADAPTER_VERSION,
        },
        "provider_age": {
            "policy": POLICY_VERSION,
            "older_ma": row["older_ma"],
            "younger_ma": row["younger_ma"],
            "determined_dates": row["evidence"]["dates"],
            "source_intervals": {
                key: row["evidence"]["raw"].get(key) for key in ("early_interval", "late_interval")
            },
        },
        "source_numeric_age": {
            "older_ma": row["source_older_ma"],
            "younger_ma": row["source_younger_ma"],
        },
        "modern_position": row["evidence"]["position"],
        "paleocoordinates": {
            key: value
            for key, value in row["evidence"]["raw"].items()
            if key.startswith("paleo") or key == "geoplate"
        },
        "provenance": {
            key: row[key]
            for key in ("source_record_id", "content_hash", "normalization_hash", "external_id")
        },
        "references": [dict(ref) for ref in references],
        "materials": [dict(material) for material in materials],
        "material_evidence_count": row["material_evidence_count"],
    }
