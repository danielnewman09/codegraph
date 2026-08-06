"""SQLite connection lifecycle — SQLAlchemy Engine + session helpers.

Mirrors ``codegraph.backends.neo4j.connection.Neo4jConnection``:

- ``execute_raw(sql, params)`` returns ``(list[dict], columns)`` — rows
  keyed by column name (the SQLite shape of the Neo4j backend's
  ``(rows, columns)`` contract; callers that indexed rows positionally
  on Neo4j must switch to ``row["col"]``).
- ``session()`` yields a transactional SQLAlchemy Connection.
- ``health_check`` / ``close`` / ``reconnect`` mirror the driver
  lifecycle.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from codegraph.backends.sqlite.config import SqliteConfig

log = logging.getLogger(__name__)

# Per-connection pragmas.  WAL enables concurrent readers + fast commits;
# foreign_keys is OFF by default in SQLite and must be enabled per
# connection — FK cascade is the delete strategy.  synchronous=NORMAL is
# safe under WAL (~10x faster commits); busy_timeout handles concurrent
# writers; cache_size=-64000 pins a 64MB page cache.
_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA cache_size=-64000",
)


class SqliteUnavailableError(RuntimeError):
    """Raised when the SQLite database cannot be opened."""


class SqliteConnection:
    """Manages a single SQLAlchemy Engine over a SQLite database file."""

    def __init__(self, config: SqliteConfig | None = None):
        if config is None:
            config = SqliteConfig.from_env()
        self._config = config
        self._engine = self._build_engine(config)

    # ── Engine construction ─────────────────────────────────────────

    def _build_engine(self, config: SqliteConfig) -> sa.Engine:
        kwargs: dict[str, Any] = {
            "connect_args": {"check_same_thread": False},
        }
        if config.path == ":memory:":
            # SQLAlchemy's default pool hands out multiple connections,
            # each with its own private in-memory database.  StaticPool
            # pins a single shared connection so :memory: behaves like a
            # real database.
            kwargs["poolclass"] = StaticPool
        else:
            kwargs["connect_args"]["timeout"] = 30
        engine = sa.create_engine(config.url, **kwargs)

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _record) -> None:
            cursor = dbapi_conn.cursor()
            try:
                for pragma in _PRAGMAS:
                    cursor.execute(pragma)
            finally:
                cursor.close()

        return engine

    # ── Session access ──────────────────────────────────────────────

    @contextmanager
    def session(self):
        """Yield a transactional SQLAlchemy Connection (auto-commit).

        Use for write paths: DML runs inside one transaction that
        commits on exit and rolls back on exception.
        """
        with self._engine.begin() as conn:
            yield conn

    @contextmanager
    def connect(self):
        """Yield a read-only SQLAlchemy Connection (no auto-commit).

        Use for read paths that don't mutate.
        """
        with self._engine.connect() as conn:
            yield conn

    # ── Raw query (escape hatch) ────────────────────────────────────

    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Run a SQL statement, returning ``(rows, columns)``.

        *rows* is a list of dicts keyed by column name; *columns* is
        the ordered list of column names.  Commits the transaction so
        DDL/DML issued through this escape hatch persists.
        """
        with self._engine.connect() as conn:
            result = conn.execute(sa.text(query), params or {})
            if result.returns_rows:
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                conn.commit()
                return rows, columns
            conn.commit()
            return [], []

    # ── Lifecycle ───────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Return True if the database is reachable and operational."""
        try:
            with self._engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            return True
        except Exception:
            log.warning("SQLite health check failed", exc_info=True)
            return False

    def close(self) -> None:
        """Dispose the engine, closing all pooled connections."""
        self._engine.dispose()

    def reconnect(self) -> None:
        """Rebuild the engine from fresh environment configuration."""
        self._engine.dispose()
        self._config = SqliteConfig.from_env()
        self._engine = self._build_engine(self._config)

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def engine(self) -> sa.Engine:
        """The underlying SQLAlchemy Engine."""
        return self._engine

    @property
    def config(self) -> SqliteConfig:
        """The active configuration."""
        return self._config

    def require_connection(self) -> None:
        """Raise if the database is not reachable."""
        if not self.health_check():
            raise SqliteUnavailableError(
                f"Cannot open SQLite database at {self._config.path}"
            )


def row_to_dict(row) -> dict | None:
    """Convert a SQLAlchemy 2.0 Row to a plain dict.

    In 2.0, ``Row`` only supports integer indexing — string keys require
    ``row._mapping`` (see the migration guide "Result rows act like named
    tuples").  This helper normalises rows so backend code can use
    ``d["col"]`` uniformly.
    """
    if row is None:
        return None
    return dict(row._mapping)
