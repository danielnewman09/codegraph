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

from typing import Any, override

from codegraph.backends.interface import Backend, BackendConfig, EdgeDescriptor
from codegraph.backends.neo4j.config import Neo4jConfig
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.graph_repository import Neo4jGraphRepository
from codegraph.backends.neo4j.memory_repository import Neo4jMemoryRepository
from codegraph.backends.neo4j.requirements_repository import Neo4jRequirementsRepository
from codegraph.backends.neo4j.node_ops import Neo4jNodeOps
from codegraph.backends.neo4j.rel_ops import Neo4jRelOps
from codegraph.backends.neo4j.bulk_ops import Neo4jBulkOps
from codegraph.models.tags import CodeGraphNode
from codegraph.graph import LayerGraph
from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.memory_repository import MemoryRepository
from codegraph.persistence.requirements_repository import RequirementsRepository


class Neo4jBackend(Backend):
    """Neo4j storage backend for the codegraph knowledge graph.

    Composes:
    - ``_conn`` — driver lifecycle + raw Cypher
    - ``_graph`` — Neo4jGraphRepository (code graph operations)
    - ``_memory`` — Neo4jMemoryRepository (design memory operations)
    - ``_requirements`` — Neo4jRequirementsRepository (HLR/LLR/test ops)
    """

    def __init__(self, config: Neo4jConfig | None = None):
        if config is None:
            config = Neo4jConfig.from_env()
        self._config = config
        self._conn = Neo4jConnection(config)
        self._graph = Neo4jGraphRepository(self._conn)
        self._memory = Neo4jMemoryRepository(self._conn, self._graph)
        self._requirements = Neo4jRequirementsRepository(self._conn, self._graph)
        self._node_ops = Neo4jNodeOps(self._conn)
        self._rel_ops = Neo4jRelOps(self._conn)
        self._bulk_ops = Neo4jBulkOps(self._conn, self._node_ops, self._rel_ops)

    # ── Lifecycle ────────────────────────────────────────────────────

    @override
    def initialize(self, config: BackendConfig) -> None:
        self._conn.ensure_driver()

    @override
    def health_check(self) -> bool:
        return self._conn.health_check()

    @override
    def close(self) -> None:
        """Close the Neo4j driver and release resources."""
        self._conn.close()

    @override
    def reconnect(self) -> None:
        """Re-establish the Neo4j connection with fresh env config."""
        self._conn.reconnect()

    # ── Repositories ────────────────────────────────────────────────

    @property
    @override
    def graph(self) -> GraphRepository:
        return self._graph

    @property
    @override
    def memory(self) -> MemoryRepository:
        return self._memory

    @property
    @override
    def requirements(self) -> RequirementsRepository:
        return self._requirements

    # ── Node CRUD (model-layer delegation) ─────────────────────────

    @override
    def save(self, node: CodeGraphNode) -> CodeGraphNode:
        return self._node_ops.save(node)

    @override
    def delete(self, node: CodeGraphNode) -> None:
        self._node_ops.delete(node)

    @override
    def get(
        self, node_type: type[CodeGraphNode], **filters: Any
    ) -> CodeGraphNode | None:
        return self._node_ops.get(node_type, **filters)

    @override
    def find_all(
        self, node_type: type[CodeGraphNode], **filters: Any
    ) -> list[CodeGraphNode]:
        return self._node_ops.find_all(node_type, **filters)

    @override
    def inflate(self, raw: Any, node_type: type[CodeGraphNode]) -> CodeGraphNode:
        return self._node_ops.inflate(raw, node_type)

    # ── Relationship operations (model-layer delegation) ──────────

    @override
    def connect(
        self, source: CodeGraphNode, rel_type: str, target: CodeGraphNode
    ) -> None:
        self._rel_ops.connect(source, rel_type, target)

    @override
    def disconnect(
        self, source: CodeGraphNode, rel_type: str, target: CodeGraphNode
    ) -> None:
        self._rel_ops.disconnect(source, rel_type, target)

    @override
    def get_composed_children(self, node: CodeGraphNode) -> list[CodeGraphNode]:
        return self._rel_ops.get_composed_children(node)

    @override
    def get_all_edges(self, node: CodeGraphNode) -> list[EdgeDescriptor]:
        return self._rel_ops.get_all_edges(node)

    @override
    def get_all_edges_outgoing(self, node: CodeGraphNode) -> list[EdgeDescriptor]:
        return self._rel_ops.get_all_edges_outgoing(node)

    # ── Bulk operations ──────────────────────────────────────────

    @override
    def bulk_save(self, layer_graph: LayerGraph) -> None:
        self._bulk_ops.bulk_save(layer_graph)

    @override
    def bulk_load_by_tag(self, tag: str) -> list[CodeGraphNode]:
        return self._bulk_ops.bulk_load_by_tag(tag)

    # ── Raw query ───────────────────────────────────────────────────

    @override
    def wipe(self) -> None:
        """Delete every node and relationship from Neo4j via DETACH DELETE."""
        self._conn.require_connection()
        self._conn.execute_raw("MATCH (n) DETACH DELETE n")

    @override
    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        return self._conn.execute_raw(query, params)
