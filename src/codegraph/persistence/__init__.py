"""Persistence layer for codegraph.

Provides ORM data access and Docker container management for the
codebase graph.  Connection and config logic lives in
``codegraph.backends.neo4j``.

Modules
-------
- :mod:`repository` — backend-agnostic read/write data access layer
  (:class:`GraphRepository`).
- :mod:`memory_repository` — data access layer for design memory nodes
  (:class:`MemoryRepository`).
- :mod:`docker` — project-local Neo4j Docker container management.
- :mod:`db_cli` — CLI entry point for ``codegraph-db``.
"""

from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.memory_repository import MemoryRepository

# Backend access — re-export for convenience
from codegraph.backends import get_backend, set_backend

__all__ = [
    # Repositories
    "GraphRepository",
    "MemoryRepository",
    # Backend
    "get_backend",
    "set_backend",
    "Neo4jBackend",
]


def __getattr__(name: str):
    """Lazy attribute access (PEP 562).

    ``Neo4jBackend`` is re-exported here for convenience, but importing
    it eagerly drags in the neo4j driver + neomodel on every
    ``import codegraph`` — even for sqlite-only runs.  Resolve it on
    demand so sqlite/memory users never load the Neo4j stack.
    """
    if name == "Neo4jBackend":
        from codegraph.backends.neo4j import Neo4jBackend

        return Neo4jBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
