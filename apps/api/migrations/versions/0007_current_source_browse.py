"""Cover the current-source revision guard without fetching raw-payload rows.

Revision ID: 0007_current_source_browse
Revises: 0006_catalog_browse
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_current_source_browse"
down_revision = "0006_catalog_browse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_source_record_current_catalog",
        "source_record",
        ["id"],
        postgresql_include=["content_hash", "source_dataset_id"],
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index("ix_source_record_current_catalog", table_name="source_record")
