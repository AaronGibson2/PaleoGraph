"""Bounded source-classification membership projection.

Revision ID: 0005_classification
Revises: 0004_discovery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_classification"
down_revision: str | Sequence[str] | None = "0004_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_link",
        sa.Column(
            "taxon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("taxon.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "parent_taxon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("taxon.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("taxon_id <> parent_taxon_id", name="ck_classification_no_self_parent"),
    )
    op.create_index(
        "ix_classification_link_parent_taxon_id", "classification_link", ["parent_taxon_id"]
    )
    op.execute("""INSERT INTO classification_link
WITH parents AS (
    SELECT DISTINCT ON (p.ancestor_id) p.ancestor_id id, a.ancestor_id parent_id
    FROM taxon_path p JOIN taxon child ON child.id=p.ancestor_id
    LEFT JOIN taxon_path a ON a.taxon_id=p.taxon_id AND a.ancestor_id<>p.ancestor_id
        AND a.ancestor_id<>a.taxon_id AND EXISTS (SELECT 1 FROM taxon parent
            WHERE parent.id=a.ancestor_id AND (p.ancestor_id=p.taxon_id OR
               
        array_position(ARRAY['kingdom','phylum','class','order','family','genus','species'],
        parent.rank) <
        array_position(ARRAY['kingdom','phylum','class','order','family','genus','species'],
        child.rank)))
    LEFT JOIN taxon parent ON parent.id=a.ancestor_id
    ORDER BY p.ancestor_id,
        array_position(ARRAY['kingdom','phylum','class','order','family','genus','species'],
        parent.rank) DESC NULLS LAST,a.ancestor_id
) SELECT id,parent_id FROM parents
    """)
    op.execute("ANALYZE classification_link")


def downgrade() -> None:
    op.drop_table("classification_link")
