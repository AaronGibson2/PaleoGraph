"""Additive archived PBDB taxonomy graph; no existing scientific rows change."""

from alembic import op

revision = "0016_pbdb_taxonomy_hierarchy"
down_revision = "0015_taxonomy_browse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE pbdb_taxonomy_snapshot (
        hash VARCHAR(64) CONSTRAINT pk_pbdb_taxonomy_snapshot PRIMARY KEY,
        manifest_hash VARCHAR(64) NOT NULL
        CONSTRAINT uq_pbdb_taxonomy_snapshot_manifest_hash UNIQUE,
        storage_reference TEXT NOT NULL, manifest JSONB NOT NULL)""")
    op.execute("""CREATE TABLE pbdb_taxonomy_head (
        scope TEXT CONSTRAINT pk_pbdb_taxonomy_head PRIMARY KEY, snapshot_hash VARCHAR(64) NOT NULL
        CONSTRAINT fk_pbdb_taxonomy_head_snapshot_hash_pbdb_taxonomy_snapshot
        REFERENCES pbdb_taxonomy_snapshot(hash))""")
    op.execute("""CREATE TABLE pbdb_taxonomy_record (
        snapshot_hash VARCHAR(64) NOT NULL
        CONSTRAINT fk_pbdb_taxonomy_record_snapshot_hash_pbdb_taxonomy_snapshot
        REFERENCES pbdb_taxonomy_snapshot(hash),
        selector TEXT NOT NULL, concept_id TEXT NOT NULL, payload JSONB NOT NULL,
        CONSTRAINT pk_pbdb_taxonomy_record PRIMARY KEY(snapshot_hash,selector))""")
    op.create_index("ix_pbdb_taxonomy_record_concept_id", "pbdb_taxonomy_record", ["concept_id"])
    op.execute("""CREATE TABLE pbdb_taxonomy_dependency (
        snapshot_hash VARCHAR(64) NOT NULL, selector TEXT NOT NULL,
        relationship TEXT NOT NULL, target TEXT NOT NULL,
        CONSTRAINT pk_pbdb_taxonomy_dependency
        PRIMARY KEY(snapshot_hash,selector,relationship,target),
        CONSTRAINT fk_pbdb_taxonomy_dependency_child FOREIGN KEY(snapshot_hash,selector)
        REFERENCES pbdb_taxonomy_record(snapshot_hash,selector),
        CONSTRAINT fk_pbdb_taxonomy_dependency_target FOREIGN KEY(snapshot_hash,target)
        REFERENCES pbdb_taxonomy_record(snapshot_hash,selector))""")


def downgrade() -> None:
    for table in (
        "pbdb_taxonomy_dependency",
        "pbdb_taxonomy_record",
        "pbdb_taxonomy_head",
        "pbdb_taxonomy_snapshot",
    ):
        op.drop_table(table)
