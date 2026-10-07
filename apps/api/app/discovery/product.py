"""Shared product reads with explicit source/evidence semantics and bounded contracts."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.discovery import associations, queries
from app.discovery.classification import classification_contexts
from app.discovery.multi_source import InternalQuery, occurrence_catalog
from app.discovery.occurrence_browse import eligibility, query_parameters
from app.discovery.pbdb import DATASET_UUID
from app.discovery.product_schemas import (
    EvidenceCounts,
    EvidenceItem,
    EvidencePage,
    OccurrenceEvidence,
    ProductDetail,
    ProductLocalitySummary,
    ReferenceItem,
    ReferencePage,
)
from app.discovery.schemas import ContextQuery, EntityKind, EntityRef
from app.ingestion.pbdb import POLICY_VERSION


def locality(session: Session, identifier: UUID, query: ContextQuery) -> ProductLocalitySummary:
    summary = associations.locality_summary(session, identifier, query)
    result = ProductLocalitySummary.model_validate(summary.model_dump())
    if summary.entity.source != "pbdb":
        return result
    where, params = queries.matching(ContextQuery(source="pbdb", locality_id=identifier))
    row = (
        session.execute(
            text(f"""SELECT sr.source_record_id external_id,sr.id source_record_id,
        sr.content_hash,pa.older_ma,pa.younger_ma,pa.evidence
        {queries.JOINS} JOIN provider_age_evidence pa
          ON pa.source_record_id=ce.provider_age_source_record_id
          AND pa.content_hash=ce.provider_age_content_hash
          AND pa.policy_version=ce.provider_age_policy_version
        JOIN source_record sr ON sr.id=pa.source_record_id WHERE {where}
        ORDER BY ce.occurrence_id LIMIT 1"""),
            params,
        )
        .mappings()
        .first()
    )
    if row:
        from app.discovery.product_schemas import CollectionContext

        age = row["evidence"]
        result.collection_context = CollectionContext.model_validate(
            {
                "external_id": row["external_id"],
                "source_record_id": row["source_record_id"],
                "content_hash": row["content_hash"],
                "modern_position": age["position"],
                "provider_age": {
                    "older_ma": row["older_ma"],
                    "younger_ma": row["younger_ma"],
                    "policy": POLICY_VERSION,
                    "early_interval": age["raw"].get("early_interval"),
                    "late_interval": age["raw"].get("late_interval"),
                    "determined_dates": age["dates"],
                },
            }
        )
    return result


def catalog(session: Session, query: ContextQuery) -> EvidencePage:
    page = occurrence_catalog(
        session, InternalQuery.model_validate(query.model_dump()), projected=True
    )
    classes = classification_contexts(session, [item.taxon_id for item in page.items])
    items = [
        EvidenceItem.model_validate(
            {
                **item.model_dump(),
                **classes.get(str(item.taxon_id), {}),
                "source": "pbdb" if item.source_dataset_id == DATASET_UUID else "ufvp",
            }
        )
        for item in page.items
    ]
    return EvidencePage(
        items=items,
        total=page.total,
        counts=EvidenceCounts.model_validate(page.counts),
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


def reference_item(row: dict[str, Any]) -> ReferenceItem:
    bibliography = row.pop("bibliography")
    authors = (
        " ".join(
            str(bibliography[k])
            for k in ("author1init", "author1last", "author2init", "author2last", "otherauthors")
            if bibliography.get(k)
        )
        or None
    )
    return ReferenceItem.model_validate(
        {**row, "authors": authors, "publication": bibliography.get("pubtitle")}
    )


def references(
    session: Session, kind: EntityKind, identifier: UUID, query: ContextQuery
) -> ReferencePage:
    """Explicit edge roles only, proven inside current occurrence dependency frames."""
    scope = query.model_copy(update={"source": "pbdb", "q": ""})
    where, params = queries.matching(scope)
    params["identifier"] = identifier
    if kind == "occurrence":
        where += " AND ce.occurrence_id=:identifier"
    elif kind == "locality":
        where += " AND ce.locality_id=:identifier"
    elif kind == "taxon":
        where += " AND ce.taxon_id=:identifier"
    else:
        return ReferencePage(items=[], total=0, next_cursor=None, limit=query.limit)
    sql = f"""WITH evidence AS MATERIALIZED (
        SELECT
        ce.occurrence_id,ce.locality_id,ce.source_record_id,ce.content_hash,ce.normalization_hash
        {queries.JOINS} WHERE {where}), roles AS (
        SELECT ie.source_record_id,ie.content_hash,ie.reference_id,'identification' role,
          ie.occurrence_id FROM identification_evidence ie
        WHERE ie.occurrence_id IN (SELECT occurrence_id FROM evidence)
        UNION ALL SELECT cr.source_record_id,cr.content_hash,cr.reference_id,'collection',o.id
          FROM collection_reference_evidence cr JOIN occurrence o
          ON o.collection_event_id=cr.collection_event_id WHERE o.id IN (SELECT occurrence_id
          FROM evidence)
        UNION ALL SELECT op.source_record_id,op.content_hash,op.reference_id,
          'taxonomic opinion',e.occurrence_id
          FROM evidence e JOIN source_record_dependency d ON d.source_record_id=e.source_record_id
          AND d.content_hash=e.content_hash AND d.normalization_hash=e.normalization_hash
          JOIN opinion_reference_evidence op ON op.source_record_id=d.dependency_record_id
          AND op.content_hash=d.dependency_content_hash
        UNION ALL SELECT
        me.source_record_id,me.content_hash,me.reference_id,'material',me.occurrence_id
          FROM material_evidence me WHERE me.occurrence_id IN (SELECT occurrence_id FROM evidence)
        ), proven AS (
        SELECT DISTINCT rr.id,rs.source_record_id external_id,rr.title,rr.doi,rr.published_year,
          rr.bibliography,r.role,r.source_record_id evidence_source_record_id
        FROM roles r JOIN evidence e ON e.occurrence_id=r.occurrence_id
        JOIN source_record origin ON origin.id=r.source_record_id AND origin.is_current
          AND origin.content_hash=r.content_hash
        JOIN source_record_dependency frame ON frame.source_record_id=e.source_record_id
          AND frame.content_hash=e.content_hash AND frame.normalization_hash=e.normalization_hash
          AND frame.dependency_record_id=origin.id AND
          frame.dependency_content_hash=origin.content_hash
        JOIN research_reference rr ON rr.id=r.reference_id
        JOIN source_record rs ON rs.id=rr.source_record_id AND rs.is_current
        JOIN source_record_dependency rf ON rf.source_record_id=e.source_record_id
          AND rf.content_hash=e.content_hash AND rf.normalization_hash=e.normalization_hash
          AND rf.dependency_record_id=rs.id AND rf.dependency_content_hash=rs.content_hash
        )"""
    namespace = f"references:{kind}:{identifier}"
    position = queries.decode_cursor(query, namespace)
    try:
        offset = int(position or "0")
        if not 0 <= offset <= 2**31 - 1:
            raise ValueError("offset")
    except ValueError as error:
        raise HTTPException(422, "Invalid reference cursor") from error
    params.update(limit=query.limit + 1, offset=offset)
    row = (
        session.execute(
            text(
                sql
                + """ SELECT (SELECT count(*) FROM proven) total,
        coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY
        published_year,id,role,evidence_source_record_id)
        FROM (SELECT * FROM proven ORDER BY published_year,id,role,evidence_source_record_id
          LIMIT :limit OFFSET :offset) p),'[]'::jsonb) items"""
            ),
            params,
        )
        .mappings()
        .one()
    )
    return ReferencePage(
        items=[reference_item(dict(i)) for i in row["items"][: query.limit]],
        total=row["total"],
        limit=query.limit,
        next_cursor=queries.encode_cursor(query, namespace, str(offset + query.limit))
        if len(row["items"]) > query.limit
        else None,
    )


def detail(
    session: Session, kind: EntityKind, identifier: UUID, query: ContextQuery
) -> ProductDetail:
    if kind in ("specimen", "collection", "institution"):
        return ProductDetail.model_validate(
            queries.detail(session, kind, identifier, query).model_dump()
        )
    if kind == "reference":
        row = (
            session.execute(
                text("""SELECT rr.id,sr.source_record_id external_id,rr.title,rr.doi,
            rr.published_year,rr.bibliography,'reference' role,sr.id evidence_source_record_id
            FROM research_reference rr JOIN source_record sr ON sr.id=rr.source_record_id
            JOIN source_dataset sd ON sd.id=sr.source_dataset_id
            WHERE rr.id=:id AND sr.is_current AND NOT sd.is_synthetic
              AND sd.id=:pbdb_dataset"""),
                {**query_parameters(), "id": identifier},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Current PBDB reference not found")
        ref = reference_item(dict(row))
        return ProductDetail(
            entity=EntityRef(
                kind=kind,
                id=identifier,
                label=ref.title or f"PBDB reference {ref.external_id}",
                subtitle=ref.published_year,
                source="pbdb",
            ),
            reference=ref,
            material_count=0,
            mapped_count=0,
            related=[],
            related_has_more=False,
            properties={},
            research_note="PBDB-supplied bibliographic metadata; no full publication text.",
        )
    if kind == "occurrence":
        params = {**query_parameters(), "id": identifier}
        row = (
            session.execute(
                text(f"""SELECT ce.*,l.name locality_name,sr.source_record_id external_id,
            nr.payload->'evidence' evidence,pa.evidence age_evidence
            {queries.JOINS} JOIN source_record sr ON sr.id=ce.source_record_id
            JOIN normalized_source_revision nr ON nr.source_record_id=ce.source_record_id
              AND nr.content_hash=ce.content_hash AND nr.normalization_hash=ce.normalization_hash
            JOIN provider_age_evidence pa ON pa.source_record_id=ce.provider_age_source_record_id
              AND pa.content_hash=ce.provider_age_content_hash AND
              pa.policy_version=ce.provider_age_policy_version
            WHERE ce.occurrence_id=:id AND {eligibility("pbdb")}"""),
                params,
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(404, "Current complete published occurrence not found")
        material_rows = (
            session.execute(
                text("""SELECT me.catalog_label,me.source_record_id
            FROM material_evidence me JOIN source_record sr ON sr.id=me.source_record_id
            AND sr.content_hash=me.content_hash AND sr.is_current
            JOIN source_record_dependency d ON d.source_record_id=:source AND d.content_hash=:hash
              AND d.normalization_hash=:normalization AND d.dependency_record_id=sr.id
              AND d.dependency_content_hash=sr.content_hash
            WHERE me.occurrence_id=:id ORDER BY me.source_record_id LIMIT 11"""),
                {
                    "id": identifier,
                    "source": row["source_record_id"],
                    "hash": row["content_hash"],
                    "normalization": row["normalization_hash"],
                },
            )
            .mappings()
            .all()
        )
        age = row["age_evidence"]
        occurrence = OccurrenceEvidence.model_validate(
            {
                "external_id": row["external_id"],
                "original_identification": row["evidence"]["original_identification"],
                "latest_identification": row["evidence"]["latest_identification"],
                "modern_position": age["position"],
                "provider_age": {
                    "older_ma": row["older_ma"],
                    "younger_ma": row["younger_ma"],
                    "policy": POLICY_VERSION,
                    "early_interval": age["raw"].get("early_interval"),
                    "late_interval": age["raw"].get("late_interval"),
                    "determined_dates": age["dates"],
                },
                "material_evidence_count": row["material_evidence_count"],
                "materials": material_rows[:10],
                "materials_has_more": len(material_rows) > 10,
                "content_hash": row["content_hash"],
                "normalization_hash": row["normalization_hash"],
            }
        )
        related = [queries.entity_ref(session, "taxon", row["taxon_id"])]
        if row["locality_id"]:
            related.append(queries.entity_ref(session, "locality", row["locality_id"]))
        return ProductDetail(
            entity=EntityRef(
                kind=kind,
                id=identifier,
                label=row["label"],
                subtitle=row["scientific_name"],
                source="pbdb",
            ),
            occurrence=occurrence,
            material_count=1,
            mapped_count=0,
            related=related,
            related_has_more=False,
            properties={},
            research_note="Explicit PBDB reference roles are available on demand. "
            "Material labels are source evidence; no canonical PBDB specimen is asserted.",
        )
    entity = queries.entity_ref(session, kind, identifier)
    if entity.source != "pbdb":
        return ProductDetail.model_validate(
            queries.detail(session, kind, identifier, query).model_dump()
        )
    context = queries.entity_context(kind, identifier, ContextQuery(source="pbdb", limit=12))
    page = catalog(session, context)
    properties: dict[str, Any] = {
        "authority": "Source-scoped PBDB identification; "
        "equal names do not merge taxonomic concepts."
    }
    related = []
    if kind == "locality":
        summary = associations.locality_summary(session, identifier, context)
        properties = summary.properties
        related = [i for i in associations.fauna(session, context).items]
    return ProductDetail(
        entity=entity,
        material_count=page.total,
        mapped_count=0,
        properties=properties,
        related=related,
        related_has_more=False,
        research_note="Published occurrence evidence from PBDB / CC0 1.0. "
        "Provider envelopes describe observed source evidence, not evolutionary duration.",
    )
