"""Disposable summaries and transactional input-generation invalidation.

Revision ID: 0008_browse_summaries
Revises: 0007_current_source_browse
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_browse_summaries"
down_revision = "0007_current_source_browse"
branch_labels = None
depends_on = None

# Statement triggers avoid an update to the generation row for every imported row.
# Derived inputs are included so manual repair/test edits also invalidate summaries.
INPUTS = (
    "source_record",
    "source_dataset",
    "catalog_entry",
    "catalog_term",
    "taxon_path",
    "classification_link",
    "taxon",
    "context_term",
    "age_interpretation",
    "locality",
    "collection",
    "institution",
)


def upgrade() -> None:
    op.create_table(
        "browse_projection_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("input_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("built_revision", sa.BigInteger()),
        sa.Column("projection_version", sa.Text()),
        sa.Column("built_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="ck_browse_projection_state_singleton"),
    )
    op.execute("INSERT INTO browse_projection_state (id) VALUES (1)")
    op.create_table(
        "locality_browse_summary",
        sa.Column("locality_id", sa.Uuid(), sa.ForeignKey("locality.id"), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "taxon_browse_summary",
        sa.Column("id", sa.Uuid(), sa.ForeignKey("taxon.id"), primary_key=True),
        *(
            sa.Column(name, sa.BigInteger(), nullable=False)
            for name in (
                "assertion_count",
                "specimen_count",
                "source_taxon_count",
                "known_age_count",
                "unknown_age_count",
            )
        ),
        sa.Column("older_ma", sa.Numeric()),
        sa.Column("younger_ma", sa.Numeric()),
    )
    op.execute("""CREATE FUNCTION invalidate_browse_summaries() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        UPDATE browse_projection_state SET input_revision=input_revision+1 WHERE id=1;
        RETURN NULL; END $$""")
    for table in INPUTS:
        op.execute(f"""CREATE TRIGGER invalidate_browse_summaries
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION invalidate_browse_summaries()""")


def downgrade() -> None:
    for table in INPUTS:
        op.execute(f"DROP TRIGGER invalidate_browse_summaries ON {table}")
    op.execute("DROP FUNCTION invalidate_browse_summaries()")
    op.drop_table("taxon_browse_summary")
    op.drop_table("locality_browse_summary")
    op.drop_table("browse_projection_state")
