"""Atomic, versioned materialization over eligible catalog evidence, never source writes."""

import hashlib
import json
import time
from collections import defaultdict
from typing import Any, cast
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.discovery.occurrence_browse import eligibility, query_parameters
from app.discovery.timescale import POLICY_VERSION
from app.ingestion.pbdb import POLICY_VERSION as PBDB_POLICY
from app.models import TaxonomyBrowseConcept, TaxonomyBrowseNode, TaxonomyBrowsePath
from app.taxonomy.pbdb_hierarchy import classification_from_graph
from app.taxonomy.policy import (
    QUALIFIED,
    VERSION,
    Classification,
    Term,
    complete_prefix,
    identity,
    normalized,
    pbdb_classification,
)

PROJECTION_VERSION = f"{VERSION}:{POLICY_VERSION}:{PBDB_POLICY}:pbdb-hierarchy-v1"


def load_classifications(session: Session) -> list[Classification]:
    taxa = {
        r.id: r
        for r in session.execute(
            text(
                "SELECT t.id,t.scientific_name,t.rank,c.parent_taxon_id FROM taxon t "
                "LEFT JOIN classification_link c ON c.taxon_id=t.id"
            )
        ).all()
    }
    qualifiers = session.execute(
        text(f"""
        SELECT ce.taxon_id,array_agg(DISTINCT
        sr.raw_payload->>'identificationQualifier') FILTER (WHERE
        coalesce(sr.raw_payload->>'identificationQualifier','')<>'') qualifiers
        FROM catalog_entry ce JOIN source_record sr ON sr.id=ce.source_record_id
        WHERE ce.evidence_kind='material' AND {eligibility("ufvp")} GROUP BY ce.taxon_id"""),
        query_parameters(),
    ).all()
    result = []
    for taxon_id, qualification in qualifiers:
        terms: list[Term] = []
        current: UUID | None = taxon_id
        seen: set[UUID] = set()
        conflict = False
        while current and current in taxa:
            if current in seen or len(seen) >= 32:
                conflict = True
                break
            seen.add(current)
            row = taxa[current]
            # UFVP UUIDs hash identification/classification fields; they are not
            # provider-issued canonical concept identifiers. Keep every backreference,
            # but compatible complete paths can share a reversible display grouping.
            term = Term(row.scientific_name, row.rank, str(current), current, canonical=False)
            if not terms or term.signature != terms[-1].signature:
                terms.append(term)
            current = row.parent_taxon_id
        terms.reverse()
        if not terms:
            continue
        qualified = tuple(sorted(qualification or ()))
        if QUALIFIED.search(terms[-1].name):
            qualified += ("qualified source name",)
        result.append(Classification(taxon_id, "ufvp", tuple(terms), qualified, conflict))
    rows = session.execute(
        text(f"""SELECT ce.taxon_id,t.scientific_name,t.rank,
        nr.payload->'evidence'->'latest_identification' raw FROM catalog_entry ce
        JOIN taxon t ON t.id=ce.taxon_id JOIN normalized_source_revision nr
          ON nr.source_record_id=ce.source_record_id AND nr.content_hash=ce.content_hash
          AND nr.normalization_hash=ce.normalization_hash
        WHERE ce.evidence_kind='occurrence' AND {eligibility("pbdb")}"""),
        query_parameters(),
    ).all()
    snapshot = session.scalar(
        text("SELECT snapshot_hash FROM pbdb_taxonomy_head WHERE scope='florida'")
    )
    records = (
        {
            row.selector: row.payload
            for row in session.execute(
                text(
                    "SELECT selector,payload FROM pbdb_taxonomy_record "
                    "WHERE snapshot_hash=:snapshot"
                ),
                {"snapshot": snapshot},
            ).all()
        }
        if snapshot
        else {}
    )
    for taxon_id, name, rank, raw in rows:
        result.append(
            classification_from_graph(taxon_id, name, rank, raw or {}, records, snapshot)
            if snapshot
            else pbdb_classification(taxon_id, name, rank, raw or {})
        )
    return result


def plan(
    classifications: list[Classification], scope: str = "florida"
) -> tuple[dict[UUID, dict[str, Any]], list[dict[str, Any]], dict[UUID, UUID]]:
    supported = [
        c.terms
        for c in classifications
        if c.source == "ufvp" and c.terms[0].rank == "kingdom" and not c.conflict
    ]
    placed = []
    completions: dict[tuple[tuple[str, str | None], ...], tuple[Term, ...]] = {}
    # Multiple provider concept identifiers at the identical context are unresolved
    # homonyms/variants unless they already share an explicit canonical identifier.
    keys: dict[tuple[str, tuple[tuple[str, str | None], ...]], set[str]] = defaultdict(set)
    for classification in classifications:
        terms, extended = classification.terms, False
        if classification.conflict:
            terms = classification.terms[-1:]
        elif len(terms) >= 2 and terms[0].rank != "kingdom" and not classification.rooted:
            pair = tuple(t.signature for t in terms[:2])
            if pair not in completions:
                completed, changed = complete_prefix(terms[:2], supported)
                completions[pair] = completed[:-2] if changed else ()
            prefix = completions[pair]
            terms, extended = prefix + terms, bool(prefix)
        placed.append((classification, terms, extended))
        for index, term in enumerate(terms):
            if extended and index < len(terms) - len(classification.terms):
                continue
            key = tuple(t.signature for t in terms[: index + 1])
            if term.canonical:
                keys[classification.source, key].add(term.concept)
    nodes: dict[UUID, dict[str, Any]] = {}
    concepts: dict[tuple[UUID, str, str], dict[str, Any]] = {}
    leaves = {}
    for classification, terms, extended in sorted(placed, key=lambda item: str(item[0].taxon_id)):
        signatures = tuple(t.signature for t in terms)
        parent = None
        path: list[dict[str, Any]] = []
        rooted = classification.rooted or terms[0].rank == "kingdom"
        status = (
            "unresolved"
            if classification.conflict or not terms[-1].rank
            else "partial"
            if not rooted
            else "supported"
        )
        if not rooted:
            name = (
                "Unresolved classification" if status == "unresolved" else "Partial classification"
            )
            container_id = identity(scope, ((name, "container"),))
            nodes.setdefault(
                container_id,
                {
                    "id": container_id,
                    "scope": scope,
                    "parent_id": None,
                    "name": name,
                    "rank": None,
                    "search_name": normalized(name),
                    "placement": "container",
                    "path": [],
                    "ufvp_count": 0,
                    "pbdb_count": 0,
                    "summary": {},
                },
            )
            parent = container_id
        isolation_path: list[str] = []
        for index, term in enumerate(terms):
            ambiguous = len(keys[classification.source, signatures[: index + 1]]) > 1
            last = index == len(terms) - 1
            isolation = ""
            node_status = "partial" if not rooted else "supported"
            if ambiguous or (
                last
                and (
                    classification.qualifiers
                    or classification.conflict
                    or not term.rank
                    or classification.leaf_placement == "unresolved"
                )
            ):
                isolation = classification.source + ":" + term.concept
                node_status = (
                    "qualified"
                    if last and classification.qualifiers
                    else "ambiguous"
                    if ambiguous
                    else "unresolved"
                )
            if last and classification.leaf_placement:
                node_status = classification.leaf_placement
            if isolation:
                isolation_path.append(isolation)
            identifier = identity(scope, signatures[: index + 1], "|".join(isolation_path))
            path = path + [{"id": str(identifier), "name": term.name, "rank": term.rank}]
            nodes.setdefault(
                identifier,
                {
                    "id": identifier,
                    "scope": scope,
                    "parent_id": parent,
                    "name": term.name,
                    "rank": term.rank,
                    "search_name": normalized(term.name),
                    "placement": node_status,
                    "path": path,
                    "ufvp_count": 0,
                    "pbdb_count": 0,
                    "summary": {},
                },
            )
            if node_status in {"ambiguous", "qualified", "unresolved"}:
                nodes[identifier]["summary"]["identity_hint"] = (
                    classification.source + ":" + term.concept
                )
            visual_ids = nodes[identifier]["summary"].setdefault("visual_ids", [])
            visual_terms = (
                terms[: index + 1]
                if classification.source == "ufvp"
                else terms[: min(index + 1, len(terms) - len(classification.terms))]
                if extended
                else ()
            )
            for supplied in visual_terms:
                if supplied.taxon_id and str(supplied.taxon_id) not in visual_ids:
                    visual_ids.append(str(supplied.taxon_id))
            # Borrowed upper context is display placement, not PBDB's own assertion.
            if not extended or index >= len(terms) - len(classification.terms):
                concept_key = term.concept + (
                    ":taxon:" + str(term.taxon_id) if term.taxon_id else ""
                )
                concepts[identifier, classification.source, concept_key] = {
                    "node_id": identifier,
                    "source": classification.source,
                    "concept_key": concept_key,
                    "taxon_id": term.taxon_id,
                    "details": {
                        "name": term.name,
                        "rank": term.rank,
                        "qualifiers": list(classification.qualifiers) if last else [],
                        "upper_path_placement": extended,
                        "supplied_path": [
                            {"name": t.name, "rank": t.rank} for t in classification.terms
                        ],
                        "classification_conflict": classification.conflict,
                        "hierarchy": term.provenance,
                    },
                }
            parent = identifier
        leaves[classification.taxon_id] = identifier
    return nodes, list(concepts.values()), leaves


def rebuild(session: Session, scope: str = "florida") -> dict[str, Any]:
    if scope != "florida":
        raise ValueError("Only retained Florida evidence is currently supported")
    started = time.perf_counter()
    with session.begin_nested():
        session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
        session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
        revision = session.scalar(
            text("SELECT input_revision FROM browse_projection_state WHERE id=1 FOR UPDATE")
        )
        session.execute(text("SET LOCAL jit=off"))
        nodes, concepts, leaves = plan(load_classifications(session), scope)
        for table in (
            "taxonomy_browse_member",
            "taxonomy_browse_path",
            "taxonomy_browse_concept",
            "taxonomy_browse_node",
        ):
            session.execute(text(f"DELETE FROM {table}"))
        for model, rows in (
            (TaxonomyBrowseNode, list(nodes.values())),
            (TaxonomyBrowseConcept, concepts),
        ):
            for offset in range(0, len(rows), 1000):
                session.execute(insert(model), rows[offset : offset + 1000])
        closure = []
        children: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for child in nodes.values():
            if child["parent_id"]:
                children[child["parent_id"]].append(child)
        for node in nodes.values():
            current, depth = node["id"], 0
            while current is not None:
                closure.append({"ancestor_id": current, "node_id": node["id"], "depth": depth})
                current = nodes[current]["parent_id"]
                depth += 1
        for offset in range(0, len(closure), 1000):
            session.execute(insert(TaxonomyBrowsePath), closure[offset : offset + 1000])
        session.execute(text("DROP TABLE IF EXISTS pg_temp.taxonomy_leaf_map"))
        session.execute(
            text(
                "CREATE TEMP TABLE taxonomy_leaf_map(taxon_id uuid PRIMARY KEY,node_id uuid) "
                "ON COMMIT DROP"
            )
        )
        from sqlalchemy import Column, MetaData, Table
        from sqlalchemy.dialects.postgresql import UUID as SQLUUID

        mapping = Table(
            "taxonomy_leaf_map", MetaData(), Column("taxon_id", SQLUUID), Column("node_id", SQLUUID)
        )
        pairs = [{"taxon_id": taxon, "node_id": node} for taxon, node in leaves.items()]
        for offset in range(0, len(pairs), 1000):
            session.execute(insert(mapping), pairs[offset : offset + 1000])
        session.execute(
            text(f"""INSERT INTO taxonomy_browse_member SELECT ce.occurrence_id,m.node_id,
          CASE WHEN ce.evidence_kind='material' THEN 'ufvp' ELSE 'pbdb' END
          FROM catalog_entry ce JOIN taxonomy_leaf_map m ON m.taxon_id=ce.taxon_id
          WHERE {eligibility("all")}"""),
            query_parameters(),
        )
        session.execute(text("ANALYZE taxonomy_browse_member"))
        session.execute(text("ANALYZE taxonomy_browse_path"))
        aggregates = (
            session.execute(
                text("""SELECT p.ancestor_id id,coalesce(m.source,'all') source,
          count(*) evidence_count,count(*) FILTER (WHERE p.depth=0) direct_count,
          count(*) FILTER (WHERE m.source='ufvp') ufvp_material_count,
          count(*) FILTER (WHERE m.source='pbdb') pbdb_occurrence_count,
          count(*) FILTER (WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL)
known_age_count,
          count(*) FILTER (WHERE ce.older_ma IS NULL OR ce.younger_ma IS NULL)
unknown_age_count,
          max(ce.older_ma) FILTER (WHERE ce.younger_ma IS NOT NULL) older_ma,
          min(ce.younger_ma) FILTER (WHERE ce.older_ma IS NOT NULL) younger_ma,
          count(*) FILTER (WHERE ce.age_basis='derived-interval') derived_count,
          count(*) FILTER (WHERE ce.age_basis IN ('provider-envelope','source-numeric'))
source_numeric_count,
          max(ce.older_ma) FILTER (WHERE ce.age_basis='derived-interval') derived_older_ma,
          min(ce.younger_ma) FILTER (WHERE ce.age_basis='derived-interval')
derived_younger_ma,
          max(ce.older_ma) FILTER (WHERE ce.age_basis IN
('provider-envelope','source-numeric')) source_older_ma,
          min(ce.younger_ma) FILTER (WHERE ce.age_basis IN
('provider-envelope','source-numeric')) source_younger_ma
          FROM taxonomy_browse_member m JOIN taxonomy_browse_path p ON p.node_id=m.node_id
          JOIN catalog_entry ce ON ce.occurrence_id=m.occurrence_id
          GROUP BY GROUPING SETS ((p.ancestor_id,m.source),(p.ancestor_id))""")
            )
            .mappings()
            .all()
        )
        for row in aggregates:
            payload = {
                k: float(v) if k.endswith("_ma") and v is not None else v
                for k, v in row.items()
                if k not in ("id", "source")
            }
            nodes[row["id"]]["summary"][row["source"]] = payload
        for node in nodes.values():
            for source in ("all", "ufvp", "pbdb"):
                payload = node["summary"].get(source)
                if payload:
                    payload["child_count"] = sum(
                        1 for child in children[node["id"]] if source in child["summary"]
                    )
            node["ufvp_count"] = node["summary"].get("ufvp", {}).get("evidence_count", 0)
            node["pbdb_count"] = node["summary"].get("pbdb", {}).get("evidence_count", 0)
        # Bulk update avoids one SQL round trip per browse node.
        from sqlalchemy import bindparam, update

        updates = [
            {
                "key": n["id"],
                "counts_ufvp": n["ufvp_count"],
                "counts_pbdb": n["pbdb_count"],
                "payload": n["summary"],
            }
            for n in nodes.values()
        ]
        node_table = cast(Table, TaxonomyBrowseNode.__table__)
        statement = (
            update(node_table)
            .where(node_table.c.id == bindparam("key"))
            .values(
                ufvp_count=bindparam("counts_ufvp"),
                pbdb_count=bindparam("counts_pbdb"),
                summary=bindparam("payload"),
            )
        )
        session.connection().execute(statement, updates)
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    PROJECTION_VERSION,
                    revision,
                    session.scalar(
                        text("SELECT snapshot_hash FROM pbdb_taxonomy_head WHERE scope=:scope"),
                        {"scope": scope},
                    ),
                    sorted((str(k), str(v)) for k, v in leaves.items()),
                ]
            ).encode()
        ).hexdigest()
        session.execute(
            text("""
        INSERT INTO
        taxonomy_browse_state(scope,built_revision,projection_version,input_hash)
          VALUES (:scope,:revision,:version,:hash) ON CONFLICT(scope) DO UPDATE SET
built_revision=excluded.built_revision,projection_version=excluded.projection_version,
          input_hash=excluded.input_hash,built_at=now()"""),
            {
                "scope": scope,
                "revision": revision,
                "version": PROJECTION_VERSION,
                "hash": fingerprint,
            },
        )
        session.execute(text("ANALYZE taxonomy_browse_node"))
        members = session.scalar(text("SELECT count(*) FROM taxonomy_browse_member"))
        expected = session.scalar(
            text(f"SELECT count(*) FROM catalog_entry ce WHERE {eligibility('all')}"),
            query_parameters(),
        )
        if members != expected:
            raise ValueError("Incomplete taxonomy evidence membership")
    return {
        "version": PROJECTION_VERSION,
        "scope": scope,
        "nodes": len(nodes),
        "concepts": len(concepts),
        "members": members,
        "paths": len(closure),
        "input_hash": fingerprint,
        "seconds": round(time.perf_counter() - started, 3),
    }


def main() -> None:
    from app.config import Settings
    from app.db import create_db_engine

    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session:
            result = rebuild(session)
            session.commit()
            print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
