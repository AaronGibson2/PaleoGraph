"""Retain independent source occurrence evidence

Revision ID: 0010_pbdb_evidence
Revises: 0009_time_policy_cover
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_pbdb_evidence"
down_revision: str | Sequence[str] | None = "0009_time_policy_cover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATALOG_CHECKS = {
    "evidence_kind": "(evidence_kind = 'material' AND specimen_id IS NOT NULL) OR "
    "(evidence_kind = 'occurrence' AND specimen_id IS NULL)",
    "material_evidence_count": "material_evidence_count >= 0",
    "interpretation_policy": "interpretation_policy_version IS NULL OR "
    "interpretation_policy_version = policy_version",
    "provider_policy": "provider_age_policy_version IS NULL OR "
    "provider_age_policy_version = policy_version",
    "provider_age_key": "num_nonnulls(provider_age_source_record_id,provider_age_content_hash,"
    "provider_age_policy_version) IN (0,3)",
    "age_evidence_boundary": "interpretation_policy_version IS NULL OR "
    "provider_age_policy_version IS NULL",
    "age_proof": "(evidence_kind = 'material' AND interpretation_policy_version IS NOT NULL) OR "
    "(evidence_kind = 'occurrence' AND normalization_hash IS NOT NULL AND "
    "provider_age_policy_version IS NOT NULL)",
}


def upgrade() -> None:
    # Additive source-neutral evidence. Apply only to disposable databases in Phase 4B.
    op.create_table(
        "research_reference",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("source_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("published_year", sa.Text(), nullable=True),
        sa.Column("bibliography", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["source_dataset_id"],
            ["source_dataset.id"],
            name=op.f("fk_research_reference_source_dataset_id_source_dataset"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_research_reference_source_record_id_source_record"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_reference")),
        sa.UniqueConstraint(
            "source_record_id", name=op.f("uq_research_reference_source_record_id")
        ),
    )
    op.create_table(
        "collection_reference_evidence",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("collection_event_id", sa.Uuid(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_event_id"],
            ["collection_event.id"],
            name=op.f("fk_collection_reference_evidence_collection_event_id_collection_event"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["research_reference.id"],
            name=op.f("fk_collection_reference_evidence_reference_id_research_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_collection_reference_evidence_source_record_id_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id", "content_hash", name=op.f("pk_collection_reference_evidence")
        ),
    )
    op.create_table(
        "identification_evidence",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("occurrence_id", sa.Uuid(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("taxon_id", sa.Uuid(), nullable=False),
        sa.Column("provider_identification_id", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["occurrence.id"],
            name=op.f("fk_identification_evidence_occurrence_id_occurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["research_reference.id"],
            name=op.f("fk_identification_evidence_reference_id_research_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_identification_evidence_source_record_id_source_record_revision"),
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"], ["taxon.id"], name=op.f("fk_identification_evidence_taxon_id_taxon")
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id", "content_hash", name=op.f("pk_identification_evidence")
        ),
    )
    op.create_index(
        op.f("ix_identification_evidence_occurrence_id"),
        "identification_evidence",
        ["occurrence_id"],
        unique=False,
    )
    op.create_table(
        "material_evidence",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("occurrence_id", sa.Uuid(), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("catalog_label", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["occurrence.id"],
            name=op.f("fk_material_evidence_occurrence_id_occurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["research_reference.id"],
            name=op.f("fk_material_evidence_reference_id_research_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_material_evidence_source_record_id_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id", "content_hash", name=op.f("pk_material_evidence")
        ),
    )
    op.create_index(
        op.f("ix_material_evidence_occurrence_id"),
        "material_evidence",
        ["occurrence_id"],
        unique=False,
    )
    op.create_table(
        "normalized_source_revision",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalization_hash", sa.String(length=64), nullable=False),
        sa.Column("adapter_version", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
            name=op.f("fk_normalized_source_revision_ingestion_run_id_ingestion_run"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_normalized_source_revision_source_record_id_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id",
            "content_hash",
            "normalization_hash",
            name=op.f("pk_normalized_source_revision"),
        ),
    )
    op.create_table(
        "opinion_reference_evidence",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["research_reference.id"],
            name=op.f("fk_opinion_reference_evidence_reference_id_research_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_opinion_reference_evidence_source_record_id_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id", "content_hash", name=op.f("pk_opinion_reference_evidence")
        ),
    )
    op.create_table(
        "provider_age_evidence",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("older_ma", sa.Numeric(), nullable=True),
        sa.Column("younger_ma", sa.Numeric(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "older_ma >= 0 AND older_ma < 'Infinity'::numeric AND younger_ma >= 0 AND "
            "younger_ma < 'Infinity'::numeric AND older_ma >= younger_ma",
            name=op.f("ck_provider_age_evidence_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_provider_age_evidence_source_record_id_source_record_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id",
            "content_hash",
            "policy_version",
            name=op.f("pk_provider_age_evidence"),
        ),
    )
    op.create_table(
        "source_normalization_current",
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
                "fk_source_normalization_current_source_record_id_normalized_source_revision"
            ),
        ),
        sa.PrimaryKeyConstraint("source_record_id", name=op.f("pk_source_normalization_current")),
    )
    op.create_table(
        "source_record_dependency",
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalization_hash", sa.String(length=64), nullable=False),
        sa.Column("dependency_record_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_content_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["dependency_record_id", "dependency_content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
            name=op.f("fk_source_record_dependency_dependency_record_id_source_record_revision"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
            name=op.f("fk_source_record_dependency_source_record_id_normalized_source_revision"),
        ),
        sa.PrimaryKeyConstraint(
            "source_record_id",
            "content_hash",
            "normalization_hash",
            "dependency_record_id",
            "dependency_content_hash",
            name=op.f("pk_source_record_dependency"),
        ),
    )
    op.create_index(
        op.f("ix_source_record_dependency_dependency_record_id"),
        "source_record_dependency",
        ["dependency_record_id"],
        unique=False,
    )
    op.add_column(
        "catalog_entry",
        sa.Column("evidence_kind", sa.Text(), server_default="material", nullable=False),
    )
    op.add_column(
        "catalog_entry",
        sa.Column("material_evidence_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "catalog_entry", sa.Column("normalization_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "catalog_entry",
        sa.Column(
            "interpretation_policy_version",
            sa.Text(),
            server_default="ufvp-geology-v1:ics-2026-06",
            nullable=True,
        ),
    )
    op.add_column(
        "catalog_entry", sa.Column("provider_age_source_record_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "catalog_entry", sa.Column("provider_age_content_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "catalog_entry", sa.Column("provider_age_policy_version", sa.Text(), nullable=True)
    )
    op.alter_column("catalog_entry", "specimen_id", existing_type=sa.UUID(), nullable=True)
    op.drop_constraint(
        op.f("fk_catalog_entry_source_record_id_age_interpretation"),
        "catalog_entry",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_catalog_entry_source_record_id_age_interpretation"),
        "catalog_entry",
        "age_interpretation",
        ["source_record_id", "content_hash", "interpretation_policy_version"],
        ["source_record_id", "content_hash", "policy_version"],
    )
    op.create_foreign_key(
        op.f("fk_catalog_entry_source_record_id_normalized_source_revision"),
        "catalog_entry",
        "normalized_source_revision",
        ["source_record_id", "content_hash", "normalization_hash"],
        ["source_record_id", "content_hash", "normalization_hash"],
    )
    op.create_foreign_key(
        op.f("fk_catalog_entry_provider_age_source_record_id_provider_age_evidence"),
        "catalog_entry",
        "provider_age_evidence",
        [
            "provider_age_source_record_id",
            "provider_age_content_hash",
            "provider_age_policy_version",
        ],
        ["source_record_id", "content_hash", "policy_version"],
    )
    op.execute("UPDATE catalog_entry SET interpretation_policy_version=policy_version")
    for name, expression in CATALOG_CHECKS.items():
        op.create_check_constraint(op.f("ck_catalog_entry_" + name), "catalog_entry", expression)


def downgrade() -> None:
    # The old projection requires material. Drop only the new disposable occurrence
    # projection; retain canonical entities and raw revisions until a base downgrade.
    op.execute(
        "DELETE FROM catalog_term WHERE occurrence_id IN "
        "(SELECT occurrence_id FROM catalog_entry WHERE specimen_id IS NULL)"
    )
    op.execute("DELETE FROM catalog_entry WHERE specimen_id IS NULL")
    for name in CATALOG_CHECKS:
        op.drop_constraint(op.f("ck_catalog_entry_" + name), "catalog_entry", type_="check")
    op.drop_constraint(
        op.f("fk_catalog_entry_provider_age_source_record_id_provider_age_evidence"),
        "catalog_entry",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_catalog_entry_source_record_id_normalized_source_revision"),
        "catalog_entry",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_catalog_entry_source_record_id_age_interpretation"),
        "catalog_entry",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_catalog_entry_source_record_id_age_interpretation"),
        "catalog_entry",
        "age_interpretation",
        ["source_record_id", "content_hash", "policy_version"],
        ["source_record_id", "content_hash", "policy_version"],
    )
    op.alter_column("catalog_entry", "specimen_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("catalog_entry", "provider_age_policy_version")
    op.drop_column("catalog_entry", "provider_age_content_hash")
    op.drop_column("catalog_entry", "provider_age_source_record_id")
    op.drop_column("catalog_entry", "interpretation_policy_version")
    op.drop_column("catalog_entry", "normalization_hash")
    op.drop_column("catalog_entry", "material_evidence_count")
    op.drop_column("catalog_entry", "evidence_kind")
    op.drop_index(
        op.f("ix_source_record_dependency_dependency_record_id"),
        table_name="source_record_dependency",
    )
    op.drop_table("source_record_dependency")
    op.drop_table("source_normalization_current")
    op.drop_table("provider_age_evidence")
    op.drop_table("opinion_reference_evidence")
    op.drop_table("normalized_source_revision")
    op.drop_index(op.f("ix_material_evidence_occurrence_id"), table_name="material_evidence")
    op.drop_table("material_evidence")
    op.drop_index(
        op.f("ix_identification_evidence_occurrence_id"), table_name="identification_evidence"
    )
    op.drop_table("identification_evidence")
    op.drop_table("collection_reference_evidence")
    op.drop_table("research_reference")
