"""Set-based large Design C invalidity refresh with current statistics.

Revision ID: 0014_design_c_native_cache
Revises: 0013_design_c
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_design_c_native_cache"
down_revision: str | Sequence[str] | None = "0013_design_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The original 0013 predicate is retained for small changes and downgrade.
SMALL_REFRESH = """
      INSERT INTO source_normalization_invalid
      SELECT n.source_record_id,n.content_hash,n.normalization_hash
      FROM normalized_source_revision n WHERE n.normalization_key=ANY(keys)
        AND (NOT EXISTS(SELECT 1 FROM source_record own
          JOIN source_dataset ds ON ds.id=own.source_dataset_id
          JOIN source_normalization_current nc ON nc.source_record_id=own.id
          WHERE own.id=n.source_record_id AND own.is_current AND NOT ds.is_synthetic
            AND own.content_hash=n.content_hash AND nc.content_hash=n.content_hash
            AND nc.normalization_hash=n.normalization_hash)
        OR EXISTS (SELECT 1 FROM source_record_dependency d
          JOIN source_record s ON s.id=d.dependency_record_id
          JOIN source_dataset ds ON ds.id=s.source_dataset_id
          WHERE n.frame_format='full' AND d.source_record_id=n.source_record_id
            AND d.content_hash=n.content_hash AND d.normalization_hash=n.normalization_hash
            AND (NOT s.is_current OR ds.is_synthetic
              OR s.content_hash IS DISTINCT FROM d.dependency_content_hash))
        OR EXISTS(SELECT 1 FROM source_proof_edge e
          JOIN source_record_revision r USING(revision_key)
          JOIN source_record s ON s.id=r.source_record_id
          JOIN source_dataset ds ON ds.id=s.source_dataset_id
          WHERE n.frame_format='compact' AND e.normalization_key=n.normalization_key
            AND (NOT s.is_current OR ds.is_synthetic
              OR s.content_hash IS DISTINCT FROM r.content_hash)))
      ON CONFLICT DO NOTHING;
"""
DELETE_REFRESH = """
      DELETE FROM source_normalization_invalid i USING normalized_source_revision n
        WHERE n.normalization_key=ANY(keys) AND i.source_record_id=n.source_record_id
          AND i.content_hash=n.content_hash AND i.normalization_hash=n.normalization_hash;
"""


def upgrade() -> None:
    op.execute(
        """CREATE OR REPLACE FUNCTION refresh_source_proof_invalid(keys bigint[])
      RETURNS void LANGUAGE plpgsql SET plan_cache_mode='force_custom_plan' AS $$ BEGIN
      IF coalesce(cardinality(keys),0)=0 THEN RETURN; END IF;
      IF cardinality(keys)>=4096 THEN
        -- Fresh COPY/publication tables otherwise retain empty-table estimates.
        -- ANALYZE sees this transaction's rows, including AFTER STATEMENT inserts.
        ANALYZE source_record;
        ANALYZE source_record_revision;
        ANALYZE normalized_source_revision;
        ANALYZE source_normalization_current;
        ANALYZE source_record_dependency;
        ANALYZE source_proof_edge;
      END IF;
    """
        + DELETE_REFRESH
        + """
      IF cardinality(keys)<4096 THEN
    """
        + SMALL_REFRESH
        + """
      ELSE
        WITH chosen AS MATERIALIZED (
          SELECT n.normalization_key,n.source_record_id,n.content_hash,
            n.normalization_hash,n.frame_format FROM normalized_source_revision n
          WHERE n.normalization_key=ANY(keys)), bad AS (
          SELECT n.normalization_key FROM chosen n
            JOIN source_record own ON own.id=n.source_record_id
            JOIN source_dataset ds ON ds.id=own.source_dataset_id
            LEFT JOIN source_normalization_current nc ON nc.source_record_id=own.id
          WHERE NOT own.is_current OR ds.is_synthetic OR own.content_hash<>n.content_hash
            OR nc.source_record_id IS NULL OR nc.content_hash<>n.content_hash
            OR nc.normalization_hash<>n.normalization_hash
          UNION
          SELECT n.normalization_key FROM chosen n JOIN source_record_dependency d
            ON d.source_record_id=n.source_record_id AND d.content_hash=n.content_hash
              AND d.normalization_hash=n.normalization_hash
            JOIN source_record dep ON dep.id=d.dependency_record_id
            JOIN source_dataset ds ON ds.id=dep.source_dataset_id
          WHERE n.frame_format='full' AND (NOT dep.is_current OR ds.is_synthetic
            OR dep.content_hash IS DISTINCT FROM d.dependency_content_hash)
          UNION
          SELECT n.normalization_key FROM chosen n JOIN source_proof_edge e USING(normalization_key)
            JOIN source_record_revision r USING(revision_key)
            JOIN source_record dep ON dep.id=r.source_record_id
            JOIN source_dataset ds ON ds.id=dep.source_dataset_id
          WHERE n.frame_format='compact' AND (NOT dep.is_current OR ds.is_synthetic
            OR dep.content_hash IS DISTINCT FROM r.content_hash))
        INSERT INTO source_normalization_invalid
        SELECT n.source_record_id,n.content_hash,n.normalization_hash
          FROM chosen n JOIN bad USING(normalization_key) ON CONFLICT DO NOTHING;
      END IF;
    END $$"""
    )


def downgrade() -> None:
    op.execute(
        """CREATE OR REPLACE FUNCTION refresh_source_proof_invalid(keys bigint[])
      RETURNS void LANGUAGE plpgsql AS $$ BEGIN
    """
        + DELETE_REFRESH
        + SMALL_REFRESH
        + "END $$"
    )
    op.execute("ALTER FUNCTION refresh_source_proof_invalid(bigint[]) RESET plan_cache_mode")
