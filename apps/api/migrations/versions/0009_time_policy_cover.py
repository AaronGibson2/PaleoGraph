"""Keep scientific-policy eligibility covered on existing material browse reads.

Revision ID: 0009_time_policy_cover
Revises: 0008_browse_summaries
"""

from alembic import op

revision = "0009_time_policy_cover"
down_revision = "0008_browse_summaries"
branch_labels = None
depends_on = None


def replace_index(include: list[str]) -> None:
    op.drop_index("ix_catalog_entry_locality_page", table_name="catalog_entry")
    op.create_index(
        "ix_catalog_entry_locality_page",
        "catalog_entry",
        ["locality_id", "occurrence_id"],
        postgresql_include=include,
    )


def upgrade() -> None:
    replace_index(["source_record_id", "content_hash", "policy_version"])


def downgrade() -> None:
    replace_index(["source_record_id", "content_hash"])
