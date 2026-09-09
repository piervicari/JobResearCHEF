"""Database engine and transaction helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Resolve a configured database URL to its effective form.

    Central resolver (ADR 0042): a leading `~` in a file-backed SQLite URL
    expands against the runtime HOME so every entrypoint — CLI, scanner,
    dashboard, sync commands — opens the same canonical file. Relative
    SQLite paths are left untouched (the CLI joins those to the project
    root); `:memory:` and non-SQLite URLs pass through unchanged.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return database_url
    expanded = os.path.expanduser(url.database)
    if expanded == url.database:
        return database_url
    return str(url.set(database=expanded))


def ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    database_url = normalize_database_url(database_url)
    ensure_sqlite_parent(database_url)
    engine = create_engine(database_url, echo=echo)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = session_factory(engine)
    with factory() as session:
        with session.begin():
            yield session
