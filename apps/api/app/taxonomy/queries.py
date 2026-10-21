from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.discovery.queries import matching
from app.taxonomy.build import PROJECTION_VERSION
from app.taxonomy.policy import normalized
from app.taxonomy.schemas import (
    BranchChildren,
    BranchChildrenPage,
    ConceptPage,
    EvidencePreview,
    SourceConcept,
    TaxonomyDetail,
    TaxonomyNode,
    TaxonomyPage,
    TaxonomyQuery,
)

FRESH = """EXISTS (SELECT 1 FROM taxonomy_browse_state t JOIN browse_projection_state s ON s.id=1
    WHERE t.scope='florida' AND t.built_revision=s.input_revision AND
t.projection_version=:version)"""


def ready(session: Session) -> None:
    if not session.scalar(text("SELECT " + FRESH), {"version": PROJECTION_VERSION}):
        raise HTTPException(
            503,
            "Taxonomy classification snapshot needs rebuilding. "
            "Retry after the browse projection is refreshed.",
        )


def resolved(session: Session, identifier: UUID) -> UUID:
    """Old source-taxon URLs resolve through explicit reversible membership only."""
    value = session.scalar(
        text("""SELECT id FROM taxonomy_browse_node WHERE id=:id UNION ALL
        SELECT node_id FROM taxonomy_browse_alias WHERE old_id=:id UNION ALL
        SELECT node_id FROM taxonomy_browse_concept WHERE taxon_id=:id LIMIT 1"""),
        {"id": identifier},
    )
    if value is None:
        raise HTTPException(404, "Taxonomy browse node not found")
    return UUID(str(value))


def contextual(query: TaxonomyQuery) -> bool:
    return any(
        getattr(query, name) is not None
        for name in (
            "taxon_id",
            "locality_id",
            "collection_id",
            "institution_id",
            "term_id",
            "reference_id",
            "older_ma",
            "at_lon",
            "west",
        )
    )


def evidence_where(query: TaxonomyQuery) -> tuple[str, dict[str, Any]]:
    where, params = matching(query.model_copy(update={"q": ""}), eligibility="TRUE")
    if query.source != "all":
        where += " AND m.source=:source"
    params.update(source=query.source, version=PROJECTION_VERSION)
    return where, params


def nodes(session: Session, rows: list[Any], query: TaxonomyQuery) -> list[TaxonomyNode]:
    payloads: dict[UUID, dict[str, Any]] = {}
    if rows and contextual(query):
        where, params = evidence_where(query)
        params["ids"] = [row["id"] for row in rows]
        aggregates = (
            session.execute(
                text(f"""SELECT p.ancestor_id id,count(*) evidence_count,
            count(*) FILTER(WHERE p.depth=0) direct_count,
            count(*) FILTER(WHERE m.source='ufvp') ufvp_material_count,
            count(*) FILTER(WHERE m.source='pbdb') pbdb_occurrence_count,
        count(*) FILTER(WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL)
        known_age_count,
            count(*) FILTER(WHERE ce.older_ma IS NULL OR ce.younger_ma IS NULL) unknown_age_count,
            max(ce.older_ma) FILTER(WHERE ce.younger_ma IS NOT NULL) older_ma,
            min(ce.younger_ma) FILTER(WHERE ce.older_ma IS NOT NULL) younger_ma,
            count(*) FILTER(WHERE ce.age_basis='derived-interval') derived_count,
        count(*) FILTER(WHERE ce.age_basis IN ('provider-envelope','source-numeric'))
        source_numeric_count,
            max(ce.older_ma) FILTER(WHERE ce.age_basis='derived-interval') derived_older_ma,
            min(ce.younger_ma) FILTER(WHERE ce.age_basis='derived-interval') derived_younger_ma,
        max(ce.older_ma) FILTER(WHERE ce.age_basis IN
        ('provider-envelope','source-numeric')) source_older_ma,
        min(ce.younger_ma) FILTER(WHERE ce.age_basis IN
        ('provider-envelope','source-numeric')) source_younger_ma
            FROM taxonomy_browse_path p JOIN taxonomy_browse_member m ON m.node_id=p.node_id
        JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id LEFT JOIN locality l
        ON l.id=ce.locality_id
            WHERE p.ancestor_id=ANY(:ids) AND {where} AND {FRESH} GROUP BY p.ancestor_id"""),
                params,
            )
            .mappings()
            .all()
        )
        payloads = {row["id"]: dict(row) for row in aggregates}
        child_counts = (
            session.execute(
                text(f"""SELECT n.parent_id id,count(*) child_count FROM taxonomy_browse_node n
            WHERE n.parent_id=ANY(:ids) AND EXISTS (
            SELECT 1 FROM taxonomy_browse_path p JOIN taxonomy_browse_member m
            ON m.node_id=p.node_id JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id
            LEFT JOIN locality l ON l.id=ce.locality_id
            WHERE p.ancestor_id=n.id AND {where} AND {FRESH}) GROUP BY n.parent_id"""),
                params,
            )
            .mappings()
            .all()
        )
        for row in child_counts:
            payloads.setdefault(row["id"], {})["child_count"] = row["child_count"]
    result = []
    for row in rows:
        summary = row["summary"].get(query.source, {})
        if contextual(query):
            summary = payloads.get(row["id"], {})
        result.append(
            TaxonomyNode.model_validate(
                {
                    **row,
                    "counts": summary,
                    "identity_hint": row["summary"].get("identity_hint"),
                    "classification_path_ids": row["summary"].get("visual_ids_nearest", []),
                    "unified": row["summary"].get("unified", False),
                    "source_disagreement_note": row["summary"].get("source_disagreement_note"),
                    "sources": [
                        source
                        for source, field in [("ufvp", "ufvp_count"), ("pbdb", "pbdb_count")]
                        if row[field] > 0
                    ],
                }
            )
        )
    return result


def listing(
    session: Session, query: TaxonomyQuery, *, parent: UUID | None = None, search: bool = False
) -> TaxonomyPage:
    ready(session)
    params: dict[str, Any] = {
        "version": PROJECTION_VERSION,
        "source": query.source,
        "limit": query.limit,
        "offset": query.offset,
    }
    clauses = [FRESH, "n.scope='florida'", "(n.summary->:source->>'evidence_count')::bigint>0"]
    ordering = "(n.placement='container'),n.search_name,n.id"
    if search:
        params["exact"] = normalized(query.q.strip())
        escaped = params["exact"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses += ["n.placement<>'container'", "n.search_name LIKE :needle"]
        params["needle"] = "%" + escaped + "%"
        params["prefix"] = escaped + "%"
        ordering = (
            "CASE WHEN n.search_name=:exact THEN 0 "
            "WHEN n.search_name LIKE :prefix THEN 1 ELSE 2 END,n.search_name,"
            "(n.placement='supported') DESC,(n.ufvp_count>0 AND n.pbdb_count>0) DESC,"
            "(n.summary->:source->>'evidence_count')::bigint DESC,n.id"
        )
    else:
        clauses.append("n.parent_id=:parent" if parent else "n.parent_id IS NULL")
        if parent:
            params["parent"] = resolved(session, parent)
    if contextual(query):
        where, filters = evidence_where(query)
        params.update(filters)
        clauses.append(f"""
        EXISTS (SELECT 1 FROM taxonomy_browse_path p JOIN taxonomy_browse_member m ON
        m.node_id=p.node_id
        JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id LEFT JOIN locality l
        ON l.id=ce.locality_id
            WHERE p.ancestor_id=n.id AND {where})""")
    conditions = " AND ".join(clauses)
    total = (
        session.scalar(
            text(f"SELECT count(*) FROM taxonomy_browse_node n WHERE {conditions}"), params
        )
        or 0
    )
    rows = (
        session.execute(
            text(
                f"SELECT n.* FROM taxonomy_browse_node n WHERE {conditions} "
                f"ORDER BY {ordering} LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        .mappings()
        .all()
    )
    ready(session)
    return TaxonomyPage(
        items=nodes(session, list(rows), query),
        total=total,
        next_offset=query.offset + query.limit if query.offset + query.limit < total else None,
        version=PROJECTION_VERSION,
    )


def detail(session: Session, identifier: UUID, query: TaxonomyQuery) -> TaxonomyDetail:
    ready(session)
    identifier = resolved(session, identifier)
    params = {"id": identifier, "version": PROJECTION_VERSION}
    row = (
        session.execute(
            text(f"SELECT * FROM taxonomy_browse_node WHERE id=:id AND {FRESH}"), params
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        ready(session)
        raise HTTPException(404, "Taxonomy browse node not found")
    path = (
        session.execute(
            text(f"""
        SELECT n.* FROM taxonomy_browse_path p JOIN taxonomy_browse_node n ON
        n.id=p.ancestor_id
        WHERE p.node_id=:id AND p.depth>0 AND {FRESH} ORDER BY p.depth DESC"""),
            params,
        )
        .mappings()
        .all()
    )
    concepts = (
        session.execute(
            text(
                "SELECT source,concept_key,taxon_id,details FROM taxonomy_browse_concept "
                "WHERE node_id=:id ORDER BY source,concept_key LIMIT 30"
            ),
            params,
        )
        .mappings()
        .all()
    )
    total = (
        session.scalar(
            text("SELECT count(*) FROM taxonomy_browse_concept WHERE node_id=:id"), params
        )
        or 0
    )
    where, filters = evidence_where(query)
    filters["id"] = identifier
    evidence = (
        session.execute(
            text(f"""SELECT coalesce(ce.specimen_id,ce.occurrence_id) id,ce.occurrence_id,
        CASE WHEN m.source='ufvp' THEN 'specimen' ELSE 'occurrence' END kind,m.source,ce.label,
        ce.scientific_name,ce.locality_id,l.name
        locality_name,ce.older_ma,ce.younger_ma,ce.age_basis
        FROM taxonomy_browse_path p JOIN taxonomy_browse_member m ON m.node_id=p.node_id
        JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id LEFT JOIN locality l
        ON l.id=ce.locality_id
        WHERE p.ancestor_id=:id AND {where} AND {FRESH} ORDER BY ce.occurrence_id LIMIT 12"""),
            filters,
        )
        .mappings()
        .all()
    )
    ready(session)
    return TaxonomyDetail(
        node=nodes(session, [row], query)[0],
        ancestors=nodes(session, list(path), query),
        concepts=[SourceConcept.model_validate(row) for row in concepts],
        concept_total=total,
        evidence=[EvidencePreview.model_validate(row) for row in evidence],
        version=PROJECTION_VERSION,
    )


def concept_page(session: Session, identifier: UUID, query: TaxonomyQuery) -> ConceptPage:
    ready(session)
    identifier = resolved(session, identifier)
    params = {"id": identifier, "offset": query.offset, "limit": query.limit}
    rows = (
        session.execute(
            text(
                "SELECT source,concept_key,taxon_id,details FROM taxonomy_browse_concept "
                "WHERE node_id=:id ORDER BY source,concept_key LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        .mappings()
        .all()
    )
    total = (
        session.scalar(
            text("SELECT count(*) FROM taxonomy_browse_concept WHERE node_id=:id"), params
        )
        or 0
    )
    ready(session)
    return ConceptPage(
        items=[SourceConcept.model_validate(row) for row in rows],
        total=total,
        next_offset=query.offset + query.limit if query.offset + query.limit < total else None,
        version=PROJECTION_VERSION,
    )


def ancestor_page(session: Session, identifier: UUID, query: TaxonomyQuery) -> TaxonomyPage:
    ready(session)
    identifier = resolved(session, identifier)
    rows = (
        session.execute(
            text(f"""SELECT n.* FROM taxonomy_browse_path p
        JOIN taxonomy_browse_node n ON n.id=p.ancestor_id
        WHERE p.node_id=:id AND p.depth>0 AND {FRESH} ORDER BY p.depth DESC"""),
            {"id": identifier, "version": PROJECTION_VERSION},
        )
        .mappings()
        .all()
    )
    items = nodes(session, list(rows), query)
    ready(session)
    return TaxonomyPage(items=items, total=len(items), version=PROJECTION_VERSION)


def branch_children(session: Session, identifier: UUID, query: TaxonomyQuery) -> BranchChildrenPage:
    """First child pages for up to 64 ancestors, using fixed-count batched queries."""
    ready(session)
    identifier = resolved(session, identifier)
    parents = list(
        session.scalars(
            text("""SELECT ancestor_id FROM taxonomy_browse_path
      WHERE node_id=:id AND depth>0 ORDER BY depth DESC"""),
            {"id": identifier},
        )
    )
    selected = parents[query.offset : query.offset + 64]
    params: dict[str, Any] = {
        "parents": selected,
        "limit": query.limit,
        "source": query.source,
        "version": PROJECTION_VERSION,
    }
    clauses = [
        FRESH,
        "n.scope='florida'",
        "n.parent_id=ANY(:parents)",
        "(n.summary->:source->>'evidence_count')::bigint>0",
    ]
    if contextual(query):
        where, filters = evidence_where(query)
        params.update(filters)
        clauses.append(f"""EXISTS(SELECT 1 FROM taxonomy_browse_path p
          JOIN taxonomy_browse_member m ON m.node_id=p.node_id
          JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id
          LEFT JOIN locality l ON l.id=ce.locality_id
          WHERE p.ancestor_id=n.id AND {where})""")
    rows = (
        list(
            session.execute(
                text(f"""SELECT * FROM (
      SELECT n.*,count(*) OVER(PARTITION BY parent_id) branch_total,
      row_number() OVER(PARTITION BY parent_id ORDER BY n.search_name,n.id) position
      FROM taxonomy_browse_node n WHERE {" AND ".join(clauses)}) ranked
      WHERE position<=:limit ORDER BY parent_id,position"""),
                params,
            ).mappings()
        )
        if selected
        else []
    )
    represented = nodes(session, rows, query)
    groups: dict[UUID, list[TaxonomyNode]] = {parent: [] for parent in selected}
    totals: dict[UUID, int] = {}
    for row, node in zip(rows, represented, strict=True):
        groups[row["parent_id"]].append(node)
        totals[row["parent_id"]] = row["branch_total"]
    ready(session)
    return BranchChildrenPage(
        items=[
            BranchChildren(
                parent_id=parent,
                page=TaxonomyPage(
                    items=groups[parent],
                    total=totals.get(parent, 0),
                    next_offset=query.limit if totals.get(parent, 0) > query.limit else None,
                    version=PROJECTION_VERSION,
                ),
            )
            for parent in selected
        ],
        next_offset=query.offset + 64 if query.offset + 64 < len(parents) else None,
        version=PROJECTION_VERSION,
    )
