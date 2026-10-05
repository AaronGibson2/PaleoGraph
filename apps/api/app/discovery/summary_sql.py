"""Shared exact aggregate derivation for live contexts and disposable summaries."""

COUNTS = """
    count(*) assertion_count, count(DISTINCT ce.specimen_id) specimen_count,
    count(DISTINCT ce.taxon_id) source_taxon_count,
    max(ce.older_ma) FILTER (WHERE ce.younger_ma IS NOT NULL) older_ma,
    min(ce.younger_ma) FILTER (WHERE ce.older_ma IS NOT NULL) younger_ma,
    count(*) FILTER (WHERE ce.older_ma IS NOT NULL AND ce.younger_ma IS NOT NULL) known_age_count,
    count(*) FILTER (WHERE ce.older_ma IS NULL OR ce.younger_ma IS NULL) unknown_age_count
"""


def lineage_nodes(material_sql: str) -> str:
    """CTEs through nodes, including exact cross-identification specimen correction."""
    return f"""material AS MATERIALIZED ({material_sql}), leaves AS (
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
    )"""
