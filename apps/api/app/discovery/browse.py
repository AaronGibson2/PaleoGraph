"""Versioned disposable browse summaries within the discovery transaction lifecycle.

Browse projections accelerate reads; they do not define scientific truth.
"""

import json
import time
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine
from app.discovery.queries import AGE_JOIN, JOINS, PUBLIC
from app.discovery.schemas import ContextQuery
from app.discovery.summary_sql import COUNTS, lineage_nodes

VERSION = "browse-v1"
FRESH = """EXISTS (SELECT 1 FROM browse_projection_state WHERE id=1
    AND input_revision=built_revision AND projection_version=:browse_version)"""


def global_context(
    query: ContextQuery, *, locality: UUID | None = None, taxon: UUID | None = None
) -> bool:
    """Only the complete represented context; pagination does not change membership."""
    return (
        query.locality_id in (None, locality)
        and query.taxon_id in (None, taxon)
        and not query.q.strip()
        and all(
            getattr(query, field) is None
            for field in (
                "collection_id",
                "institution_id",
                "term_id",
                "older_ma",
                "younger_ma",
                "at_lon",
                "at_lat",
                "west",
                "east",
                "south",
                "north",
            )
        )
    )


def ready(session: Session) -> bool:
    # Each actual projected read also checks FRESH in its own SQL snapshot. A
    # generation check alone must never authorize a later unchecked payload read.
    return bool(
        session.scalar(
            text("""SELECT id FROM browse_projection_state
        WHERE id=1 AND input_revision=built_revision AND projection_version=:version"""),
            {"version": VERSION},
        )
    )


def revision(session: Session) -> str:
    row = (
        session.execute(
            text("""SELECT input_revision,built_revision,projection_version
        FROM browse_projection_state WHERE id=1""")
        )
        .mappings()
        .one()
    )
    state = (
        VERSION
        if row["built_revision"] == row["input_revision"] and (row["projection_version"] == VERSION)
        else "live"
    )
    return f"{row['input_revision']}:{state}"


def locality_payload(
    session: Session, identifier: UUID, query: ContextQuery
) -> dict[str, Any] | None:
    if not global_context(query, locality=identifier):
        return None
    return cast(
        dict[str, Any] | None,
        session.scalar(
            text(f"SELECT payload FROM locality_browse_summary WHERE locality_id=:id AND {FRESH}"),
            {"id": identifier, "browse_version": VERSION},
        ),
    )


def rebuild(session: Session) -> dict[str, Any]:
    """Savepoint protects replacement on failure; caller commits successful publication."""
    with session.begin_nested():
        return _rebuild(session)


def _rebuild(session: Session) -> dict[str, Any]:
    started = time.perf_counter()
    # Same ordering as ingestion/discovery; session-held import locks are reentrant.
    session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
    session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
    input_revision = session.scalar(
        text("""SELECT input_revision FROM browse_projection_state
        WHERE id=1 FOR UPDATE""")
    )
    session.execute(text("SET LOCAL jit=off"))
    session.execute(text("DROP TABLE IF EXISTS pg_temp.browse_material"))
    session.execute(text("DROP TABLE IF EXISTS pg_temp.browse_locality_taxon"))
    session.execute(
        text(f"""CREATE TEMP TABLE browse_material ON COMMIT DROP AS
        SELECT ce.occurrence_id,ce.specimen_id,ce.taxon_id,ce.locality_id,
            ce.collection_id,ce.institution_id,ce.source_record_id,ce.content_hash,
            ce.policy_version,ce.older_ma,ce.younger_ma,ce.age_basis {JOINS} WHERE {PUBLIC}""")
    )
    session.execute(text("CREATE INDEX ON browse_material (locality_id)"))
    session.execute(text("ANALYZE browse_material"))
    session.execute(
        text("""CREATE TEMP TABLE browse_locality_taxon ON COMMIT DROP AS
        SELECT DISTINCT locality_id,taxon_id FROM browse_material WHERE locality_id IS NOT NULL""")
    )
    session.execute(text("CREATE UNIQUE INDEX ON browse_locality_taxon (locality_id,taxon_id)"))
    session.execute(text("CREATE INDEX ON browse_locality_taxon (taxon_id,locality_id)"))
    session.execute(text("ANALYZE browse_locality_taxon"))

    session.execute(text("DELETE FROM locality_browse_summary"))
    session.execute(
        text(f"""INSERT INTO locality_browse_summary (locality_id,payload)
        WITH summary AS (
            SELECT ce.locality_id,{COUNTS},count(DISTINCT ce.collection_id) collection_count,
                count(DISTINCT ce.institution_id) institution_count
            FROM browse_material ce WHERE ce.locality_id IS NOT NULL GROUP BY ce.locality_id
        ), terms AS (
            SELECT ce.locality_id,t.field,t.namespace,t.label,count(*) assertion_count
            FROM browse_material ce JOIN catalog_term ct ON ct.occurrence_id=ce.occurrence_id
            JOIN context_term t ON t.id=ct.term_id GROUP BY ce.locality_id,t.id
        ), term_arrays AS (
            SELECT locality_id,jsonb_agg(to_jsonb(terms)-'locality_id'
                ORDER BY namespace,field,label) items FROM terms GROUP BY locality_id
        ), intervals AS (
            SELECT ce.locality_id,ai.interval_id,ai.source_label,ce.age_basis,
                ce.older_ma,ce.younger_ma,
                count(*) assertion_count FROM browse_material ce{AGE_JOIN}
            GROUP BY ce.locality_id,ai.interval_id,ai.source_label,ce.age_basis,
                ce.older_ma,ce.younger_ma
        ), interval_arrays AS (
            SELECT locality_id,jsonb_agg(to_jsonb(intervals)-'locality_id'
                ORDER BY older_ma DESC NULLS LAST,source_label) items
            FROM intervals GROUP BY locality_id
        ), custody AS (
            SELECT ce.locality_id,c.id collection_id,coalesce(c.name,c.code) collection,
                i.name institution,count(*) assertion_count FROM browse_material ce
            LEFT JOIN collection c ON c.id=ce.collection_id
            LEFT JOIN institution i ON i.id=ce.institution_id GROUP BY ce.locality_id,c.id,i.name
        ), custody_arrays AS (
            SELECT locality_id,jsonb_agg(to_jsonb(custody)-'locality_id'
                ORDER BY collection,institution) items FROM custody GROUP BY locality_id
        ) SELECT s.locality_id,(to_jsonb(s)-'locality_id') || jsonb_build_object(
            'source_terms',coalesce(t.items,'[]'::jsonb),
            'interpreted_intervals',coalesce(a.items,'[]'::jsonb),
            'custody',coalesce(c.items,'[]'::jsonb),
            'related_localities',coalesce((
                SELECT jsonb_agg(to_jsonb(related) ORDER BY id) FROM (
                    SELECT 'locality' kind,l.id,l.name label,'Shared source identification' subtitle
                    FROM locality l WHERE l.id<>s.locality_id AND EXISTS (
                        SELECT 1 FROM browse_locality_taxon other WHERE other.locality_id=l.id
                        AND EXISTS (SELECT 1 FROM browse_locality_taxon own
                            WHERE own.locality_id=s.locality_id AND own.taxon_id=other.taxon_id)
                    ) ORDER BY l.id LIMIT 12
                ) related
            ),'[]'::jsonb))
        FROM summary s LEFT JOIN term_arrays t ON t.locality_id=s.locality_id
        LEFT JOIN interval_arrays a ON a.locality_id=s.locality_id
        LEFT JOIN custody_arrays c ON c.locality_id=s.locality_id
    """)
    )
    session.execute(text("DELETE FROM taxon_browse_summary"))
    nodes = lineage_nodes(
        "SELECT ce.taxon_id,ce.specimen_id,ce.older_ma,ce.younger_ma FROM browse_material ce"
    )
    session.execute(
        text(f"""INSERT INTO taxon_browse_summary
        (id,assertion_count,specimen_count,source_taxon_count,older_ma,younger_ma,
         known_age_count,unknown_age_count) WITH {nodes} SELECT * FROM nodes""")
    )
    invalid = session.scalar(
        text("""SELECT EXISTS (SELECT 1 FROM taxon_browse_summary
        WHERE specimen_count>assertion_count OR specimen_count<0
        OR known_age_count+unknown_age_count<>assertion_count)""")
    )
    expected = session.scalar(
        text("""SELECT count(*) FROM browse_material
        WHERE locality_id IS NOT NULL""")
    )
    actual = session.scalar(
        text("""SELECT coalesce(sum((payload->>'assertion_count')::bigint),0)
        FROM locality_browse_summary""")
    )
    if invalid or expected != actual:
        raise ValueError("Browse projection completeness/count validation failed")
    session.execute(
        text("""UPDATE browse_projection_state SET built_revision=:revision,
        projection_version=:version,built_at=now() WHERE id=1"""),
        {"revision": input_revision, "version": VERSION},
    )
    session.execute(text("ANALYZE locality_browse_summary"))
    session.execute(text("ANALYZE taxon_browse_summary"))
    return {
        "projection_version": VERSION,
        "input_revision": input_revision,
        "localities": session.scalar(text("SELECT count(*) FROM locality_browse_summary")),
        "taxa": session.scalar(text("SELECT count(*) FROM taxon_browse_summary")),
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
