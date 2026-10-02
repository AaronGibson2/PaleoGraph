import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.models import Base


@pytest.mark.integration
def test_migration_head_and_postgis_geometry() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a migrated disposable PostGIS database")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(
        url, connect_args={"connect_timeout": 5, "options": "-csearch_path=public"}
    )
    try:
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == head
            assert connection.scalar(text("SELECT PostGIS_Version()"))
            point = connection.execute(
                text(
                    "SELECT ST_SRID(geom), ST_X(geom), ST_Y(geom) FROM "
                    "(SELECT ST_SetSRID(ST_MakePoint(-82.3, 29.6), 4326)"
                    "::geometry(Point, 4326) AS geom) AS point"
                )
            ).one()
            assert tuple(point) == (4326, -82.3, 29.6)
            assert set(Base.metadata.tables) | {"alembic_version", "spatial_ref_sys"} == set(
                inspect(connection).get_table_names(schema="public")
            )
    finally:
        engine.dispose()
