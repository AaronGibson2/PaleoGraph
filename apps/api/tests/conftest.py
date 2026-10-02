import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Tests never load a developer's database URL or require a running database.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:1/test"
os.environ["CORS_ORIGINS"] = '["http://localhost:3000"]'


@pytest.fixture
def db_session() -> Iterator[Session]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL must point to a migrated disposable PostGIS database")
    engine = create_engine(
        url, connect_args={"options": "-csearch_path=public", "connect_timeout": 5}
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()
    engine.dispose()
