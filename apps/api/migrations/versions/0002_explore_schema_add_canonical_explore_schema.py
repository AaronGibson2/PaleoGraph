"""add canonical explore schema

Revision ID: 0002_explore_schema
Revises: 0001_enable_postgis
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0002_explore_schema"
down_revision: str | Sequence[str] | None = "0001_enable_postgis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "locality",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("original_latitude", sa.Text(), nullable=True),
        sa.Column("original_longitude", sa.Text(), nullable=True),
        sa.Column("coordinate_uncertainty_m", sa.Float(), nullable=True),
        sa.Column("coordinate_precision", sa.Float(), nullable=True),
        sa.Column("geodetic_datum", sa.Text(), nullable=True),
        sa.Column("location_is_generalized", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("location_is_withheld", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("information_withheld", sa.Text(), nullable=True),
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
            "coordinate_precision >= 0 AND coordinate_precision < 'Infinity'::float8",
            name=op.f("ck_locality_precision"),
        ),
        sa.CheckConstraint(
            "coordinate_uncertainty_m >= 0 AND coordinate_uncertainty_m < 'Infinity'::float8",
            name=op.f("ck_locality_uncertainty"),
        ),
        sa.CheckConstraint(
            "NOT location_is_withheld OR geom IS NULL", name=op.f("ck_locality_withheld_point")
        ),
        sa.CheckConstraint(
            "geom IS NULL OR (NOT ST_IsEmpty(geom) AND ST_X(geom) BETWEEN -180 AND 180 "
            "AND ST_Y(geom) BETWEEN -90 AND 90)",
            name=op.f("ck_locality_valid_point"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locality")),
    )
    op.create_index("ix_locality_geom", "locality", ["geom"], unique=False, postgresql_using="gist")
    op.create_table(
        "source",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("api_url", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source")),
        sa.UniqueConstraint("name", name=op.f("uq_source_name")),
    )
    op.create_table(
        "taxon",
        sa.Column("scientific_name", sa.Text(), nullable=False),
        sa.Column("rank", sa.String(length=50), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_taxon")),
    )
    op.create_table(
        "collection_event",
        sa.Column("locality_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("stratigraphy", sa.Text(), nullable=True),
        sa.Column("older_ma", sa.Numeric(), nullable=True),
        sa.Column("younger_ma", sa.Numeric(), nullable=True),
        sa.Column("early_interval_name", sa.Text(), nullable=True),
        sa.Column("late_interval_name", sa.Text(), nullable=True),
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
            "older_ma >= 0 AND older_ma < 'Infinity'::numeric",
            name=op.f("ck_collection_event_older_age"),
        ),
        sa.CheckConstraint(
            "younger_ma >= 0 AND younger_ma < 'Infinity'::numeric",
            name=op.f("ck_collection_event_younger_age"),
        ),
        sa.CheckConstraint("older_ma >= younger_ma", name=op.f("ck_collection_event_age_order")),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["locality.id"], name=op.f("fk_collection_event_locality_id_locality")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_event")),
    )
    op.create_index(
        op.f("ix_collection_event_locality_id"), "collection_event", ["locality_id"], unique=False
    )
    op.create_table(
        "source_dataset",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_dataset_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("dataset_url", sa.Text(), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("rights_holder", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default="false", nullable=False),
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
            ["source_id"], ["source.id"], name=op.f("fk_source_dataset_source_id_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_dataset")),
        sa.UniqueConstraint(
            "source_id", "external_dataset_id", name=op.f("uq_source_dataset_source_id")
        ),
    )
    op.create_table(
        "ingestion_run",
        sa.Column("source_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_read", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
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
            "status IN ('running', 'completed', 'failed', 'partial')",
            name=op.f("ck_ingestion_run_status"),
        ),
        sa.CheckConstraint(
            "records_read >= 0 AND records_inserted >= 0 AND records_updated >= 0 "
            "AND records_skipped >= 0 AND records_failed >= 0",
            name=op.f("ck_ingestion_run_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"],
            ["source_dataset.id"],
            name=op.f("fk_ingestion_run_source_dataset_id_source_dataset"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_run")),
        sa.UniqueConstraint("id", "source_dataset_id", name=op.f("uq_ingestion_run_id")),
    )
    op.create_table(
        "occurrence",
        sa.Column("taxon_id", sa.Uuid(), nullable=False),
        sa.Column("collection_event_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["collection_event_id"],
            ["collection_event.id"],
            name=op.f("fk_occurrence_collection_event_id_collection_event"),
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"], ["taxon.id"], name=op.f("fk_occurrence_taxon_id_taxon")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_occurrence")),
    )
    op.create_index(
        op.f("ix_occurrence_collection_event_id"),
        "occurrence",
        ["collection_event_id"],
        unique=False,
    )
    op.create_table(
        "source_record",
        sa.Column("source_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("basis_of_record", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("rights_holder", sa.Text(), nullable=True),
        sa.Column("access_rights", sa.Text(), nullable=True),
        sa.Column("information_withheld", sa.Text(), nullable=True),
        sa.Column("data_generalizations", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
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
            "last_seen_at >= first_seen_at", name=op.f("ck_source_record_seen_order")
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id", "source_dataset_id"],
            ["ingestion_run.id", "ingestion_run.source_dataset_id"],
            name=op.f("fk_source_record_ingestion_run_id_ingestion_run"),
        ),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"],
            ["source_dataset.id"],
            name=op.f("fk_source_record_source_dataset_id_source_dataset"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_record")),
        sa.UniqueConstraint(
            "source_dataset_id",
            "record_type",
            "source_record_id",
            name=op.f("uq_source_record_source_dataset_id"),
        ),
    )
    op.create_table(
        "collection_event_evidence",
        sa.Column("collection_event_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_event_id"],
            ["collection_event.id"],
            name=op.f("fk_collection_event_evidence_collection_event_id_collection_event"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_collection_event_evidence_source_record_id_source_record"),
        ),
        sa.PrimaryKeyConstraint(
            "collection_event_id", "source_record_id", name=op.f("pk_collection_event_evidence")
        ),
    )
    op.create_table(
        "locality_evidence",
        sa.Column("locality_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["locality.id"], name=op.f("fk_locality_evidence_locality_id_locality")
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_locality_evidence_source_record_id_source_record"),
        ),
        sa.PrimaryKeyConstraint(
            "locality_id", "source_record_id", name=op.f("pk_locality_evidence")
        ),
    )
    op.create_table(
        "occurrence_evidence",
        sa.Column("occurrence_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["occurrence.id"],
            name=op.f("fk_occurrence_evidence_occurrence_id_occurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_occurrence_evidence_source_record_id_source_record"),
        ),
        sa.PrimaryKeyConstraint(
            "occurrence_id", "source_record_id", name=op.f("pk_occurrence_evidence")
        ),
    )
    op.create_table(
        "taxon_evidence",
        sa.Column("taxon_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_record.id"],
            name=op.f("fk_taxon_evidence_source_record_id_source_record"),
        ),
        sa.ForeignKeyConstraint(
            ["taxon_id"], ["taxon.id"], name=op.f("fk_taxon_evidence_taxon_id_taxon")
        ),
        sa.PrimaryKeyConstraint("taxon_id", "source_record_id", name=op.f("pk_taxon_evidence")),
    )


def downgrade() -> None:
    op.drop_table("taxon_evidence")
    op.drop_table("occurrence_evidence")
    op.drop_table("locality_evidence")
    op.drop_table("collection_event_evidence")
    op.drop_table("source_record")
    op.drop_index(op.f("ix_occurrence_collection_event_id"), table_name="occurrence")
    op.drop_table("occurrence")
    op.drop_table("ingestion_run")
    op.drop_table("source_dataset")
    op.drop_index(op.f("ix_collection_event_locality_id"), table_name="collection_event")
    op.drop_table("collection_event")
    op.drop_table("taxon")
    op.drop_table("source")
    op.drop_index("ix_locality_geom", table_name="locality", postgresql_using="gist")
    op.drop_table("locality")
