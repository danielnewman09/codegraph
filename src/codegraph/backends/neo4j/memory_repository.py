"""Neo4jMemoryRepository — Neo4j implementation of the MemoryRepository
abstract interface.

All Cypher is sealed inside ``Neo4jMemoryOps`` + delegated graph ops.
No raw query strings in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.memory_ops import Neo4jMemoryOps
from codegraph.persistence.memory_repository import MemoryRepository

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode
    from codegraph.persistence.repository import GraphRepository


class Neo4jMemoryRepository(MemoryRepository):
    """Neo4j implementation of the MemoryRepository interface."""

    def __init__(
        self,
        conn: Neo4jConnection,
        graph_repo: "GraphRepository",
    ):
        self._conn = conn
        self._graph = graph_repo
        self._memory_ops = Neo4jMemoryOps(conn)

    # ── Memory → code node queries (delegate to memory_ops) ───────

    @override
    def find_for_code_node(self, uid: str) -> list[dict]:
        return self._memory_ops.find_related_nodes(
            uid,
            Neo4jMemoryOps.MEMORY_REL_PATTERN,
            source_labels=Neo4jMemoryOps.MEMORY_LABELS,
        )

    @override
    def find_for_code_node_by_qname(
        self, qualified_name: str
    ) -> list[dict]:
        uid = self._graph.resolve_uid(qualified_name)
        if uid is None:
            return []
        return self.find_for_code_node(uid)

    # ── Memory nodes by tag (delegate to memory_ops) ─────────────

    @override
    def find_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        return self._memory_ops.find_by_tag(tag)

    # ── Memory-to-memory edges (delegate to memory_ops via graph) ─

    @override
    def merge_edge(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        source_label: str,
        target_label: str,
    ) -> None:
        self._memory_ops.merge_labeled_relationship(
            source_uid, source_label, rel_type,
            target_uid, target_label,
        )

    # ── Composite traversal + memory queries (delegate to memory_ops)

    @override
    def find_linked_to_ancestors(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list[dict]:
        return self._memory_ops.find_linked_to_ancestors(
            uid, max_depth=max_depth,
        )

    @override
    def find_linked_to_descendants(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list["CodeGraphNode"]:
        return self._memory_ops.find_linked_to_descendants(
            uid, max_depth=max_depth,
        )

    # ── Full-text search (delegate to graph ops) ──────────────────

    @override
    def search_content(
        self,
        query: str,
        limit: int = 20,
        tag: str | None = None,
    ) -> list[dict]:
        results = self._graph.search_fulltext(
            query,
            index_name="memory_search",
            labels=Neo4jMemoryOps.MEMORY_LABELS,
            tag=tag,
            limit=limit,
        )
        output: list[dict] = []
        for r in results:
            node = r["node"]
            if node is not None:
                data = node.serialize()
                data["search_score"] = r.get("score", 0.0)
                output.append(data)
        return output

    # ── Memory ↔ code node linking (delegate to memory_ops) ──────

    @override
    def link_to_code_node(
        self,
        memory_uid: str,
        code_uid: str,
        rel_type: str,
    ) -> None:
        self._memory_ops.link_to_code_node(
            memory_uid, code_uid, rel_type,
        )

    @override
    def find_linked_code_node(
        self,
        memory_uid: str,
    ) -> dict | None:
        return self._memory_ops.find_linked_code_node(memory_uid)

    # ── Vector search (delegate to graph ops) ─────────────────────

    @override
    def search_semantic(
        self,
        embedding: list[float],
        limit: int = 10,
        tag: str | None = None,
    ) -> list[dict]:
        if not embedding:
            return []
        results = self._graph.search_vector(
            embedding,
            index_name="memory_embedding",
            labels=Neo4jMemoryOps.MEMORY_LABELS,
            tag=tag,
            limit=limit,
        )
        output: list[dict] = []
        for r in results:
            node = r["node"]
            if node is not None:
                data = node.serialize()
                data["similarity_score"] = r.get("score", 0.0)
                output.append(data)
        return output
