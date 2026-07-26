"""Neo4j driver lifecycle — wraps neomodel's db object.

Extracted from ``codegraph.persistence.connection``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from neo4j import NotificationDisabledCategory, NotificationMinimumSeverity
from neomodel import db

from codegraph.backends.neo4j.config import Neo4jConfig

log = logging.getLogger(__name__)


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j is not reachable."""


class Neo4jConnection:
    """Manages the Neo4j driver lifecycle via neomodel's db object.

    Provides session management, raw Cypher execution, and health checks.
    """

    def __init__(self, config: Neo4jConfig | None = None):
        if config is None:
            config = Neo4jConfig.from_env()
        self._config = config
        self._driver_ensured = False

    def ensure_driver(self) -> None:
        """Ensure neomodel's driver is initialised.

        Neomodel lazily creates the driver on first use, but some
        operations require it to exist.  This forces initialisation.

        Raises:
            Neo4jUnavailableError: If the driver cannot connect.
        """
        if db.driver is not None:
            return

        if not self._config.database_url:
            raise Neo4jUnavailableError(
                "No Neo4j connection URL configured. "
                "Set NEO4J_URI environment variable."
            )

        try:
            db.set_connection(url=self._config.database_url)
            self._driver_ensured = True
        except Exception as exc:
            raise Neo4jUnavailableError(
                f"Cannot connect to Neo4j at {self._config.database_url}: {exc}\n"
                "Is Neo4j running? Start it with: docker compose up -d"
            ) from exc

    def get_session(self):
        """Return a neo4j driver session as a context manager.

        Returns:
            A ``neo4j.Session`` context manager.
        """
        self.ensure_driver()
        return db.driver.session(
            notifications_min_severity=NotificationMinimumSeverity.WARNING,
            notifications_disabled_categories=[
                NotificationDisabledCategory.UNRECOGNIZED,
            ],
        )

    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Run a Cypher query and return rows as dicts keyed by column name.

        Args:
            query: Cypher query string.
            params: Optional dict of query parameters.

        Returns:
            A ``(rows, columns)`` tuple — *rows* is a list of dicts,
            *columns* the ordered column names.
        """
        self.ensure_driver()
        with self.get_session() as session:
            result = session.run(query, params or {})
            keys = list(result.keys())
            rows = [dict(zip(keys, record.values())) for record in result]
            return rows, keys

    def health_check(self) -> bool:
        """Check that Neo4j is reachable.

        Returns:
            True if the connection is working, False otherwise.
        """
        try:
            self.ensure_driver()
            db.cypher_query("RETURN 1")
            return True
        except Exception:
            log.warning("Neo4j connectivity check failed", exc_info=True)
            return False

    def require_connection(self) -> None:
        """Verify Neo4j is reachable; raise if not.

        Raises:
            Neo4jUnavailableError: If Neo4j is not reachable.
        """
        self.ensure_driver()
        try:
            db.cypher_query("RETURN 1")
        except Exception as exc:
            raise Neo4jUnavailableError(
                f"Cannot execute query against Neo4j: {exc}\n"
                "Is Neo4j running? Start it with: docker compose up -d"
            ) from exc
