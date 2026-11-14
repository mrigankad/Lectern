"""SQLite engine (WAL) and session helper."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from . import config

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        engine = create_engine(
            f"sqlite:///{config.db_path().as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        _engine = engine
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests that switch the data directory)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    from . import models  # noqa: F401  (registers the tables)

    SQLModel.metadata.create_all(get_engine())
    _add_missing_columns()


@contextmanager
def session() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s


def _add_missing_columns() -> None:
    """Tiny forward-only migration for additive nullable columns (no Alembic yet)."""
    from sqlalchemy import inspect, text
    engine = get_engine()
    wanted = {"deck": {"icon": "VARCHAR", "icon_color": "VARCHAR"}, "message": {"undone_at": "VARCHAR"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sqltype in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}"))
