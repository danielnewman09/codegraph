"""Neo4j connection access — backward-compatible wrappers.

These functions now delegate to the Neo4j backend.
Prefer ``from codegraph.backends.neo4j import Neo4jBackend`` in new code.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from neo4j import NotificationDisabledCategory, NotificationMinimumSeverity
from neomodel import db

log = logging.getLogger(__name__)


def get_session():
    """Return a neo4j driver session as a context manager.

    Uses the active Neo4j backend's connection.
    """
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    return conn.get_session()


def cypher_query(query: str, params: dict | None = None) -> tuple[list[Any], dict]:
    """Run a Cypher query via the Neo4j backend."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    return conn.execute_raw(query, params)


def verify_connectivity() -> bool:
    """Check that Neo4j is reachable."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    return conn.health_check()


def require_connection() -> None:
    """Verify Neo4j is reachable; raise if not."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    conn.require_connection()


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j is not reachable."""


def _ensure_driver() -> None:
    """Ensure neomodel's driver is initialised.

    Raises:
        Neo4jUnavailableError: If the driver cannot connect to Neo4j.
    """
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    conn.ensure_driver()