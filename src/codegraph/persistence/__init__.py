"""Persistence layer for codegraph.

Provides ORM data access and Docker container management for the
codebase graph.  Connection and config logic lives in
``codegraph.backends.neo4j``.

Modules
-------
- :mod:`repository` — backend-agnostic read/write data access layer
  (:class:`GraphRepository`).
- :mod:`docker` — project-local Neo4j Docker container management.
- :mod:`db_cli` — CLI entry point for ``codegraph-db``.
"""

from codegraph.persistence.repository import GraphRepository

# Backend access — re-export for convenience
from codegraph.backends import get_backend, set_backend
from codegraph.backends.neo4j import Neo4jBackend

__all__ = [
    # Repository
    "GraphRepository",
    # Backend
    "get_backend",
    "set_backend",
    "Neo4jBackend",
]
