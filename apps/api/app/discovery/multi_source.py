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


def eligibility(source: str) -> str:
    ufvp = f"(ce.evidence_kind='material' AND {PUBLIC})"
    pbdb = f"({ELIGIBLE})"
    return ufvp if source == "ufvp" else pbdb if source == "pbdb" else f"({ufvp} OR {pbdb})"


def occurrence_catalog(session: Session, query: InternalQuery) -> InternalPage:
    """Reference filtering means explicit current identification-to-reference edges."""
    where, params = matching(query, eligibility=eligibility(query.source))
    params.update(parameters())
    if query.reference_id:
        params["reference"] = query.reference_id
        where += """ AND EXISTS (SELECT 1 FROM identification_evidence ie
          JOIN source_record ir ON ir.id=ie.source_record_id AND ir.content_hash=ie.content_hash
          JOIN source_record_dependency frame ON frame.source_record_id=ce.source_record_id
            AND frame.content_hash=ce.content_hash
            AND frame.normalization_hash=ce.normalization_hash
            AND frame.dependency_record_id=ir.id AND frame.dependency_content_hash=ir.content_hash
          WHERE ie.occurrence_id=ce.occurrence_id AND ie.reference_id=:reference
            AND ir.is_current)"""
    total = int(session.scalar(text(f"SELECT count(*) {JOINS} WHERE {where}"), params) or 0)
    namespace = "internal-multi-source-v1"
    cursor = decode_cursor(query, namespace)
    if cursor:
        try:
            params["after"] = UUID(cursor)
        except ValueError as error:
            raise HTTPException(422, "Invalid internal occurrence cursor") from error
        where += " AND ce.occurrence_id > :after"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(f"""WITH page AS MATERIALIZED (
          SELECT ce.occurrence_id {JOINS} WHERE {where} ORDER BY ce.occurrence_id LIMIT :limit)
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
