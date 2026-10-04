"""Locality associations and a bounded source hierarchy over the existing projection.

Time spans summarize indexed material. No temporal position describes an ancestor.
All aggregate membership passes the same current-public evidence guard as the atlas.
"""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.discovery.classification import classification_labels
from app.discovery.queries import (
    AGE_JOIN,
    JOINS,
    decode_cursor,
    encode_cursor,
    matching,
    safe_geography,
)
from app.discovery.schemas import (
    AssociationItem,
    AssociationPage,
    ContextQuery,
    EntityRef,
    LineageItem,
    LineagePage,
    LocalitySummary,
)

COUNTS = """
    count(*) assertion_count, count(DISTINCT ce.specimen_id) specimen_count,
    count(DISTINCT ce.taxon_id) source_taxon_count,
    max(ce.older_ma) FILTER (WHERE ce.younger_ma IS NOT NULL) older_ma,
    min(ce.younger_ma) FILTER (WHERE ce.older_ma IS NOT NULL) younger_ma,
    count(*) FILTER (WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL) known_age_count,
    count(*) FILTER (WHERE ce.older_ma IS NULL OR ce.younger_ma IS NULL) unknown_age_count
"""


def _page(
    session: Session, query: ContextQuery, sql: str, params: dict[str, Any], namespace: str
) -> AssociationPage:
    position = decode_cursor(query, namespace)
    offset = 0
    if position:
        try:
            offset = int(position)
            if not 0 <= offset <= 2**31 - 1:
                raise ValueError("negative offset")
        except ValueError as error:
            raise HTTPException(422, "Invalid association cursor") from error
    order = {
        "count": "assertion_count DESC,label,id",
        "name": "label,id",
        "hierarchy": "array_position(ARRAY['kingdom','phylum','class','order','family',"
        "'genus','species'],subtitle) NULLS LAST,label,id",
    }[getattr(query, "order", "count")]
    params["limit"] = query.limit + 1
    params["offset"] = offset
    response = (
        session.execute(
            text(f"""WITH associations AS MATERIALIZED ({sql}),
        page AS (SELECT * FROM associations ORDER BY {order} LIMIT :limit OFFSET :offset)
        SELECT (SELECT count(*) FROM associations) total,
            coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY {order})
                FROM page),'[]'::jsonb) items
        """),
            params,
        )
        .mappings()
        .one()
    )
    total, rows = response["total"], response["items"]
    classes = classification_labels(
        session, [UUID(row["id"]) for row in rows[: query.limit] if row["kind"] == "taxon"]
    )
    items = [
        AssociationItem.model_validate({**row, "classification": classes.get(row["id"], [])})
        for row in rows[: query.limit]
    ]
    return AssociationPage(
        items=items,
        total=total,
        limit=query.limit,
        next_cursor=encode_cursor(query, namespace, str(offset + query.limit))
        if len(rows) > query.limit
        else None,
    )


def localities(session: Session, query: ContextQuery) -> AssociationPage:
    where, params = matching(query.model_copy(update={"q": ""}))
    if query.q.strip():
        where += " AND lower(l.name) LIKE :label_filter"
        params["label_filter"] = _label_filter(query.q)
    sql = f"""SELECT 'locality' kind, l.id, l.name label, 'Published locality' subtitle,
        {COUNTS} {JOINS} WHERE {where} AND l.id IS NOT NULL GROUP BY l.id"""
    return _page(session, query, sql, params, "localities")


def fauna(session: Session, query: ContextQuery) -> AssociationPage:
    where, params = matching(query.model_copy(update={"q": ""}))
    if query.q.strip():
        where += " AND lower(t.scientific_name) LIKE :label_filter"
        params["label_filter"] = _label_filter(query.q)
    sql = f"""SELECT 'taxon' kind, t.id, t.scientific_name label, t.rank subtitle,
        {COUNTS} {JOINS} JOIN taxon t ON t.id=ce.taxon_id
        WHERE {where} GROUP BY t.id"""
    return _page(session, query, sql, params, "fauna")


def _label_filter(value: str) -> str:
    return (
        "%"
        + value.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        + "%"
    )


def locality_summary(session: Session, identifier: UUID, query: ContextQuery) -> LocalitySummary:
    row = (
        session.execute(
            text("""SELECT id, name label, description,
        coordinate_uncertainty_m, geodetic_datum, location_is_generalized, location_is_withheld,
        CASE WHEN NOT location_is_withheld THEN ST_X(geom) END longitude,
        CASE WHEN NOT location_is_withheld THEN ST_Y(geom) END latitude
        FROM locality WHERE id=:id AND EXISTS (SELECT 1 FROM catalog_entry ce
        JOIN source_record sr ON sr.id=ce.source_record_id AND sr.is_current AND
        sr.content_hash=ce.content_hash
        JOIN source_dataset sd ON sd.id=sr.source_dataset_id AND NOT sd.is_synthetic
        WHERE ce.locality_id=locality.id)"""),
            {"id": identifier},
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Current public locality not found")
    # A conflicting locality is a conjunction yielding no material, never a replacement filter.
    where, params = matching(query)
    params["focus_locality"] = identifier
    where += " AND ce.locality_id=:focus_locality"
    other_where, other_params = matching(query.model_copy(update={"locality_id": None}))
    params.update(other_params)
    result = (
        session.execute(
            text(f"""WITH material AS MATERIALIZED (
        SELECT ce.occurrence_id,ce.specimen_id,ce.taxon_id,ce.collection_id,ce.institution_id,
            ce.source_record_id,ce.content_hash,ce.policy_version,ce.older_ma,ce.younger_ma,ce.age_basis
        {JOINS} WHERE {where}
    ), terms AS (
        SELECT t.field,t.namespace,t.label,count(*) assertion_count
        FROM material ce JOIN catalog_term ct ON ct.occurrence_id=ce.occurrence_id
        JOIN context_term t ON t.id=ct.term_id GROUP BY t.id
    ), intervals AS (
        SELECT ai.interval_id,ai.source_label,ce.age_basis,ce.older_ma,ce.younger_ma,
            count(*) assertion_count FROM material ce{AGE_JOIN}
        GROUP BY ai.interval_id,ai.source_label,ce.age_basis,ce.older_ma,ce.younger_ma
    ), custody AS (
        SELECT c.id collection_id,coalesce(c.name,c.code) collection,i.name institution,
            count(*) assertion_count FROM material ce
        LEFT JOIN collection c ON c.id=ce.collection_id
        LEFT JOIN institution i ON i.id=ce.institution_id GROUP BY c.id,i.name
    ), related AS (
        SELECT DISTINCT 'locality' kind,l.id,l.name label,'Shared source identification' subtitle
        {JOINS} WHERE {other_where} AND ce.locality_id<>:focus_locality
        AND ce.taxon_id IN (SELECT DISTINCT taxon_id FROM material) ORDER BY l.id LIMIT 12
    ), summary AS (
        SELECT {COUNTS},count(DISTINCT ce.collection_id) collection_count,
            count(DISTINCT ce.institution_id) institution_count FROM material ce
    ) SELECT summary.*,
        coalesce((SELECT jsonb_agg(to_jsonb(terms) ORDER BY namespace,field,label)
            FROM terms),'[]'::jsonb) source_terms,
        coalesce((SELECT jsonb_agg(to_jsonb(intervals)
            ORDER BY older_ma DESC NULLS LAST,source_label)
            FROM intervals),'[]'::jsonb) interpreted_intervals,
        coalesce((SELECT jsonb_agg(to_jsonb(custody) ORDER BY collection,institution)
            FROM custody),'[]'::jsonb) custody,
        coalesce((SELECT jsonb_agg(to_jsonb(related) ORDER BY id)
            FROM related),'[]'::jsonb) related_localities
    FROM summary"""),
            params,
        )
        .mappings()
        .one()
    )
    properties = {
        key: value for key, value in row.items() if key not in {"id", "label", "description"}
    }
    properties["geography"] = safe_geography(row["description"], row["location_is_withheld"])
    return LocalitySummary(
        entity=EntityRef(kind="locality", id=identifier, label=row["label"]),
        **dict(result),
        properties=properties,
    )


# Resolve nearest published rank over prefix paths, including missing intermediate ranks.
# Source identification nodes sit BELOW their most specific supplied classification node,
# even if a genus-only identification repeats that node's label. Nothing is name-merged.
PARENTS = "parents AS (SELECT taxon_id id,parent_taxon_id parent_id FROM classification_link)"


def lineage(session: Session, query: ContextQuery, focus: UUID | None = None) -> LineagePage:
    where, params = matching(query)
    params.update(focus=focus, limit=query.limit + 1)
    if focus:
        where += (
            " AND EXISTS (SELECT 1 FROM taxon_path scope WHERE "
            "scope.taxon_id=ce.taxon_id AND scope.ancestor_id=:focus)"
        )
    # Aggregate leaf facts first, correcting ONLY specimens appearing under multiple
    # identifications. This is exact even when one specimen has several assertions;
    # it avoids sorting every assertion again at every ancestor rank.
    cte = f"""WITH RECURSIVE {PARENTS}, material AS MATERIALIZED (
        SELECT ce.taxon_id,ce.specimen_id,ce.older_ma,ce.younger_ma {JOINS} WHERE {where}
    ), leaves AS (
        SELECT ce.taxon_id,{COUNTS} FROM material ce GROUP BY ce.taxon_id
    ), duplicates AS (
        SELECT specimen_id FROM material GROUP BY specimen_id HAVING count(DISTINCT taxon_id)>1
    ), corrections AS (
        SELECT ancestor_id,sum(overcount)::bigint overcount FROM (
            SELECT p.ancestor_id,m.specimen_id,count(DISTINCT m.taxon_id)-1 overcount
            FROM material m JOIN duplicates d ON d.specimen_id=m.specimen_id
            JOIN taxon_path p ON p.taxon_id=m.taxon_id GROUP BY p.ancestor_id,m.specimen_id
        ) shared GROUP BY ancestor_id
    ), envelopes AS (
        SELECT p.ancestor_id id,sum(m.assertion_count)::bigint assertion_count,
            sum(m.specimen_count)::bigint specimen_count,count(*)::bigint source_taxon_count,
            max(m.older_ma) older_ma,min(m.younger_ma) younger_ma,
            sum(m.known_age_count)::bigint known_age_count,
            sum(m.unknown_age_count)::bigint unknown_age_count
        FROM leaves m JOIN taxon_path p ON p.taxon_id=m.taxon_id GROUP BY p.ancestor_id
    ), nodes AS (
        SELECT e.id,e.assertion_count,e.specimen_count-coalesce(c.overcount,0) specimen_count,
            e.source_taxon_count,e.older_ma,e.younger_ma,e.known_age_count,e.unknown_age_count
        FROM envelopes e LEFT JOIN corrections c ON c.ancestor_id=e.id
    ), branches AS (
        SELECT n.*,t.scientific_name label,t.rank subtitle,parents.parent_id,
            'taxon' kind, EXISTS(SELECT 1 FROM parents c JOIN nodes x ON x.id=c.id
                WHERE c.parent_id=n.id) has_children,
            EXISTS(SELECT 1 FROM taxon_path s WHERE s.taxon_id=n.id AND s.ancestor_id=n.id)
                is_source_identification
        FROM nodes n JOIN taxon t ON t.id=n.id LEFT JOIN parents ON parents.id=n.id
    )"""
    condition = "parent_id IS NULL" if focus is None else "parent_id=:focus"
    namespace = f"lineage:{focus}"
    position = decode_cursor(query, namespace)
    seek = ""
    if position:
        try:
            priority, identifier = position.split(":", 1)
            if priority not in {"0", "1"}:
                raise ValueError("Invalid classification priority")
            params["after_identification"] = priority == "1"
            params["after"] = UUID(identifier)
        except ValueError as error:
            raise HTTPException(422, "Invalid lineage cursor") from error
        seek = " AND (is_source_identification,id)>(:after_identification,:after)"
    response = (
        session.execute(
            text(f"""{cte}, page AS (
        SELECT * FROM branches WHERE {condition}{seek}
        ORDER BY is_source_identification,id LIMIT :limit)
        SELECT (SELECT count(*) FROM branches WHERE {condition}) total,
            coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY is_source_identification,id)
                FROM page),'[]'::jsonb) items,
            (SELECT to_jsonb(b) FROM branches b WHERE id=:focus) focal
    """),
            params,
        )
        .mappings()
        .one()
    )
    total = response["total"]
    rows = response["items"]
    # Breadcrumbs describe the stable published parent path, not chronology.
    crumbs = (
        session.execute(
            text(f"""WITH RECURSIVE {PARENTS}, trail AS (
        SELECT id,parent_id,0 depth FROM parents WHERE id=:focus UNION ALL
        SELECT p.id,p.parent_id,t.depth+1 FROM parents p JOIN trail t ON p.id=t.parent_id
        WHERE t.depth<10)
        SELECT 'taxon' kind,t.id,t.scientific_name label,t.rank subtitle
        FROM trail JOIN taxon t ON t.id=trail.id ORDER BY depth DESC"""),
            params,
        )
        .mappings()
        .all()
        if focus
        else []
    )
    if focus and not crumbs:
        raise HTTPException(404, "Source classification not found")
    ids = [UUID(row["id"]) for row in rows[: query.limit]]
    classifications = classification_labels(session, ids)
    items = [
        LineageItem.model_validate({**row, "classification": classifications.get(row["id"], [])})
        for row in rows[: query.limit]
    ]
    breadcrumbs = [EntityRef.model_validate(row) for row in crumbs]
    focal_row = response["focal"]
    focal = (
        LineageItem.model_validate(
            {**focal_row, "classification": [item.label for item in breadcrumbs]}
        )
        if focal_row
        else None
    )
    return LineagePage(
        items=items,
        focus=breadcrumbs[-1] if breadcrumbs else None,
        breadcrumbs=breadcrumbs,
        focal=focal,
        total=total,
        limit=query.limit,
        next_cursor=encode_cursor(
            query, namespace, f"{int(items[-1].is_source_identification)}:{items[-1].id}"
        )
        if len(rows) > query.limit
        else None,
    )
