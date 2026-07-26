"""Persistence layer for codegraph.

Provides Neo4j connection management, ORM data access, and Docker
container management for the codebase graph.

Modules
-------
- :mod:`config` — Neo4j connection configuration from environment.
- :mod:`connection` — direct Cypher session access via the Neo4j backend.
- :mod:`repository` — backend-agnostic read/write data access layer
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

# Backend access — re-export for convenience
from codegraph.backends import get_backend, set_backend
from codegraph.backends.neo4j import Neo4jBackend

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
    # Backend
    "get_backend",
    "set_backend",
    "Neo4jBackend",
]