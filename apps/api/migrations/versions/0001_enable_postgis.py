"""Enable PostGIS; scientific tables belong to the next phase."""

from alembic import op

revision = "0001_enable_postgis"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # An existing extension may be shared or image-provisioned. Never drop it here.
    pass
