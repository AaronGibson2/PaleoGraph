"""Reversible taxonomy browse projection; no source/scientific row changes."""

from alembic import op

revision = "0015_taxonomy_browse"
down_revision = "0014_design_c_native_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE taxonomy_browse_state (
    scope TEXT NOT NULL,
    built_revision BIGINT NOT NULL,
    projection_version TEXT NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    built_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_taxonomy_browse_state PRIMARY KEY (scope)
)""")
    op.execute("""CREATE TABLE taxonomy_browse_node (
    id UUID NOT NULL,
    scope TEXT NOT NULL,
    parent_id UUID,
    name TEXT NOT NULL,
    rank TEXT,
    search_name TEXT NOT NULL,
    placement TEXT NOT NULL,
    path JSONB NOT NULL,
    ufvp_count BIGINT NOT NULL,
    pbdb_count BIGINT NOT NULL,
    summary JSONB NOT NULL,
    CONSTRAINT pk_taxonomy_browse_node PRIMARY KEY (id),
    CONSTRAINT fk_taxonomy_browse_node_parent_id_taxonomy_browse_node
    FOREIGN KEY(parent_id) REFERENCES taxonomy_browse_node (id) DEFERRABLE INITIALLY DEFERRED
)""")
    op.execute(
        """CREATE INDEX ix_taxonomy_browse_node_parent_id ON taxonomy_browse_node (parent_id)"""
    )
    op.execute("""CREATE INDEX ix_taxonomy_browse_node_scope ON taxonomy_browse_node (scope)""")
    op.execute(
        """CREATE INDEX ix_taxonomy_browse_node_search_name ON taxonomy_browse_node (search_name)"""
    )
    op.execute("""CREATE TABLE taxonomy_browse_concept (
    node_id UUID NOT NULL,
    source TEXT NOT NULL,
    concept_key TEXT NOT NULL,
    taxon_id UUID,
    details JSONB NOT NULL,
    CONSTRAINT pk_taxonomy_browse_concept PRIMARY KEY (node_id, source, concept_key),
    CONSTRAINT fk_taxonomy_browse_concept_node_id_taxonomy_browse_node
    FOREIGN KEY(node_id) REFERENCES taxonomy_browse_node (id),
    CONSTRAINT fk_taxonomy_browse_concept_taxon_id_taxon FOREIGN KEY(taxon_id) REFERENCES taxon (id)
)""")
    op.execute(
        """CREATE INDEX ix_taxonomy_browse_concept_taxon_id ON taxonomy_browse_concept (taxon_id)"""
    )
    op.execute("""CREATE TABLE taxonomy_browse_path (
    ancestor_id UUID NOT NULL,
    node_id UUID NOT NULL,
    depth INTEGER NOT NULL,
    CONSTRAINT pk_taxonomy_browse_path PRIMARY KEY (ancestor_id, node_id),
    CONSTRAINT fk_taxonomy_browse_path_ancestor_id_taxonomy_browse_node
    FOREIGN KEY(ancestor_id) REFERENCES taxonomy_browse_node (id),
    CONSTRAINT fk_taxonomy_browse_path_node_id_taxonomy_browse_node
    FOREIGN KEY(node_id) REFERENCES taxonomy_browse_node (id)
)""")
    op.execute(
        """CREATE INDEX ix_taxonomy_path_node ON taxonomy_browse_path (node_id, ancestor_id)"""
    )
    op.execute("""CREATE TABLE taxonomy_browse_member (
    occurrence_id UUID NOT NULL,
    node_id UUID NOT NULL,
    source TEXT NOT NULL,
    CONSTRAINT pk_taxonomy_browse_member PRIMARY KEY (occurrence_id),
    CONSTRAINT fk_taxonomy_browse_member_occurrence_id_catalog_entry
    FOREIGN KEY(occurrence_id) REFERENCES catalog_entry (occurrence_id) ON DELETE CASCADE,
    CONSTRAINT fk_taxonomy_browse_member_node_id_taxonomy_browse_node
    FOREIGN KEY(node_id) REFERENCES taxonomy_browse_node (id)
)""")
    op.execute(
        """CREATE INDEX ix_taxonomy_browse_member_node_id ON taxonomy_browse_member (node_id)"""
    )


def downgrade() -> None:
    op.drop_table("taxonomy_browse_member")
    op.drop_table("taxonomy_browse_path")
    op.drop_table("taxonomy_browse_concept")
    op.drop_table("taxonomy_browse_node")
    op.drop_table("taxonomy_browse_state")
