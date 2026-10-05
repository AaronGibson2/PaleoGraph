"""Cover locality counts and ordered material identities.

Revision ID: 0006_catalog_browse
Revises: 0005_classification
"""

from alembic import op

revision = "0006_catalog_browse"
down_revision = "0005_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_catalog_entry_locality_page",
        "catalog_entry",
        ["locality_id", "occurrence_id"],
        postgresql_include=["source_record_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_entry_locality_page", table_name="catalog_entry")
