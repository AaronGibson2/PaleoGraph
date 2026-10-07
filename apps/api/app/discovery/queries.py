"""Bounded SQL discovery. No raw-payload scanning on interactive request paths."""

import base64
import hashlib
import json
import re
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.discovery.classification import classification_contexts, common_classification
from app.discovery.schemas import (
    CatalogItem,
    CatalogPage,
    ContextQuery,
    EntityDetail,
    EntityKind,
    EntityRef,
    GraphEdge,
    GraphPage,
    Place,
    PlacePage,
    SearchPage,
)
from app.discovery.timescale import POLICY_VERSION, configuration

JOINS = "FROM catalog_entry ce LEFT JOIN locality l ON l.id = ce.locality_id"
AGE_JOIN = (
    " LEFT JOIN age_interpretation ai ON ai.source_record_id = ce.source_record_id "
    "AND ai.content_hash = ce.content_hash AND ai.policy_version = ce.policy_version"
)
PUBLIC = (
    # A scientific-version change requires discovery repair before these rows
    # can be interpreted using the deployed reference configuration.
    f"ce.policy_version = '{POLICY_VERSION}' AND "
    "EXISTS (SELECT 1 FROM source_record sr JOIN source_dataset sd "
    "ON sd.id = sr.source_dataset_id WHERE sr.id = ce.source_record_id "
    "AND sr.is_current AND NOT sd.is_synthetic AND sr.content_hash = ce.content_hash)"
)


def safe_geography(description: Any, withheld: bool) -> dict[str, str]:
    """Public administrative labels; never return raw coordinate-bearing JSON."""
    try:
        raw = json.loads(description or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: raw[key]
        for key in ("continent", "country", "stateProvince", "county")
        if isinstance(raw.get(key), str) and not (withheld and key == "county")
    }


def matching(query: ContextQuery, *, eligibility: str | None = None) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if eligibility is None and query.source != "ufvp":
        from app.discovery.occurrence_browse import eligibility as product_eligibility
        from app.discovery.occurrence_browse import query_parameters

        eligibility = product_eligibility(query.source)
        params.update(query_parameters())
    clauses = [PUBLIC if eligibility is None else eligibility]
    if query.reference_id:
        clauses.append("""EXISTS (SELECT 1 FROM identification_evidence ie
            JOIN source_record ir ON ir.id=ie.source_record_id AND ir.is_current
              AND ir.content_hash=ie.content_hash
            JOIN source_record_dependency frame ON frame.source_record_id=ce.source_record_id
              AND frame.content_hash=ce.content_hash
              AND frame.normalization_hash=ce.normalization_hash
              AND frame.dependency_record_id=ir.id AND frame.dependency_content_hash=ir.content_hash
            WHERE ie.occurrence_id=ce.occurrence_id AND ie.reference_id=:reference_id)""")
        params["reference_id"] = query.reference_id
    for key in ("locality_id", "collection_id", "institution_id"):
        value = getattr(query, key)
        if value is not None:
            clauses.append(f"ce.{key} = :{key}")
            params[key] = value
    if query.taxon_id:
        clauses.append(
            "EXISTS (SELECT 1 FROM taxon_path tp WHERE tp.taxon_id = ce.taxon_id "
            "AND tp.ancestor_id = :taxon_id)"
        )
        params["taxon_id"] = query.taxon_id
    if query.term_id:
        clauses.append(
            "EXISTS (SELECT 1 FROM catalog_term ct WHERE "
            "ct.occurrence_id = ce.occurrence_id AND ct.term_id = :term_id)"
        )
        params["term_id"] = query.term_id
    if query.older_ma is not None:
        clauses.append("ce.older_ma >= :younger_ma AND ce.younger_ma <= :older_ma")
        params.update(older_ma=query.older_ma, younger_ma=query.younger_ma)
    if query.at_lon is not None:
        clauses.append(
            "l.geom = ST_SetSRID(ST_MakePoint(:at_lon, :at_lat), 4326) "
            "AND NOT l.location_is_withheld"
        )
        params.update(at_lon=query.at_lon, at_lat=query.at_lat)
    if query.west is not None:
        intersects = "ST_Intersects(l.geom, ST_MakeEnvelope(:west,:south,:east,:north,4326))"
        if query.east is not None and query.west > query.east:
            intersects = (
                "(ST_Intersects(l.geom, ST_MakeEnvelope(:west,:south,180,:north,4326)) "
                "OR ST_Intersects(l.geom,ST_MakeEnvelope(-180,:south,:east,:north,4326)))"
            )
        clauses.append(f"{intersects} AND NOT l.location_is_withheld")
        params.update(west=query.west, east=query.east, south=query.south, north=query.north)
    if query.q.strip():
        needle = query.q.strip().casefold()
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        words = re.findall(r"[\w]+", needle, flags=re.UNICODE)
        params.update(
            needle=needle,
            compact=re.sub(r"[^\w]", "", needle),
            prefix=escaped + "%",
            partial="%" + escaped + "%",
            tsquery=" & ".join(word + ":*" for word in words),
        )
        if words and len(needle) >= 3:
            clauses.append(
                "(ce.search_vector @@ to_tsquery('simple', :tsquery) "
                "OR ce.search_text LIKE :partial)"
            )
        else:
            clauses.append("lower(ce.label) LIKE :prefix OR lower(ce.scientific_name) LIKE :prefix")
            clauses[-1] = f"({clauses[-1]})"
    return " AND ".join(clauses), params


def fingerprint(query: ContextQuery, namespace: str) -> str:
    values = query.model_dump(mode="json", exclude={"cursor", "limit"})
    return hashlib.sha256((namespace + json.dumps(values, sort_keys=True)).encode()).hexdigest()[
        :16
    ]


def encode_cursor(query: ContextQuery, namespace: str, position: str) -> str:
    return base64.urlsafe_b64encode(f"{fingerprint(query, namespace)}|{position}".encode()).decode()


def decode_cursor(query: ContextQuery, namespace: str) -> str | None:
    if not query.cursor:
        return None
    try:
        key, position = (
            base64.b64decode(query.cursor, altchars=b"-_", validate=True).decode().split("|", 1)
        )
        if key != fingerprint(query, namespace):
            raise ValueError("Cursor context changed")
        return position
    except (ValueError, UnicodeError) as error:
        raise HTTPException(422, "Invalid or stale pagination cursor") from error


def catalog(session: Session, query: ContextQuery) -> CatalogPage:
    where, params = matching(query)
    total = int(session.scalar(text(f"SELECT count(*) {JOINS} WHERE {where}"), params) or 0)
    cursor = decode_cursor(query, "catalog")
    if cursor:
        try:
            params["after"] = UUID(cursor)
        except ValueError as error:
            raise HTTPException(422, "Invalid catalog cursor") from error
        where += " AND ce.occurrence_id > :after"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(f"""
        WITH page AS MATERIALIZED (
            SELECT ce.occurrence_id {JOINS} WHERE {where}
            ORDER BY ce.occurrence_id LIMIT :limit
        )
        SELECT ce.occurrence_id id, ce.specimen_id, ce.label, ce.scientific_name, ce.taxon_id,
            ce.locality_id, l.name locality_name,
            CASE WHEN NOT l.location_is_withheld THEN ST_X(l.geom) END longitude,
            CASE WHEN NOT l.location_is_withheld THEN ST_Y(l.geom) END latitude,
            ce.older_ma, ce.younger_ma, ce.age_basis, ai.source_label source_age_label
        FROM page JOIN catalog_entry ce ON ce.occurrence_id=page.occurrence_id
        LEFT JOIN locality l ON l.id=ce.locality_id{AGE_JOIN}
        ORDER BY ce.occurrence_id
        """),
            params,
        )
        .mappings()
        .all()
    )
    classes = classification_contexts(session, [row["taxon_id"] for row in rows[: query.limit]])
    items = [
        CatalogItem.model_validate({**row, **classes.get(str(row["taxon_id"]), {})})
        for row in rows[: query.limit]
    ]
    return CatalogPage(
        items=items,
        total=total,
        limit=query.limit,
        next_cursor=encode_cursor(query, "catalog", str(items[-1].id))
        if len(rows) > query.limit
        else None,
    )


def places(session: Session, query: ContextQuery) -> PlacePage:
    where, params = matching(query)
    membership = f"""SELECT ce.locality_id,count(*) record_count,
        count(*) FILTER (WHERE ce.evidence_kind='material') museum_material,
        count(*) FILTER (WHERE ce.evidence_kind='occurrence') published_occurrences,
        count(*) FILTER (WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL)
          interpreted_count {JOINS} WHERE {where} GROUP BY ce.locality_id"""
    if query.source == "all":
        # Independent source predicates allow PostgreSQL to use the existing UFVP
        # semijoin plan, instead of turning its public guard into 462k subplan probes.
        parts = []
        for source in ("ufvp", "pbdb"):
            source_where, source_params = matching(query.model_copy(update={"source": source}))
            params.update(source_params)
            parts.append(f"""SELECT ce.locality_id,count(*) record_count,
                count(*) FILTER (WHERE ce.evidence_kind='material') museum_material,
                count(*) FILTER (WHERE ce.evidence_kind='occurrence') published_occurrences,
                count(*) FILTER (WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL)
                  interpreted_count {JOINS} WHERE {source_where} GROUP BY ce.locality_id""")
        membership = f"""SELECT locality_id,sum(record_count)::bigint record_count,
            sum(museum_material)::bigint museum_material,
            sum(published_occurrences)::bigint published_occurrences,
            sum(interpreted_count)::bigint interpreted_count FROM
            ({" UNION ALL ".join(parts)}) source_places GROUP BY locality_id"""
    cursor = decode_cursor(query, "places")
    seek = ""
    if cursor:
        try:
            params["after"] = UUID(cursor)
        except ValueError as error:
            raise HTTPException(422, "Invalid place cursor") from error
        seek = "WHERE id > :after"
    params["limit"] = query.limit + 1
    # Material is counted once per canonical locality before position aggregation.
    # The same snapshot supplies totals and pagination, including an empty page.
    row = (
        session.execute(
            text(f"""
        WITH membership AS MATERIALIZED (
            {membership}
        ), points AS MATERIALIZED (
            SELECT discovery_uuid(ST_AsEWKT(l.geom)) id, ST_X(l.geom) longitude,
                ST_Y(l.geom) latitude, sum(m.record_count)::bigint record_count,
                count(*) locality_count, sum(m.interpreted_count)::bigint interpreted_count,
                sum(m.museum_material)::bigint museum_material,
                sum(m.published_occurrences)::bigint published_occurrences,
                bool_or(l.location_is_generalized) location_is_generalized
            FROM membership m JOIN locality l ON l.id=m.locality_id
            WHERE l.geom IS NOT NULL AND NOT l.location_is_withheld GROUP BY l.geom
        ), totals AS (
            SELECT coalesce(sum(m.record_count),0)::bigint total_records,
                coalesce(sum(m.museum_material),0)::bigint museum_material,
                coalesce(sum(m.published_occurrences),0)::bigint published_occurrences,
                coalesce(sum(m.published_occurrences) FILTER (WHERE l.geom IS NULL OR
                l.location_is_withheld),0)::bigint unmapped_published_occurrences,
                coalesce(sum(m.record_count) FILTER (WHERE l.geom IS NULL OR
        l.location_is_withheld),0)::bigint unmapped_records
            FROM membership m LEFT JOIN locality l ON l.id=m.locality_id
        ), page AS (SELECT * FROM points {seek} ORDER BY id LIMIT :limit)
        SELECT totals.*, (SELECT count(*) FROM points) total_places,
            coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY id) FROM page),'[]'::jsonb) items
        FROM totals
    """),
            params,
        )
        .mappings()
        .one()
    )
    items = [Place.model_validate(item) for item in row["items"][: query.limit]]
    return PlacePage(
        items=items,
        total_records=row["total_records"],
        museum_material=row["museum_material"],
        published_occurrences=row["published_occurrences"],
        unmapped_published_occurrences=row["unmapped_published_occurrences"],
        unmapped_records=row["unmapped_records"],
        total_places=row["total_places"],
        limit=query.limit,
        next_cursor=encode_cursor(query, "places", str(items[-1].id))
        if len(row["items"]) > query.limit
        else None,
    )


def search(session: Session, query: ContextQuery) -> SearchPage:
    if not query.q.strip():
        return SearchPage(items=[], total=0, limit=query.limit, next_cursor=None)
    supplied_id = re.fullmatch(
        r"(?:pbdb\s+)?(?:occ(?:urrence)?|col(?:lection)?|ref(?:erence)?)[\s:]+(\d+)",
        query.q.strip(),
        re.IGNORECASE,
    )
    lookup = (
        query.model_copy(update={"q": supplied_id[1]})
        if supplied_id and query.source != "ufvp"
        else query
    )
    where, params = matching(lookup)
    # All kinds are scoped through actual current catalog membership and active context.
    reference_candidates = ""
    if query.source != "ufvp":
        reference_where, reference_params = matching(query.model_copy(update={"q": ""}))
        params.update(reference_params)
        reference_candidates = f"""UNION ALL
          SELECT 'reference',rr.id,coalesce(rr.title,'PBDB reference '||rs.source_record_id),
            rr.published_year,NULL::uuid FROM research_reference rr
          JOIN source_record rs ON rs.id=rr.source_record_id AND rs.is_current
          WHERE lower(concat_ws(' ',rr.title,rr.doi,rs.source_record_id,
            rr.bibliography->>'author1last',rr.bibliography->>'author2last',
            rr.bibliography->>'otherauthors')) LIKE :partial
          AND EXISTS (SELECT 1 {JOINS} JOIN source_record_dependency rf
            ON rf.source_record_id=ce.source_record_id AND rf.content_hash=ce.content_hash
            AND rf.normalization_hash=ce.normalization_hash AND rf.dependency_record_id=rs.id
            AND rf.dependency_content_hash=rs.content_hash WHERE {reference_where})"""
        reference_candidates += f""" UNION
          SELECT 'locality',l.id,l.name,'PBDB collection context',NULL::uuid
          FROM locality l JOIN locality_evidence le ON le.locality_id=l.id
          JOIN source_record cs ON cs.id=le.source_record_id AND cs.is_current
          WHERE cs.source_record_id=:needle AND cs.record_type='collection'
            AND cs.source_dataset_id=:pbdb_dataset
            AND EXISTS (SELECT 1 FROM catalog_entry ce WHERE ce.locality_id=l.id
              AND {reference_where})"""
    union = f"""
        WITH material AS (SELECT ce.* {JOINS} WHERE {where}), candidates AS (
        SELECT DISTINCT 'taxon' kind, t.id, t.scientific_name label, t.rank subtitle,
            t.id classification_taxon_id
        FROM material m JOIN taxon_path p ON p.taxon_id = m.taxon_id
        JOIN taxon t ON t.id = p.ancestor_id
        WHERE lower(t.scientific_name) LIKE :partial
        UNION ALL SELECT DISTINCT 'locality', l.id, l.name, 'Published locality', NULL::uuid
        FROM material m JOIN locality l ON l.id = m.locality_id WHERE lower(l.name) LIKE :partial
        UNION ALL SELECT DISTINCT 'collection', c.id, coalesce(c.name,c.code), c.code, NULL::uuid
        FROM material m JOIN collection c ON c.id = m.collection_id
        WHERE lower(concat_ws(' ',c.name,c.code)) LIKE :partial
        UNION ALL SELECT DISTINCT 'institution', i.id, i.name, i.code, NULL::uuid
        FROM material m JOIN institution i ON i.id = m.institution_id
        WHERE lower(concat_ws(' ',i.name,i.code)) LIKE :partial
        UNION ALL SELECT DISTINCT 'term', t.id, t.label, t.namespace || ' / ' || t.field, NULL::uuid
        FROM material m JOIN catalog_term ct ON ct.occurrence_id = m.occurrence_id
        JOIN context_term t ON t.id = ct.term_id WHERE t.search_text LIKE :partial
        UNION ALL SELECT CASE WHEN m.specimen_id IS NULL THEN 'occurrence' ELSE 'specimen' END,
            coalesce(m.specimen_id,m.occurrence_id),m.label,m.scientific_name,m.taxon_id
        FROM material m
        {reference_candidates}
        ) SELECT *, CASE WHEN lower(label) = :needle OR
            (kind = 'specimen' AND (regexp_replace(lower(label),'[^[:alnum:]]','','g')
                = :compact OR lower(split_part(label,' / ',2)) = :needle)) THEN 0
            WHEN kind IN ('specimen','occurrence') THEN 3
            WHEN lower(label) LIKE :prefix THEN 1 ELSE 2 END ranking FROM candidates
        """
    total = int(session.scalar(text(f"SELECT count(*) FROM ({union}) results"), params) or 0)
    position = decode_cursor(query, "search")
    seek = ""
    if position:
        try:
            rank, kind, identifier = position.split(":", 2)
            params.update(after_rank=int(rank), after_kind=kind, after_id=UUID(identifier))
        except ValueError as error:
            raise HTTPException(422, "Invalid search cursor") from error
        seek = "WHERE (ranking,kind,id) > (:after_rank,:after_kind,:after_id)"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(f"SELECT * FROM ({union}) results {seek} ORDER BY ranking,kind,id LIMIT :limit"),
            params,
        )
        .mappings()
        .all()
    )
    classes = classification_contexts(
        session,
        [
            row["classification_taxon_id"]
            for row in rows[: query.limit]
            if row["classification_taxon_id"]
        ],
    )
    items = [
        EntityRef.model_validate({**row, **classes.get(str(row["classification_taxon_id"]), {})})
        for row in rows[: query.limit]
    ]
    # Batch source labels over the bounded result page; UUIDs stay source-scoped.
    source_rows = (
        session.execute(
            text("""SELECT id,source_dataset_id FROM taxon WHERE id=ANY(:ids)
        UNION ALL SELECT le.locality_id,sr.source_dataset_id FROM locality_evidence le
          JOIN source_record sr ON sr.id=le.source_record_id WHERE le.locality_id=ANY(:ids)
        UNION ALL SELECT id,source_dataset_id FROM context_term WHERE id=ANY(:ids)"""),
            {"ids": [i.id for i in items]},
        ).all()
        if items
        else []
    )
    from app.discovery.pbdb import DATASET_UUID

    sources: dict[UUID, Literal["pbdb", "ufvp"]] = {
        identifier: "pbdb" if dataset == DATASET_UUID else "ufvp"
        for identifier, dataset in source_rows
    }
    for item in items:
        item.source = (
            "pbdb" if item.kind in ("occurrence", "reference") else sources.get(item.id, "ufvp")
        )
        if item.kind == "locality" and item.source == "pbdb":
            item.subtitle = "PBDB collection context"
    last = rows[query.limit - 1] if len(rows) > query.limit else None
    return SearchPage(
        items=items,
        total=total,
        limit=query.limit,
        next_cursor=encode_cursor(query, "search", f"{last['ranking']}:{last['kind']}:{last['id']}")
        if last
        else None,
    )


def entity_context(kind: EntityKind, identifier: UUID, query: ContextQuery) -> ContextQuery:
    patch: dict[str, Any] = {
        "cursor": None,
        "q": "",
        "west": None,
        "east": None,
        "north": None,
        "south": None,
        "at_lon": None,
        "at_lat": None,
    }
    if kind != "specimen":
        patch[f"{kind}_id"] = identifier
    return query.model_copy(update=patch)


def entity_ref(session: Session, kind: EntityKind, identifier: UUID) -> EntityRef:
    tables = {
        "specimen": ("catalog_entry", "specimen_id", "label", "scientific_name"),
        "occurrence": ("catalog_entry", "occurrence_id", "label", "scientific_name"),
        "reference": (
            "research_reference",
            "id",
            "coalesce(title,'PBDB reference')",
            "published_year",
        ),
        "taxon": ("taxon", "id", "scientific_name", "rank"),
        "locality": ("locality", "id", "name", "'Published locality'"),
        "collection": ("collection", "id", "coalesce(name,code)", "code"),
        "institution": ("institution", "id", "name", "code"),
        "term": ("context_term", "id", "label", "namespace"),
    }
    table, key, label, subtitle = tables[kind]
    row = (
        session.execute(
            text(
                f"SELECT {key} id, {label} label, {subtitle} subtitle "
                f"FROM {table} WHERE {key} = :id"
            ),
            {"id": identifier},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Entity not found")
    source = "ufvp"
    if kind in ("taxon", "locality", "term", "reference"):
        dataset_sql = (
            (
                "SELECT sr.source_dataset_id FROM locality_evidence le "
                "JOIN source_record sr ON sr.id=le.source_record_id "
                "WHERE le.locality_id=:id AND sr.is_current LIMIT 1"
            )
            if kind == "locality"
            else f"SELECT source_dataset_id FROM {table} WHERE {key}=:id"
        )
        dataset = session.scalar(text(dataset_sql), {"id": identifier})
        from app.discovery.pbdb import DATASET_UUID

        source = "pbdb" if dataset == DATASET_UUID else "ufvp"
    elif kind == "occurrence":
        source = "pbdb"
    classification = {}
    if kind == "taxon":
        classification = classification_contexts(session, [identifier]).get(str(identifier), {})
    elif kind == "specimen":
        ids = list(
            session.scalars(
                text(
                    "SELECT DISTINCT ce.taxon_id FROM catalog_entry ce "
                    f"WHERE ce.specimen_id=:id AND {PUBLIC}"
                ),
                {"id": identifier},
            )
        )
        contexts = classification_contexts(session, ids)
        classification = common_classification(
            [
                contexts.get(str(taxon_id), {"classification": [], "classification_path_ids": []})
                for taxon_id in ids
            ]
        )
    result = EntityRef.model_validate({"kind": kind, **row, **classification, "source": source})
    if kind == "locality" and source == "pbdb":
        result.subtitle = "PBDB collection context"
    return result


def related_sql(kind: EntityKind, identifier: UUID, where: str) -> str:
    """Only membership/classification/holding/context joins; no inferred edges."""
    root_filter = "AND ce.specimen_id = :root_id" if kind == "specimen" else ""
    material = f"WITH material AS (SELECT ce.* {JOINS} WHERE {where} {root_filter})"
    return (
        material
        + """, neighbors AS (
        SELECT DISTINCT 'taxon' kind, t.id, t.scientific_name label, t.rank subtitle,
               'identified / source classification' relationship
        FROM material m JOIN taxon_path p ON p.taxon_id = m.taxon_id
        JOIN taxon t ON t.id = p.ancestor_id
        UNION ALL SELECT DISTINCT 'locality', l.id, l.name, 'Published locality', 'recorded at'
        FROM material m JOIN locality l ON l.id = m.locality_id
        UNION ALL SELECT DISTINCT 'collection', c.id, coalesce(c.name,c.code), c.code,
            'cataloged in'
        FROM material m JOIN collection c ON c.id = m.collection_id
        UNION ALL SELECT DISTINCT 'institution', i.id, i.name, i.code, 'held by'
        FROM material m JOIN institution i ON i.id = m.institution_id
        UNION ALL SELECT DISTINCT 'term', t.id, t.label, t.namespace, 'source context'
        FROM material m JOIN catalog_term ct ON ct.occurrence_id = m.occurrence_id
        JOIN context_term t ON t.id = ct.term_id
        UNION ALL SELECT 'specimen', m.specimen_id, m.label, m.scientific_name, 'catalog assertion'
        FROM material m
        ) SELECT *, row_number() OVER (PARTITION BY kind ORDER BY id) progression
        FROM neighbors WHERE NOT (kind = :root_kind AND id = :root_id)
        """
    )


def graph(session: Session, kind: EntityKind, identifier: UUID, query: ContextQuery) -> GraphPage:
    root = entity_ref(session, kind, identifier)
    context = entity_context(kind, identifier, query)
    where, params = matching(context)
    params.update(root_id=identifier, root_kind=kind)
    neighborhood = related_sql(kind, identifier, where)
    total = int(session.scalar(text(f"SELECT count(*) FROM ({neighborhood}) n"), params) or 0)
    # Zero catalog membership rejects synthetic/inactive/stale canonical entities.
    public_where = where + (" AND ce.specimen_id = :root_id" if kind == "specimen" else "")
    if not session.scalar(text(f"SELECT EXISTS (SELECT 1 {JOINS} WHERE {public_where})"), params):
        raise HTTPException(404, "No current public catalog material for this entity and context")
    namespace = f"graph:{kind}:{identifier}"
    position = decode_cursor(query, namespace)
    seek = ""
    if position:
        try:
            progression, after_kind, after_id = position.split(":", 2)
            params.update(
                after_progression=int(progression), after_kind=after_kind, after_id=UUID(after_id)
            )
        except ValueError as error:
            raise HTTPException(422, "Invalid graph cursor") from error
        seek = "WHERE (progression,kind,id) > (:after_progression,:after_kind,:after_id)"
    params["limit"] = query.limit + 1
    rows = (
        session.execute(
            text(
                f"SELECT * FROM ({neighborhood}) n {seek} ORDER BY progression,kind,id LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    neighbors = [EntityRef.model_validate(row) for row in rows[: query.limit]]
    # Between aggregate roots and material-derived context these are explicitly ASSOCIATIONS,
    # not direct occurrence assertions or universal biological relationships.
    edges = [
        GraphEdge(
            source=f"{kind}:{identifier}",
            target=f"{item.kind}:{item.id}",
            label=row["relationship"] if kind == "specimen" else "associated catalog material",
        )
        for item, row in zip(neighbors, rows, strict=False)
    ]
    last = rows[query.limit - 1] if len(rows) > query.limit else None
    return GraphPage(
        root=root,
        nodes=[root, *neighbors],
        edges=edges,
        total_neighbors=total,
        limit=query.limit,
        next_cursor=encode_cursor(
            query, namespace, f"{last['progression']}:{last['kind']}:{last['id']}"
        )
        if last
        else None,
    )


def detail(
    session: Session, kind: EntityKind, identifier: UUID, query: ContextQuery
) -> EntityDetail:
    # Inspection remains available when a selected record lies outside active map/time
    # results. Neighborhood expansion, unlike inspection, respects the active context.
    query = ContextQuery(limit=32 if kind == "specimen" else 14)
    neighborhood = graph(session, kind, identifier, query)
    context = entity_context(kind, identifier, query)
    where, params = matching(context)
    if kind == "specimen":
        where += " AND ce.specimen_id = :specimen"
        params["specimen"] = identifier
    counts = session.execute(
        text(
            f"SELECT count(*), count(*) FILTER "
            f"(WHERE l.geom IS NOT NULL AND NOT l.location_is_withheld) "
            f"{JOINS} WHERE {where}"
        ),
        params,
    ).one()
    properties: dict[str, Any] = {}
    if kind == "specimen":
        row = (
            session.execute(
                text(
                    f"SELECT ce.occurrence_id, ai.status, ai.source_field, "
                    "ai.source_label, ai.rule, ai.policy_version, ai.interval_id, "
                    "ai.older_ma, ai.younger_ma, ai.content_hash, ai.interpreted_at "
                    f"{JOINS}{AGE_JOIN} WHERE {where}"
                ),
                params,
            )
            .mappings()
            .first()
        )
        if row:
            properties = dict(row)
            if row["interval_id"]:
                properties["interval"] = next(
                    (unit for unit in configuration()["units"] if unit["id"] == row["interval_id"]),
                    None,
                )
    elif kind == "locality":
        row = (
            session.execute(
                text(
                    "SELECT description, coordinate_uncertainty_m, geodetic_datum, "
                    "location_is_generalized, location_is_withheld, "
                    "CASE WHEN NOT location_is_withheld THEN ST_X(geom) END longitude, "
                    "CASE WHEN NOT location_is_withheld THEN ST_Y(geom) END latitude "
                    "FROM locality WHERE id = :id"
                ),
                {"id": identifier},
            )
            .mappings()
            .one()
        )
        properties = dict(row)
        properties["geography"] = safe_geography(
            properties.pop("description"), row["location_is_withheld"]
        )
    elif kind == "taxon":
        row = (
            session.execute(
                text("SELECT source_dataset_id, parent_taxon_id, rank FROM taxon WHERE id = :id"),
                {"id": identifier},
            )
            .mappings()
            .one()
        )
        properties = dict(row)
        properties["authority"] = (
            "Published UFVP classification; not a reconciled accepted taxonomy"
        )
    elif kind == "term":
        row = (
            session.execute(
                text("SELECT field, namespace FROM context_term WHERE id = :id"), {"id": identifier}
            )
            .mappings()
            .one()
        )
        properties = dict(row)
    return EntityDetail(
        entity=neighborhood.root,
        material_count=counts[0],
        mapped_count=counts[1],
        related=neighborhood.nodes[1:],
        related_has_more=neighborhood.next_cursor is not None,
        properties=properties,
        research_note="No bibliographic references or DOI fields "
        "are supplied by this UFVP snapshot. Museum source records and dataset "
        "attribution are evidence, not research-paper relationships.",
    )
