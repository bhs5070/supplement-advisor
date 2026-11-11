"""SQLAlchemy connections; callers explicitly commit successful transactions."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
        raise ValueError("Use PostgreSQL with psycopg; SQLite is for isolated tests only")
    return create_engine(url, pool_pre_ping=True, echo=False, hide_parameters=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
