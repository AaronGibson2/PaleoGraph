from alembic import context
from geoalchemy2 import alembic_helpers

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base, create_db_engine

target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: dict[str, str]) -> bool:
    # PostGIS owns spatial_ref_sys; Alembic must not propose dropping it.
    return not (type_ == "table" and name == "spatial_ref_sys")


def run_migrations_offline() -> None:
    context.configure(
        url=str(Settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(Settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_name=include_name,
                render_item=alembic_helpers.render_item,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
