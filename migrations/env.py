"""Migration connections come from DATABASE_URL, never a checked-in credential."""

import os

from alembic import context
from sqlalchemy.engine import make_url

from supplement_advisor.database import make_engine
from supplement_advisor.models import Base


def database_url():
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL must be configured to run migrations")
    url = make_url(value)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return url


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=database_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied_connection = context.config.attributes.get("connection")
    if supplied_connection is not None:
        migrate(supplied_connection)
    else:
        engine = make_engine(database_url())
        try:
            with engine.connect() as connection:
                migrate(connection)
        finally:
            engine.dispose()
