"""Persistence layer for codegraph.

Provides Neo4j connection management, ORM data access, and Docker
container management for the codebase graph.

Modules
-------
- :mod:`config` — Neo4j connection configuration from environment.
- :mod:`connection` — direct Cypher session access via neomodel.
- :mod:`repository` — ORM-based read/write data access layer
  (:class:`GraphRepository`).
- :mod:`docker` — project-local Neo4j Docker container management.
- :mod:`db_cli` — CLI entry point for ``codegraph-db``.
"""

from codegraph.persistence.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.persistence.connection import (
    cypher_query,
    get_session,
    verify_connectivity,
)
from codegraph.persistence.repository import GraphRepository

__all__ = [
    # Config
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    # Connection
    "get_session",
    "cypher_query",
    "verify_connectivity",
    # Repository
    "GraphRepository",
]