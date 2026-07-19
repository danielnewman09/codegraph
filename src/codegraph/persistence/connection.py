"""Single entry point for Neo4j access — ORM and Cypher.

Provides connection management for all Neo4j interactions. Configuration
comes from environment variables (``NEO4J_URI``, ``NEO4J_USER``,
``NEO4J_PASSWORD``) set once at import time by :mod:`codegraph.persistence.config`.

This module supplements :class:`~codegraph.persistence.repository.GraphRepository`
(which handles ORM reads via neomodel) with direct Cypher access for
queries that don't fit the neomodel model (e.g. TRACES_TO traversals,
stats, aggregation).

Usage::

    from codegraph.persistence.connection import get_session, cypher_query

    # Raw Cypher via session context manager
    with get_session() as session:
        result = session.run("MATCH (n:Class) RETURN n.name AS name")

    # Convenience wrapper (returns list of dicts)
    results, meta = cypher_query("MATCH (n:Class) RETURN n.name AS name")

    # ORM reads (unchanged)
    from codegraph.persistence.repository import GraphRepository
    repo = GraphRepository()
    graph = repo.get_by_tag("design")
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

    Uses neomodel's globally-configured driver — no separate connection
    management needed.  The driver is lazily initialised on first access.

    Equivalent to the previous pattern::

        from services.dependencies import get_neo4j
        with get_neo4j().session() as ns:
            result = ns.run("MATCH ...")

    Now becomes::

        from codegraph.persistence.connection import get_session
        with get_session() as ns:
            result = ns.run("MATCH ...")

    Returns:
        A ``neo4j.Session`` context manager.
    """
    _ensure_driver()
    return db.driver.session(
        notifications_min_severity=NotificationMinimumSeverity.WARNING,
        notifications_disabled_categories=[
            NotificationDisabledCategory.UNRECOGNIZED,
        ],
    )


def cypher_query(query: str, params: dict | None = None) -> tuple[list[Any], dict]:
    """Run a Cypher query via neomodel's built-in query runner.

    Convenience wrapper around :func:`neomodel.db.cypher_query`.
    Returns the same ``(results, meta)`` tuple.

    Args:
        query: Cypher query string.
        params: Optional dict of query parameters.

    Returns:
        A ``(results, meta)`` tuple where *results* is a list of
        records and *meta* contains column names and statistics.
    """
    _ensure_driver()
    if params:
        return db.cypher_query(query, params)
    return db.cypher_query(query)


def verify_connectivity() -> bool:
    """Check that Neo4j is reachable.

    Returns:
        True if the connection is working, False otherwise.
    """
    try:
        _ensure_driver()
        db.cypher_query("RETURN 1")
        return True
    except Exception:
        log.warning("Neo4j connectivity check failed", exc_info=True)
        return False


def require_connection() -> None:
    """Verify Neo4j is reachable; raise if not.

    Call this at the top of any entry point that needs Neo4j.
    Produces a clear error message instead of a cryptic stack
    trace deep inside neomodel/the Neo4j driver.

    Raises:
        Neo4jUnavailableError: If Neo4j is not reachable.
    """
    _ensure_driver()
    try:
        db.cypher_query("RETURN 1")
    except Exception as exc:
        raise Neo4jUnavailableError(
            f"Cannot execute query against Neo4j: {exc}\n"
            "Is Neo4j running? Start it with: docker compose up -d"
        ) from exc


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j is not reachable."""


def _ensure_driver() -> None:
    """Ensure neomodel's driver is initialised.

    Neomodel lazily creates the driver on first use, but some operations
    (like ``db.driver.session()``) require it to exist.  This forces
    initialisation if needed by calling ``db.set_connection()`` with the
    configured URL.

    Raises:
        Neo4jUnavailableError: If the driver cannot connect to Neo4j.
    """
    if db.driver is None:
        from codegraph.persistence.config import config

        if not config.database_url:
            raise Neo4jUnavailableError(
                "No Neo4j connection URL configured. "
                "Set NEO4J_URI environment variable."
            )

        try:
            db.set_connection(url=config.database_url)
        except Exception as exc:
            raise Neo4jUnavailableError(
                f"Cannot connect to Neo4j at {config.database_url}: {exc}\n"
                "Is Neo4j running? Start it with: docker compose up -d"
            ) from exc