"""Atomically rebuild discovery from canonical UFVP records; retain interpretation history."""

import json
import time
from typing import Any, cast

from sqlalchemy import Table, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine
from app.discovery.classification import LINK_SQL
from app.discovery.timescale import NALMA, POLICY_VERSION, interpret, interval_key, intervals
from app.ingestion.import_ufvp import CANONICAL_DATASET_ID, upsert
from app.models import GeologicalInterval

RANKS = ("kingdom", "phylum", "class", "order", "family", "genus")
TERM_FIELDS = (
    "earliestEraOrLowestErathem",
    "earliestPeriodOrLowestSystem",
    "earliestEpochOrLowestSeries",
    "earliestAgeOrLowestStage",
    "lowestBiostratigraphicZone",
    "group",
    "formation",
    "member",
)


def rebuild(session: Session) -> dict[str, Any]:
    """Readers see the previous committed projection until the entire replacement commits."""
    started = time.perf_counter()
    session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
    session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
    session.execute(text("DROP TABLE IF EXISTS pg_temp.discovery_work"))
    session.execute(text("DROP TABLE IF EXISTS pg_temp.age_rules"))
    # Parent-first insertion satisfies immediate foreign keys without disabling constraints.
    remaining = dict(intervals())
    inserted: set[str] = set()
    while remaining:
        ready = [
            unit for unit in remaining.values() if not unit["parent"] or unit["parent"] in inserted
        ]
        if not ready:
            raise ValueError("Cyclic timescale hierarchy")
        upsert(
            session,
            cast(Table, GeologicalInterval.__table__),
            [
                {
                    "id": interval_key(unit["id"]),
                    "version": "2026-06",
                    "name": unit["name"],
                    "rank": unit["rank"],
                    "parent_id": interval_key(unit["parent"]) if unit["parent"] else None,
                    "older_ma": unit["older_ma"],
                    "younger_ma": unit["younger_ma"],
                    "color": unit["color"],
                    "reference": unit,
                }
                for unit in ready
            ],
            immutable=True,
        )
        for unit in ready:
            inserted.add(unit["id"])
            del remaining[unit["id"]]
    session.execute(
        text("""
        CREATE TEMP TABLE discovery_work ON COMMIT DROP AS
        SELECT o.id occurrence_id, o.taxon_id, o.specimen_id, e.locality_id,
               s.collection_id, c.institution_id, r.id source_record_id,
               r.content_hash, r.raw_payload raw, e.older_ma source_older,
               e.younger_ma source_younger, t.scientific_name,
               concat_ws(' / ', s.collection_code, s.catalog_number) label,
               concat_ws(' ', s.collection_code, s.catalog_number, r.source_record_id,
                   regexp_replace(lower(concat(s.collection_code,s.catalog_number)),
                                  '[^[:alnum:]]', '', 'g'),
                   s.occurrence_identifier, s.material_entity_identifier,
                   s.other_identifiers::text, t.scientific_name, l.name,
                   c.name, c.code, i.name, i.code,
                   r.raw_payload->>'kingdom', r.raw_payload->>'phylum',
                   r.raw_payload->>'class', r.raw_payload->>'order',
                   r.raw_payload->>'family', r.raw_payload->>'genus',
                   r.raw_payload->>'earliestEraOrLowestErathem',
                   r.raw_payload->>'earliestPeriodOrLowestSystem',
                   r.raw_payload->>'earliestEpochOrLowestSeries',
                   r.raw_payload->>'lowestBiostratigraphicZone',
                   r.raw_payload->>'group', r.raw_payload->>'formation',
                   r.raw_payload->>'member') search_text
        FROM source_record r JOIN occurrence_evidence oe ON oe.source_record_id = r.id
        JOIN occurrence o ON o.id = oe.occurrence_id JOIN taxon t ON t.id = o.taxon_id
        JOIN collection_event e ON e.id = o.collection_event_id
        JOIN specimen s ON s.id = o.specimen_id LEFT JOIN locality l ON l.id = e.locality_id
        LEFT JOIN collection c ON c.id = s.collection_id
        LEFT JOIN institution i ON i.id = c.institution_id
        JOIN source_dataset d ON d.id = r.source_dataset_id
        WHERE r.source_dataset_id = :dataset AND r.is_current AND NOT d.is_synthetic
        """),
        {"dataset": CANONICAL_DATASET_ID},
    )
    # Few distinct label combinations, so interpret each once, not 462k Python objects.
    combinations = (
        session.execute(
            text("""
        SELECT DISTINCT jsonb_build_object(
            'earliestAgeOrLowestStage', raw->>'earliestAgeOrLowestStage',
            'earliestEpochOrLowestSeries', raw->>'earliestEpochOrLowestSeries',
            'earliestPeriodOrLowestSystem', raw->>'earliestPeriodOrLowestSystem',
            'earliestEraOrLowestErathem', raw->>'earliestEraOrLowestErathem') labels
        FROM discovery_work
        """)
        )
        .scalars()
        .all()
    )
    session.execute(
        text("""
        CREATE TEMP TABLE age_rules (labels jsonb PRIMARY KEY, interpretation jsonb)
        ON COMMIT DROP
        """)
    )
    if combinations:
        session.execute(
            text(
                "INSERT INTO age_rules VALUES (CAST(:labels AS jsonb), "
                "CAST(:interpretation AS jsonb))"
            ),
            [
                {
                    "labels": json.dumps(labels),
                    "interpretation": json.dumps(interpret(labels)),
                }
                for labels in combinations
            ],
        )
    session.execute(
        text("""
        INSERT INTO age_interpretation
            (source_record_id, content_hash, policy_version, interval_id, source_field,
             source_label, status, rule, older_ma, younger_ma)
        SELECT w.source_record_id, w.content_hash, :policy, a.interpretation->>'interval_id',
            a.interpretation->>'source_field', a.interpretation->>'source_label',
            a.interpretation->>'status', a.interpretation->>'rule',
            (a.interpretation->>'older_ma')::numeric,
            (a.interpretation->>'younger_ma')::numeric
        FROM discovery_work w JOIN age_rules a ON a.labels = jsonb_build_object(
            'earliestAgeOrLowestStage', w.raw->>'earliestAgeOrLowestStage',
            'earliestEpochOrLowestSeries', w.raw->>'earliestEpochOrLowestSeries',
            'earliestPeriodOrLowestSystem', w.raw->>'earliestPeriodOrLowestSystem',
            'earliestEraOrLowestErathem', w.raw->>'earliestEraOrLowestErathem')
        ON CONFLICT DO NOTHING
        """),
        {"policy": POLICY_VERSION},
    )
    session.execute(text("DELETE FROM catalog_term"))
    session.execute(text("DELETE FROM catalog_entry"))
    session.execute(
        text("""
        INSERT INTO catalog_entry (occurrence_id, specimen_id, taxon_id, locality_id,
            collection_id, institution_id, source_record_id, content_hash, policy_version,
            label, scientific_name, search_text, older_ma, younger_ma, age_basis)
        SELECT w.occurrence_id, w.specimen_id, w.taxon_id, w.locality_id, w.collection_id,
            w.institution_id, w.source_record_id, w.content_hash, :policy,
            w.label, w.scientific_name, lower(w.search_text),
            CASE WHEN w.source_older IS NOT NULL AND w.source_younger IS NOT NULL
                 THEN w.source_older ELSE a.older_ma END,
            CASE WHEN w.source_older IS NOT NULL AND w.source_younger IS NOT NULL
                 THEN w.source_younger ELSE a.younger_ma END,
            CASE WHEN w.source_older IS NOT NULL AND w.source_younger IS NOT NULL
                 THEN 'source-numeric' WHEN a.status = 'mapped' THEN 'derived-interval'
                 ELSE a.status END
        FROM discovery_work w JOIN age_interpretation a
        ON a.source_record_id = w.source_record_id AND a.content_hash = w.content_hash
        AND a.policy_version = :policy
        """),
        {"policy": POLICY_VERSION},
    )
    session.execute(
        text("DELETE FROM taxon_path WHERE taxon_id IN (SELECT taxon_id FROM discovery_work)")
    )
    session.execute(
        text("""
        INSERT INTO taxon_path SELECT DISTINCT taxon_id, taxon_id FROM discovery_work
        ON CONFLICT DO NOTHING
        """)
    )
    previous: str | None = None
    for rank in RANKS:
        # Prefix identity retains conflicting source placements rather than merging names.
        prefix = " || '|' || ".join(
            f"coalesce(raw->>'{field}', '')" for field in RANKS[: RANKS.index(rank) + 1]
        )
        identity = f"discovery_uuid(:dataset || '|rank:{rank}|' || {prefix})"
        parent = "NULL::uuid"
        if previous:
            previous_prefix = " || '|' || ".join(
                f"coalesce(raw->>'{field}', '')" for field in RANKS[: RANKS.index(rank)]
            )
            parent = (
                f"CASE WHEN coalesce(raw->>'{previous}', '') <> '' THEN "
                f"discovery_uuid(:dataset || '|rank:{previous}|' || {previous_prefix}) END"
            )
        session.execute(
            text(f"""
            INSERT INTO taxon (id, scientific_name, rank, source_dataset_id, parent_taxon_id)
            SELECT DISTINCT {identity}, raw->>'{rank}', :rank, CAST(:dataset AS uuid), {parent}
            FROM discovery_work WHERE coalesce(raw->>'{rank}', '') <> ''
            ON CONFLICT (id) DO UPDATE SET parent_taxon_id = EXCLUDED.parent_taxon_id
            """),
            {"dataset": str(CANONICAL_DATASET_ID), "rank": rank},
        )
        session.execute(
            text(f"""
            INSERT INTO taxon_path SELECT DISTINCT taxon_id, {identity} FROM discovery_work
            WHERE coalesce(raw->>'{rank}', '') <> '' ON CONFLICT DO NOTHING
            """),
            {"dataset": str(CANONICAL_DATASET_ID)},
        )
        previous = rank
    # Rank is inferred ONLY from explicit classification/epithet fields agreeing with
    # the source identification. It is not an accepted-name or taxonomic reconciliation.
    session.execute(
        text("""
        UPDATE taxon t SET source_dataset_id = CAST(:dataset AS uuid), rank = CASE
            WHEN coalesce(w.raw->>'specificEpithet','') <> ''
              AND coalesce(w.raw->>'genus','') <> ''
              AND w.scientific_name LIKE (w.raw->>'genus') || ' %'
              AND position(w.raw->>'specificEpithet' in w.scientific_name) > 0 THEN 'species'
            WHEN w.scientific_name = w.raw->>'genus' THEN 'genus'
            WHEN w.scientific_name = w.raw->>'family' THEN 'family'
            WHEN w.scientific_name = w.raw->>'order' THEN 'order'
            WHEN w.scientific_name = w.raw->>'class' THEN 'class'
            ELSE NULL END
        FROM (SELECT DISTINCT ON (taxon_id) taxon_id, scientific_name, raw
              FROM discovery_work ORDER BY taxon_id) w WHERE t.id = w.taxon_id
        """),
        {"dataset": str(CANONICAL_DATASET_ID)},
    )
    # Rebuild paths for current source assertions: avoid stale classification after revisions.
    # Their stable taxon IDs already include complete classification; each assertion is immutable.
    for field in TERM_FIELDS:
        namespace = (
            "stratigraphy" if field in {"group", "formation", "member"} else "source-geology"
        )
        zone = field == "lowestBiostratigraphicZone"
        session.execute(
            text("""
            INSERT INTO context_term (id, source_dataset_id, field, namespace, label, search_text)
            SELECT DISTINCT discovery_uuid(:dataset || '|term:' || :field || '|' || (raw->>:field)),
                CAST(:dataset AS uuid), :field,
                CASE WHEN :zone AND raw->>:field = ANY(:nalma) THEN 'NALMA'
                     WHEN :zone THEN 'source-biochronology' ELSE :namespace END,
                raw->>:field, lower(raw->>:field)
            FROM discovery_work WHERE coalesce(raw->>:field, '') <> '' ON CONFLICT DO NOTHING
            """),
            {
                "dataset": str(CANONICAL_DATASET_ID),
                "field": field,
                "zone": zone,
                "nalma": list(NALMA),
                "namespace": namespace,
            },
        )
        session.execute(
            text("""
            INSERT INTO catalog_term SELECT occurrence_id,
                discovery_uuid(:dataset || '|term:' || :field || '|' || (raw->>:field))
            FROM discovery_work WHERE coalesce(raw->>:field, '') <> '' ON CONFLICT DO NOTHING
            """),
            {"dataset": str(CANONICAL_DATASET_ID), "field": field},
        )
    session.execute(text("DELETE FROM classification_link"))
    session.execute(text("INSERT INTO classification_link " + LINK_SQL))
    session.execute(text("ANALYZE classification_link"))
    session.execute(text("ANALYZE catalog_entry"))
    session.execute(text("ANALYZE taxon_path"))
    session.execute(text("ANALYZE catalog_term"))
    from app.discovery.browse import rebuild as rebuild_browse

    browse_result = rebuild_browse(session)
    return {
        "records": session.scalar(text("SELECT count(*) FROM catalog_entry")),
        "derived_records": session.scalar(
            text("SELECT count(*) FROM catalog_entry WHERE age_basis = 'derived-interval'")
        ),
        "policy_version": POLICY_VERSION,
        "browse": browse_result,
        "seconds": round(time.perf_counter() - started, 3),
    }


def main() -> None:
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
