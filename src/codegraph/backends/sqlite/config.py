"""SQLite backend configuration.

Mirrors ``codegraph.backends.neo4j.config.Neo4jConfig``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from codegraph.backends.interface import BackendConfig


@dataclass
class SqliteConfig(BackendConfig):
    """SQLite connection configuration.

    Attributes:
        path: Filesystem path to the SQLite database file, or the
            literal ``":memory:"`` for a transient in-memory database
            (used by tests).
    """

    path: str = "codegraph.sqlite3"

    @classmethod
    def from_env(cls) -> SqliteConfig:
        """Build a SqliteConfig from environment variables.

        Reads ``SQLITE_PATH`` (default ``codegraph.sqlite3`` in the
        current working directory).
        """
        return cls(path=os.environ.get("SQLITE_PATH", "codegraph.sqlite3"))

    @property
    def url(self) -> str:
        """Return the SQLAlchemy database URL for this config."""
        if self.path == ":memory:":
            return "sqlite:///:memory:"
        return f"sqlite:///{self.path}"
