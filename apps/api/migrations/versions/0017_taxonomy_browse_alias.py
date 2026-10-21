"""Preserve display-node URLs across reversible browse unification."""

from alembic import op

revision = "0017_taxonomy_browse_alias"
down_revision = "0016_pbdb_taxonomy_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE taxonomy_browse_alias (
        old_id UUID CONSTRAINT pk_taxonomy_browse_alias PRIMARY KEY,
        node_id UUID NOT NULL
        CONSTRAINT fk_taxonomy_browse_alias_node_id_taxonomy_browse_node
        REFERENCES taxonomy_browse_node(id) ON DELETE CASCADE)""")
    op.create_index("ix_taxonomy_browse_alias_node_id", "taxonomy_browse_alias", ["node_id"])


def downgrade() -> None:
    op.drop_table("taxonomy_browse_alias")
