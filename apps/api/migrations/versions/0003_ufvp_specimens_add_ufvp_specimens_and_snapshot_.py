"""add UFVP specimens and snapshot provenance

Revision ID: 0003_ufvp_specimens
Revises: 0002_explore_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ufvp_specimens"
down_revision: str | Sequence[str] | None = "0002_explore_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "institution",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institution")),
    )
    op.create_table(
        "collection",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institution.id"],
            name=op.f("fk_collection_institution_id_institution"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection")),
    )
    op.create_table(
        "specimen",
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.Column("institution_code", sa.Text(), nullable=True),
        sa.Column("collection_code", sa.Text(), nullable=True),
        sa.Column("catalog_number", sa.Text(), nullable=True),
        sa.Column("occurrence_identifier", sa.Text(), nullable=True),
        sa.Column("material_entity_identifier", sa.Text(), nullable=True),
        sa.Column("other_identifiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preparations", sa.Text(), nullable=True),
        sa.Column("individual_count", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collection.id"], name=op.f("fk_specimen_collection_id_collection")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specimen")),
    )
    op.create_table(
        "source_record_revision",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
            name=op.f("fk_source_record_revision_ingestion_run_id_ingestion_run"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_source_record_revision_source_record_id_source_record"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id", "content_hash", name=op.f("pk_source_record_revision")
        ),
    )
    op.create_table(
        "specimen_evidence",
        sa.Column("specimen_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_specimen_evidence_source_record_id_source_record"),
        ),
        sa.ForeignKeyConstraint(
            ["specimen_id"], ["specimen.id"], name=op.f("fk_specimen_evidence_specimen_id_specimen")
        ),
        sa.PrimaryKeyConstraint(
            "specimen_id", "source_record_id", name=op.f("pk_specimen_evidence")
        ),
    )
    op.add_column(
        "ingestion_run",
        sa.Column("records_accepted", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_ingestion_run_accepted_count"), "ingestion_run", "records_accepted >= 0"
    )
    op.add_column("ingestion_run", sa.Column("importer_version", sa.Text(), nullable=True))
    op.add_column(
        "ingestion_run",
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("ingestion_run", sa.Column("scope", sa.Text(), nullable=True))
    op.add_column("occurrence", sa.Column("specimen_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_occurrence_specimen_id"), "occurrence", ["specimen_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_occurrence_specimen_id_specimen"),
        "occurrence",
        "specimen",
        ["specimen_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_occurrence_specimen_id_specimen"), "occurrence", type_="foreignkey")
    op.drop_index(op.f("ix_occurrence_specimen_id"), table_name="occurrence")
    op.drop_column("occurrence", "specimen_id")
    op.drop_column("ingestion_run", "scope")
    op.drop_column("ingestion_run", "snapshot")
    op.drop_column("ingestion_run", "importer_version")
    op.drop_constraint(op.f("ck_ingestion_run_accepted_count"), "ingestion_run", type_="check")
    op.drop_column("ingestion_run", "records_accepted")
    op.drop_table("specimen_evidence")
    op.drop_table("source_record_revision")
    op.drop_table("specimen")
    op.drop_table("collection")
    op.drop_table("institution")
