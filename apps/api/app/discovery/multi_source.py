"""Internal source-aware occurrence pages. No product routes or reconciliation."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.discovery.pbdb import ELIGIBLE, parameters
from app.discovery.queries import AGE_JOIN, JOINS, PUBLIC, decode_cursor, encode_cursor, matching
from app.discovery.schemas import CatalogItem, ContextQuery


class InternalQuery(ContextQuery):
    source: Literal["ufvp", "pbdb", "all"] = "all"
    reference_id: UUID | None = None


class InternalItem(CatalogItem):
    source_dataset_id: UUID
    source_name: str
    source_license: str | None
    source_policy_version: str


class InternalPage(BaseModel):
    items: list[InternalItem]
    total: int
    next_cursor: str | None
    limit: int
    counts: dict[str, int]


def eligibility(source: str) -> str:
    ufvp = f"(ce.evidence_kind='material' AND {PUBLIC})"
    pbdb = f"({ELIGIBLE})"
    return ufvp if source == "ufvp" else pbdb if source == "pbdb" else f"({ufvp} OR {pbdb})"


def occurrence_catalog(
    session: Session, query: InternalQuery, *, projected: bool = False
) -> InternalPage:
    """Reference filtering means explicit current identification-to-reference edges."""
    if projected:
        from app.discovery.occurrence_browse import (
            eligibility as product_eligibility,
        )
        from app.discovery.occurrence_browse import (
            query_parameters,
        )

        supplied = query_parameters()
    else:
        supplied = parameters()
    # Keep each source's scientific guard as an independent plan. Source-scoped
    # UUIDs make this union disjoint, without merging any canonical entities.
    params = dict(supplied)
    parts = []
    for source in ("ufvp", "pbdb") if query.source == "all" else (query.source,):
        predicate = product_eligibility(source) if projected else eligibility(source)
        scoped = query.model_copy(update={"source": source})
        where, context_params = matching(scoped, eligibility=predicate)
        params.update(context_params)
        if query.reference_id:
            where += """ AND ce.occurrence_id IN (SELECT ie.occurrence_id
              FROM identification_evidence ie JOIN source_record ir ON ir.id=ie.source_record_id
              AND ir.content_hash=ie.content_hash AND ir.is_current
              WHERE ie.reference_id=:reference_id)"""
        parts.append(f"SELECT ce.occurrence_id,ce.evidence_kind {JOINS} WHERE {where}")
    membership = " UNION ALL ".join(parts)
    counts = dict(
        session.execute(
            text(f"""SELECT
      count(*) FILTER (WHERE ce.evidence_kind='material') museum_material,
      count(*) FILTER (WHERE ce.evidence_kind='occurrence') published_occurrences
      FROM ({membership}) ce"""),
            params,
        )
        .mappings()
        .one()
    )
    total = sum(counts.values())
    namespace = "internal-multi-source-v1"
    cursor = decode_cursor(query, namespace)
    seek = ""
    if cursor:
        try:
            params["after"] = UUID(cursor)
        except ValueError as error:
            raise HTTPException(422, "Invalid internal occurrence cursor") from error
        seek = "WHERE occurrence_id > :after"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(f"""WITH page AS MATERIALIZED (
          SELECT occurrence_id FROM ({membership}) candidates {seek}
          ORDER BY occurrence_id LIMIT :limit)
        SELECT ce.occurrence_id id,ce.specimen_id,ce.evidence_kind,ce.material_evidence_count,
          ce.label,ce.scientific_name,ce.taxon_id,ce.locality_id,l.name locality_name,
          CASE WHEN NOT l.location_is_withheld THEN ST_X(l.geom) END longitude,
          CASE WHEN NOT l.location_is_withheld THEN ST_Y(l.geom) END latitude,
          ce.older_ma,ce.younger_ma,ce.age_basis,
          CASE WHEN ce.evidence_kind='occurrence' THEN pa.evidence->'raw'->>'early_interval'
            ELSE ai.source_label END source_age_label,
          sd.id source_dataset_id,s.name source_name,sd.license source_license,
          ce.policy_version source_policy_version
        FROM page JOIN catalog_entry ce ON ce.occurrence_id=page.occurrence_id
        LEFT JOIN locality l ON l.id=ce.locality_id{AGE_JOIN}
        JOIN source_record sr ON sr.id=ce.source_record_id
        JOIN source_dataset sd ON sd.id=sr.source_dataset_id JOIN source s ON s.id=sd.source_id
        LEFT JOIN provider_age_evidence pa ON pa.source_record_id=ce.provider_age_source_record_id
          AND pa.content_hash=ce.provider_age_content_hash
          AND pa.policy_version=ce.provider_age_policy_version
        ORDER BY ce.occurrence_id"""),
            params,
        )
        .mappings()
        .all()
    )
    items = [InternalItem.model_validate(row) for row in rows[: query.limit]]
    return InternalPage(
        items=items,
        total=total,
        limit=query.limit,
        counts=counts,
        next_cursor=encode_cursor(query, namespace, str(items[-1].id))
        if len(rows) > query.limit
        else None,
    )


def source_counts(session: Session) -> dict[str, int]:
    row = (
        session.execute(
            text(f"""SELECT count(*) FILTER (WHERE ce.evidence_kind='material') ufvp_assertions,
      count(*) FILTER (WHERE ce.evidence_kind='occurrence') pbdb_occurrences,
      (SELECT count(*) FROM specimen) canonical_specimens,count(*) multi_source_occurrences
      {JOINS} WHERE {eligibility("all")}"""),
            parameters(),
        )
        .mappings()
        .one()
    )
    return {key: int(value) for key, value in row.items()}
