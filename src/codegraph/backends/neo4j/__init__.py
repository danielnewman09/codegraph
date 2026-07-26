"""Neo4j backend — composes connection, config, node_ops, rel_ops, bulk_ops.

Usage::

    from codegraph.backends.neo4j import Neo4jBackend
    from codegraph.backends import set_backend

    backend = Neo4jBackend()
    set_backend(backend)
"""

from __future__ import annotations

from typing import Any

from codegraph.backends.interface import Backend, BackendConfig, EdgeDescriptor
from codegraph.backends.neo4j.config import Neo4jConfig
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.node_ops import Neo4jNodeOps
from codegraph.backends.neo4j.rel_ops import Neo4jRelOps
from codegraph.backends.neo4j.bulk_ops import Neo4jBulkOps
from codegraph.models.tags import CodeGraphNode
from codegraph.graph import LayerGraph



class Neo4jBackend(Backend):
    """Neo4j storage backend for the codegraph knowledge graph.

    Composes five specialised sub-operation objects:
    - ``_conn`` — driver lifecycle + raw Cypher
    - ``_node_ops`` — node CRUD + tag/source/kind queries
    - ``_rel_ops`` — relationship connect/disconnect/walk
    - ``_bulk_ops`` — LayerGraph bulk save/load
    """

    def __init__(self, config: Neo4jConfig | None = None):
        if config is None:
            config = Neo4jConfig.from_env()
        self._config = config
        self._conn = Neo4jConnection(config)
        self._node_ops = Neo4jNodeOps(self._conn)
        self._rel_ops = Neo4jRelOps(self._conn)
        self._bulk_ops = Neo4jBulkOps(self._conn, self._node_ops, self._rel_ops)

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self, config: BackendConfig) -> None:
        self._conn.ensure_driver()

    def health_check(self) -> bool:
        return self._conn.health_check()

    # ── Node CRUD ────────────────────────────────────────────────────

    def save(self, node: "CodeGraphNode") -> "CodeGraphNode":
        return self._node_ops.save(node)

    def delete(self, node: "CodeGraphNode") -> None:
        self._node_ops.delete(node)

    def get(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> "CodeGraphNode | None":
        return self._node_ops.get(node_type, **filters)

    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        return self._node_ops.inflate(raw, node_type)

    # ── Node queries ─────────────────────────────────────────────────

    def _find_by_tag_impl(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        return self._node_ops.find_by_tag(node_type, tag)

    def _find_all_by_tag_impl(self, tag: str) -> list["CodeGraphNode"]:
        return self._node_ops.find_all_by_tag(tag)

    def _find_all_by_source_impl(self, source: str) -> list["CodeGraphNode"]:
        return self._node_ops.find_all_by_source(source)

    def _find_all_by_kind_impl(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        return self._node_ops.find_all_by_kind(kind, tag)

    # ── Relationship operations ─────────────────────────────────────

    def connect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        self._rel_ops.connect(source, rel_type, target)

    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        self._rel_ops.disconnect(source, rel_type, target)

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        return self._rel_ops.get_composed_children(node)

    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        return self._rel_ops.get_all_edges(node)

    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        return self._rel_ops.get_all_edges_outgoing(node)

    # ── Bulk operations ─────────────────────────────────────────────

    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        self._bulk_ops.bulk_save(layer_graph)

    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        return self._bulk_ops.bulk_load_by_tag(tag)

    # ── Raw query ───────────────────────────────────────────────────

    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list, dict]:
        return self._conn.execute_raw(query, params)
