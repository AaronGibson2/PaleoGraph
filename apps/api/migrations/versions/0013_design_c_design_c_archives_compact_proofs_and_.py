"""Design C archives compact proofs and staged publication

Revision ID: 0013_design_c
Revises: 0012_product_browse
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_design_c"
down_revision: str | Sequence[str] | None = "0012_product_browse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def install_design_c_functions() -> None:
    op.execute("""CREATE VIEW source_dependency_frame AS
      SELECT d.* FROM source_record_dependency d
        JOIN normalized_source_revision n USING(source_record_id,content_hash,normalization_hash)
        WHERE n.frame_format='full'
      UNION ALL
      SELECT n.source_record_id,n.content_hash,n.normalization_hash,
        r.source_record_id dependency_record_id,r.content_hash dependency_content_hash
      FROM source_proof_edge e
        JOIN normalized_source_revision n USING(normalization_key)
        JOIN source_record_revision r USING(revision_key) WHERE n.frame_format='compact'
    """)
    op.execute("""CREATE FUNCTION refresh_source_proof_invalid(keys bigint[]) RETURNS void
      LANGUAGE plpgsql AS $$ BEGIN
      DELETE FROM source_normalization_invalid i USING normalized_source_revision n
        WHERE n.normalization_key=ANY(keys) AND i.source_record_id=n.source_record_id
          AND i.content_hash=n.content_hash AND i.normalization_hash=n.normalization_hash;
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
    END $$""")
    op.execute("""CREATE FUNCTION refresh_proofs_after_source_update() RETURNS trigger
      LANGUAGE plpgsql AS $$ DECLARE keys bigint[]; BEGIN
      SELECT array_agg(DISTINCT k) INTO keys FROM (
        SELECT n.normalization_key k FROM new_sources s JOIN old_sources o USING(id)
          JOIN source_record_dependency d ON d.dependency_record_id=s.id
          JOIN normalized_source_revision n ON n.source_record_id=d.source_record_id
            AND n.content_hash=d.content_hash AND n.normalization_hash=d.normalization_hash
          WHERE s.content_hash IS DISTINCT FROM o.content_hash
            OR s.is_current IS DISTINCT FROM o.is_current
        UNION ALL
        SELECT e.normalization_key FROM new_sources s JOIN old_sources o USING(id)
          JOIN source_record_revision r ON r.source_record_id=s.id
          JOIN source_proof_edge e USING(revision_key)
          WHERE s.content_hash IS DISTINCT FROM o.content_hash
            OR s.is_current IS DISTINCT FROM o.is_current
        UNION ALL
        SELECT n.normalization_key FROM new_sources s JOIN old_sources o USING(id)
          JOIN normalized_source_revision n ON n.source_record_id=s.id
          WHERE s.content_hash IS DISTINCT FROM o.content_hash
            OR s.is_current IS DISTINCT FROM o.is_current) affected;
      PERFORM refresh_source_proof_invalid(coalesce(keys,'{}'::bigint[])); RETURN NULL;
    END $$""")
    op.execute("""CREATE TRIGGER design_c_source_invalid
      AFTER UPDATE ON source_record REFERENCING OLD TABLE AS old_sources NEW TABLE AS new_sources
      FOR EACH STATEMENT EXECUTE FUNCTION refresh_proofs_after_source_update()""")
    op.execute("""CREATE FUNCTION refresh_proofs_after_edges() RETURNS trigger
      LANGUAGE plpgsql AS $$ DECLARE keys bigint[]; BEGIN
      IF TG_TABLE_NAME='source_proof_edge' THEN
        SELECT array_agg(DISTINCT normalization_key) INTO keys FROM changed_edges;
      ELSE
        SELECT array_agg(DISTINCT n.normalization_key) INTO keys FROM changed_edges d
          JOIN normalized_source_revision n USING(source_record_id,content_hash,normalization_hash);
      END IF;
      PERFORM refresh_source_proof_invalid(coalesce(keys,'{}'::bigint[])); RETURN NULL;
    END $$""")
    for table in ("source_record_dependency", "source_proof_edge"):
        for action, transition in (("INSERT", "NEW"), ("DELETE", "OLD")):
            op.execute(f"""CREATE TRIGGER design_c_edges_{action.lower()}
              AFTER {action} ON {table} REFERENCING {transition} TABLE AS changed_edges
              FOR EACH STATEMENT EXECUTE FUNCTION refresh_proofs_after_edges()""")
        # Updates affect both the removed and new edge owners.
        op.execute(f"""CREATE TRIGGER design_c_edges_update_old AFTER UPDATE ON {table}
          REFERENCING OLD TABLE AS changed_edges FOR EACH STATEMENT
          EXECUTE FUNCTION refresh_proofs_after_edges()""")
        op.execute(f"""CREATE TRIGGER design_c_edges_update_new AFTER UPDATE ON {table}
          REFERENCING NEW TABLE AS changed_edges FOR EACH STATEMENT
          EXECUTE FUNCTION refresh_proofs_after_edges()""")
    op.execute("""CREATE FUNCTION refresh_proofs_after_current() RETURNS trigger
      LANGUAGE plpgsql AS $$ DECLARE keys bigint[]; BEGIN
      SELECT array_agg(DISTINCT n.normalization_key) INTO keys FROM changed_current c
        JOIN normalized_source_revision n ON n.source_record_id=c.source_record_id;
      PERFORM refresh_source_proof_invalid(coalesce(keys,'{}'::bigint[])); RETURN NULL;
    END $$""")
    for table in ("source_normalization_current", "normalized_source_revision"):
        for action, transition in (("INSERT", "NEW"), ("DELETE", "OLD")):
            op.execute(f"""CREATE TRIGGER design_c_current_{action.lower()}
              AFTER {action} ON {table} REFERENCING {transition} TABLE AS changed_current
              FOR EACH STATEMENT EXECUTE FUNCTION refresh_proofs_after_current()""")
        for side in ("OLD", "NEW"):
            op.execute(f"""CREATE TRIGGER design_c_current_update_{side.lower()}
              AFTER UPDATE ON {table} REFERENCING {side} TABLE AS changed_current
              FOR EACH STATEMENT EXECUTE FUNCTION refresh_proofs_after_current()""")
    op.execute("""CREATE FUNCTION refresh_all_source_proofs() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      PERFORM refresh_source_proof_invalid(array_agg(normalization_key))
        FROM normalized_source_revision; RETURN NULL;
    END $$""")
    for table in ("source_normalization_current", "source_record_dependency", "source_proof_edge"):
        op.execute(f"""CREATE TRIGGER design_c_proofs_truncate AFTER TRUNCATE ON {table}
          FOR EACH STATEMENT EXECUTE FUNCTION refresh_all_source_proofs()""")
    op.execute("""CREATE FUNCTION refresh_proofs_after_dataset() RETURNS trigger
      LANGUAGE plpgsql AS $$ DECLARE keys bigint[]; BEGIN
      IF NEW.is_synthetic IS DISTINCT FROM OLD.is_synthetic THEN
        SELECT array_agg(DISTINCT n.normalization_key) INTO keys
          FROM source_dependency_frame d JOIN source_record s ON s.id=d.dependency_record_id
          JOIN normalized_source_revision n ON n.source_record_id=d.source_record_id
            AND n.content_hash=d.content_hash AND n.normalization_hash=d.normalization_hash
          WHERE s.source_dataset_id=NEW.id;
        SELECT coalesce(keys,'{}'::bigint[]) || coalesce(array_agg(n.normalization_key),
          '{}'::bigint[]) INTO keys FROM normalized_source_revision n JOIN source_record s
          ON s.id=n.source_record_id WHERE s.source_dataset_id=NEW.id;
        PERFORM refresh_source_proof_invalid(coalesce(keys,'{}'::bigint[]));
      END IF; RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER design_c_dataset_invalid AFTER UPDATE ON source_dataset
      FOR EACH ROW EXECUTE FUNCTION refresh_proofs_after_dataset()""")
    op.execute("""CREATE FUNCTION enforce_ready_archive() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='source_archive' THEN
        IF TG_OP='INSERT' THEN
          IF NEW.state<>'writing' THEN
            RAISE EXCEPTION 'Archive must begin WRITING'; END IF;
        ELSIF OLD.state='ready' AND (TG_OP='DELETE' OR to_jsonb(NEW)<>to_jsonb(OLD)) THEN
          RAISE EXCEPTION 'Published archive metadata is immutable';
        ELSIF TG_OP='UPDATE' AND NEW.state IS DISTINCT FROM OLD.state
          AND NOT ((OLD.state='writing' AND NEW.state='verifying')
            OR (OLD.state='verifying' AND NEW.state='ready')) THEN
          RAISE EXCEPTION 'Archive publication requires WRITING VERIFYING READY';
        END IF;
      ELSIF TG_TABLE_NAME='source_record_revision' THEN
        IF NEW.raw_payload IS NULL AND NOT EXISTS(SELECT 1 FROM source_archive_object o
          JOIN source_archive a ON a.id=o.archive_id
          WHERE o.id=NEW.archive_object_id AND a.state='ready' AND o.kind='raw-records'
            AND NEW.archive_row>=0 AND NEW.archive_row<o.record_count) THEN
          RAISE EXCEPTION 'Raw revision requires a verified READY archive locator';
        END IF;
      ELSIF TG_TABLE_NAME='source_dataset' THEN
        IF NEW.publication_archive_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM source_archive WHERE id=NEW.publication_archive_id
          AND state='ready') THEN RAISE EXCEPTION 'Dataset archive is not READY'; END IF;
      ELSIF TG_TABLE_NAME='source_archive_object' THEN
        IF EXISTS(SELECT 1 FROM source_archive WHERE state='ready'
          AND ((TG_OP<>'INSERT' AND id=OLD.archive_id)
            OR (TG_OP<>'DELETE' AND id=NEW.archive_id))) THEN
          RAISE EXCEPTION 'Published archive object metadata is immutable'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$""")
    op.execute("""CREATE TRIGGER design_c_archive_immutable
      BEFORE INSERT OR UPDATE OR DELETE ON source_archive
      FOR EACH ROW EXECUTE FUNCTION enforce_ready_archive()""")
    op.execute("""CREATE TRIGGER design_c_object_immutable
      BEFORE INSERT OR UPDATE OR DELETE ON source_archive_object
      FOR EACH ROW EXECUTE FUNCTION enforce_ready_archive()""")
    for table in ("source_record_revision", "source_dataset"):
        op.execute(f"""CREATE TRIGGER design_c_archive_ready BEFORE INSERT OR UPDATE ON {table}
          FOR EACH ROW EXECUTE FUNCTION enforce_ready_archive()""")
    op.execute("""SELECT refresh_source_proof_invalid(array_agg(normalization_key))
      FROM normalized_source_revision""")


def remove_design_c_functions() -> None:
    op.execute("DROP VIEW source_dependency_frame")
    op.execute("DROP TRIGGER IF EXISTS design_c_source_invalid ON source_record")
    op.execute("DROP TRIGGER IF EXISTS design_c_dataset_invalid ON source_dataset")
    op.execute("DROP TRIGGER IF EXISTS design_c_archive_immutable ON source_archive")
    op.execute("DROP TRIGGER IF EXISTS design_c_object_immutable ON source_archive_object")
    for table in ("source_record_revision", "source_dataset"):
        op.execute(f"DROP TRIGGER IF EXISTS design_c_archive_ready ON {table}")
    for table in ("source_record_dependency", "source_proof_edge"):
        for action in ("insert", "delete", "update_old", "update_new"):
            op.execute(f"DROP TRIGGER IF EXISTS design_c_edges_{action} ON {table}")
    for table in ("source_normalization_current", "normalized_source_revision"):
        op.execute(f"DROP TRIGGER IF EXISTS design_c_edges_update_new ON {table}")
        for action in ("insert", "delete", "update_old", "update_new"):
            op.execute(f"DROP TRIGGER IF EXISTS design_c_current_{action} ON {table}")
    for table in ("source_normalization_current", "source_record_dependency", "source_proof_edge"):
        op.execute(f"DROP TRIGGER IF EXISTS design_c_proofs_truncate ON {table}")
    for signature in (
        "refresh_proofs_after_source_update()",
        "refresh_proofs_after_edges()",
        "refresh_proofs_after_dataset()",
        "enforce_ready_archive()",
        "refresh_proofs_after_current()",
        "refresh_all_source_proofs()",
        "refresh_source_proof_invalid(bigint[])",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "source_archive",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adapter_version", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("rights", sa.Text(), nullable=False),
        sa.Column("storage_reference", sa.Text(), nullable=False),
        sa.Column("compression", sa.Text(), server_default="gzip", nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size >= 0 AND compression='gzip'", name=op.f("ck_source_archive_format")
        ),
        sa.CheckConstraint(
            "state IN ('writing','verifying','ready')", name=op.f("ck_source_archive_state")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_archive")),
        sa.UniqueConstraint("manifest_hash", name=op.f("uq_source_archive_manifest_hash")),
    )
    op.create_table(
        "source_archive_object",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("archive_id", sa.Uuid(), nullable=False),
        sa.Column("object_hash", sa.String(length=64), nullable=False),
        sa.Column("original_hash", sa.String(length=64), nullable=False),
        sa.Column("compressed_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_bytes", sa.BigInteger(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "compressed_bytes >= 0 AND original_bytes >= 0 AND record_count >= 0",
            name=op.f("ck_source_archive_object_sizes"),
        ),
        sa.ForeignKeyConstraint(
            ["archive_id"],
            ["source_archive.id"],
            name=op.f("fk_source_archive_object_archive_id_source_archive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_archive_object")),
        sa.UniqueConstraint(
            "archive_id", "object_hash", name=op.f("uq_source_archive_object_archive_id")
        ),
    )
    op.create_index(
        op.f("ix_source_archive_object_archive_id"),
        "source_archive_object",
        ["archive_id"],
        unique=False,
    )
    op.create_table(
        "global_ingestion_job",
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("archive_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("staging_schema", sa.Text(), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('archiving','staging','normalizing','validated',"
            "'publishing','ready','failed')",
            name=op.f("ck_global_ingestion_job_state"),
        ),
        sa.ForeignKeyConstraint(
            ["archive_id"],
            ["source_archive.id"],
            name=op.f("fk_global_ingestion_job_archive_id_source_archive"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["source_dataset.id"],
            name=op.f("fk_global_ingestion_job_dataset_id_source_dataset"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_global_ingestion_job")),
        sa.UniqueConstraint(
            "dataset_id", "snapshot_hash", name=op.f("uq_global_ingestion_job_dataset_id")
        ),
        sa.UniqueConstraint("staging_schema", name=op.f("uq_global_ingestion_job_staging_schema")),
    )
    op.create_table(
        "source_normalization_invalid",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalization_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
            name=op.f(
                "fk_source_normalization_invalid_source_record_id_normalized_source_revision"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id",
            "content_hash",
            "normalization_hash",
            name=op.f("pk_source_normalization_invalid"),
        ),
    )
    op.add_column(
        "normalized_source_revision",
        sa.Column("normalization_key", sa.BigInteger(), sa.Identity(always=False), nullable=False),
    )
    op.add_column(
        "normalized_source_revision",
        sa.Column("frame_format", sa.Text(), server_default="full", nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_normalized_source_revision_normalization_key"),
        "normalized_source_revision",
        ["normalization_key"],
    )
    op.add_column("source_dataset", sa.Column("publication_archive_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_source_dataset_publication_archive_id_source_archive"),
        "source_dataset",
        "source_archive",
        ["publication_archive_id"],
        ["id"],
    )
    op.add_column(
        "source_record_revision",
        sa.Column("revision_key", sa.BigInteger(), sa.Identity(always=False), nullable=False),
    )
    op.add_column(
        "source_record_revision", sa.Column("archive_object_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("source_record_revision", sa.Column("archive_row", sa.Integer(), nullable=True))
    op.create_index(
        "ix_source_record_revision_archive_object_id",
        "source_record_revision",
        ["archive_object_id"],
    )
    op.alter_column(
        "source_record_revision",
        "raw_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.create_unique_constraint(
        op.f("uq_source_record_revision_revision_key"), "source_record_revision", ["revision_key"]
    )
    op.create_foreign_key(
        op.f("fk_source_record_revision_archive_object_id_source_archive_object"),
        "source_record_revision",
        "source_archive_object",
        ["archive_object_id"],
        ["id"],
    )
    op.create_table(
        "source_proof_edge",
        sa.Column("normalization_key", sa.BigInteger(), nullable=False),
        sa.Column("revision_key", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["normalization_key"],
            ["normalized_source_revision.normalization_key"],
            name=op.f("fk_source_proof_edge_normalization_key_normalized_source_revision"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_key"],
            ["source_record_revision.revision_key"],
            name=op.f("fk_source_proof_edge_revision_key_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "normalization_key", "revision_key", name=op.f("pk_source_proof_edge")
        ),
    )
    op.create_index(
        op.f("ix_source_proof_edge_revision_key"),
        "source_proof_edge",
        ["revision_key"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_source_record_revision_raw_evidence_retained",
        "source_record_revision",
        "raw_payload IS NOT NULL OR (archive_object_id IS NOT NULL "
        "AND archive_row IS NOT NULL AND archive_row >= 0)",
    )
    op.create_check_constraint(
        "ck_normalized_source_revision_frame_format",
        "normalized_source_revision",
        "frame_format IN ('full','compact')",
    )
    install_design_c_functions()
    # ### end Alembic commands ###


def downgrade() -> None:
    # Schema reversal must never discard externally retained scientific evidence.
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM source_record_revision WHERE raw_payload IS NULL)
          OR EXISTS(SELECT 1 FROM normalized_source_revision WHERE frame_format='compact') THEN
            RAISE EXCEPTION 'Design C downgrade blocked: run archive-backed restore_legacy first';
        END IF;
        IF EXISTS(SELECT 1 FROM global_ingestion_job WHERE state NOT IN ('ready','failed')) THEN
            RAISE EXCEPTION 'Design C downgrade blocked: finish or safely abandon pending jobs';
        END IF;
    END $$""")
    remove_design_c_functions()
    op.drop_constraint(
        "ck_source_record_revision_raw_evidence_retained", "source_record_revision", type_="check"
    )
    op.drop_constraint(
        "ck_normalized_source_revision_frame_format", "normalized_source_revision", type_="check"
    )
    op.drop_index(op.f("ix_source_proof_edge_revision_key"), table_name="source_proof_edge")
    op.drop_table("source_proof_edge")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_source_record_revision_archive_object_id_source_archive_object"),
        "source_record_revision",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_source_record_revision_revision_key"), "source_record_revision", type_="unique"
    )
    op.alter_column(
        "source_record_revision",
        "raw_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.drop_column("source_record_revision", "archive_row")
    op.drop_index(
        "ix_source_record_revision_archive_object_id", table_name="source_record_revision"
    )
    op.drop_column("source_record_revision", "archive_object_id")
    op.drop_column("source_record_revision", "revision_key")
    op.drop_constraint(
        op.f("fk_source_dataset_publication_archive_id_source_archive"),
        "source_dataset",
        type_="foreignkey",
    )
    op.drop_column("source_dataset", "publication_archive_id")
    op.drop_constraint(
        op.f("uq_normalized_source_revision_normalization_key"),
        "normalized_source_revision",
        type_="unique",
    )
    op.drop_column("normalized_source_revision", "frame_format")
    op.drop_column("normalized_source_revision", "normalization_key")
    op.drop_table("source_normalization_invalid")
    op.drop_table("global_ingestion_job")
    op.drop_index(op.f("ix_source_archive_object_archive_id"), table_name="source_archive_object")
    op.drop_table("source_archive_object")
    op.drop_table("source_archive")
    # ### end Alembic commands ###
