"""Neo4j backend — composes connection, config, and repository implementations.

Usage::

    from codegraph.backends.neo4j import Neo4jBackend
    from codegraph.backends import set_backend

    backend = Neo4jBackend()
    set_backend(backend)

    node = backend.graph.find_by_uid("abc123")
    memories = backend.memory.find_for_code_node("abc123")
"""

from __future__ import annotations

from typing import Any

from codegraph.backends.interface import Backend, BackendConfig, EdgeDescriptor
from codegraph.backends.neo4j.config import Neo4jConfig
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.graph_repository import Neo4jGraphRepository
from codegraph.backends.neo4j.memory_repository import Neo4jMemoryRepository
from codegraph.models.tags import CodeGraphNode
from codegraph.graph import LayerGraph
from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.memory_repository import MemoryRepository


class Neo4jBackend(Backend):
    """Neo4j storage backend for the codegraph knowledge graph.

    Composes:
    - ``_conn`` — driver lifecycle + raw Cypher
    - ``_graph`` — Neo4jGraphRepository (code graph operations)
    - ``_memory`` — Neo4jMemoryRepository (design memory operations)
    """

    def __init__(self, config: Neo4jConfig | None = None):
        if config is None:
            config = Neo4jConfig.from_env()
        self._config = config
        self._conn = Neo4jConnection(config)
        self._graph = Neo4jGraphRepository(self._conn)
        self._memory = Neo4jMemoryRepository(self._conn, self._graph)

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self, config: BackendConfig) -> None:
        self._conn.ensure_driver()

    def health_check(self) -> bool:
        return self._conn.health_check()

    # ── Repositories ────────────────────────────────────────────────

    @property
    def graph(self) -> GraphRepository:
        return self._graph

    @property
    def memory(self) -> MemoryRepository:
        return self._memory

    # ── Raw query ───────────────────────────────────────────────────

    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        return self._conn.execute_raw(query, params)
