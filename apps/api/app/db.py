from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Connection, Engine, MetaData, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, SessionTransaction

from app.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        # PostGIS images may expose tiger/topology tables on the role search path.
        # Application queries and Alembic must resolve only our public schema.
        connect_args={"connect_timeout": 5, "options": "-csearch_path=public"},
    )


def main() -> None:
    """Verify a live PostGIS connection without creating scientific tables."""
    engine = create_db_engine(Settings())
    try:
        with engine.connect() as connection:
            print(connection.scalar(text("SELECT PostGIS_Full_Version()")))
    finally:
        engine.dispose()


class BrowseSession(Session):
    """Lazy request sessions; validation does not require a database connection."""


@event.listens_for(BrowseSession, "after_begin")
def _browse_transaction(
    session: BrowseSession, transaction: SessionTransaction, connection: Connection
) -> None:
    if transaction.nested:
        return
    # Request-local only: ingestion sessions and server defaults are untouched.
    # Broad aggregates do not amortize JIT; skewed counts need actual parameters
    # to select useful parallel work instead of an underestimated generic plan.
    connection.exec_driver_sql("SET LOCAL jit = off")
    connection.exec_driver_sql("SET LOCAL plan_cache_mode = force_custom_plan")


def get_session(request: Request) -> Iterator[Session]:
    with BrowseSession(request.app.state.db_engine) as session:
        yield session


if __name__ == "__main__":
    main()
