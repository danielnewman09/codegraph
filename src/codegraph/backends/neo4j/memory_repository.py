"""Neo4jMemoryRepository — Neo4j implementation of the MemoryRepository
abstract interface.

Composes ``Neo4jMemoryOps`` + the graph repository (for uid resolution).
Composite queries use ``execute_raw()`` as an escape hatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from codegraph.backends import get_backend
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.memory_ops import Neo4jMemoryOps
from codegraph.persistence.memory_repository import MemoryRepository

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode
    from codegraph.persistence.repository import GraphRepository


class Neo4jMemoryRepository(MemoryRepository):
    """Neo4j implementation of the MemoryRepository interface."""

    MEMORY_LABELS = (
        "DecisionNode|ConstraintNode|RationaleNode|"
        "AssumptionNode|TradeoffNode|InsightNode"
    )
    MEMORY_REL_PATTERN = (
        "MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO"
    )

    def __init__(
        self,
        conn: Neo4jConnection,
        graph_repo: "GraphRepository",
    ):
        self._conn = conn
        self._graph = graph_repo
        self._memory_ops = Neo4jMemoryOps(conn)

    # ── Memory → code node queries ──────────────────────────────────

    @override
    def find_for_code_node(self, uid: str) -> list[dict]:
        results = self._memory_ops.find_related_nodes(
            uid,
            self.MEMORY_REL_PATTERN,
            source_labels=self.MEMORY_LABELS,
        )
        return [
            {"memory": r["node"], "rel_type": r["rel_type"]}
            for r in results
        ]

    @override
    def find_for_code_node_by_qname(
        self, qualified_name: str
    ) -> list[dict]:
        uid = self._graph.resolve_uid(qualified_name)
        if uid is None:
            return []
        return self.find_for_code_node(uid)

    # ── Memory nodes by tag ────────────────────────────────────────

    @override
    def find_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        rows, _ = self._conn.execute_raw(
            f"MATCH (m:{self.MEMORY_LABELS}) "
            "WHERE $tag IN m.tags RETURN m",
            {"tag": tag},
        )
        from codegraph_memory.models.relationships import _inflate_code_node
        nodes: list["CodeGraphNode"] = []
        for row in rows:
            node = _inflate_code_node(row["m"])
            if node is not None:
                nodes.append(node)
        return nodes

    # ── Memory-to-memory edges ─────────────────────────────────────

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
        self._graph.merge_labeled_relationship(
            source_uid, source_label, rel_type,
            target_uid, target_label,
        )

    # ── Composite traversal + memory queries ───────────────────────

    @override
    def find_linked_to_ancestors(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list[dict]:
        rows, _ = self._conn.execute_raw(
            f"MATCH (target)<-[:COMPOSES*1..{max_depth}]-(ancestor) "
            "WHERE target.uid = $uid "
            f"MATCH (m)-[r:{self.MEMORY_REL_PATTERN}]->(ancestor) "
            "RETURN ancestor.uid AS source_uid, m, type(r) AS rel_type",
            {"uid": uid},
        )
        from codegraph_memory.models.relationships import _inflate_code_node
        results: list[dict] = []
        for row in rows:
            memory = _inflate_code_node(row["m"])
            if memory is not None:
                results.append({
                    "memory": memory,
                    "source_uid": row["source_uid"],
                    "rel_type": row["rel_type"],
                })
        return results

    @override
    def find_linked_to_descendants(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list["CodeGraphNode"]:
        rows, _ = self._conn.execute_raw(
            f"MATCH (parent)-[:COMPOSES*0..{max_depth}]->(target) "
            "WHERE parent.uid = $uid "
            f"MATCH (m)-[:{self.MEMORY_REL_PATTERN}]->(target) "
            "RETURN DISTINCT m",
            {"uid": uid},
        )
        from codegraph_memory.models.relationships import _inflate_code_node
        nodes: list["CodeGraphNode"] = []
        for row in rows:
            node = _inflate_code_node(row["m"])
            if node is not None:
                nodes.append(node)
        return nodes

    # ── Full-text search ───────────────────────────────────────────

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
            labels=self.MEMORY_LABELS,
            tag=tag,
            limit=limit,
        )
        from codegraph_memory.models.relationships import _inflate_code_node
        output: list[dict] = []
        for r in results:
            node = r["node"]
            if node is not None:
                data = node.serialize()
                data["search_score"] = r.get("score", 0.0)
                output.append(data)
        return output

    # ── Memory ↔ code node linking ───────────────────────────────

    @override
    def link_to_code_node(
        self,
        memory_uid: str,
        code_uid: str,
        rel_type: str,
    ) -> None:
        self._conn.execute_raw(
            f"MATCH (m) WHERE m.uid = $mid "
            f"MATCH (c) WHERE c.uid = $cid "
            f"MERGE (m)-[:{rel_type}]->(c)",
            {"mid": memory_uid, "cid": code_uid},
        )

    @override
    def find_linked_code_node(
        self,
        memory_uid: str,
    ) -> dict | None:
        rows, _ = self._conn.execute_raw(
            "MATCH (m)-[r]->(c) "
            "WHERE m.uid = $mid "
            "AND NOT type(r) IN ['SUPERSEDES', 'CONTRADICTS', 'REFINES'] "
            "RETURN c.uid AS uid, c.qualified_name AS qualified_name, "
            "type(r) AS rel_type "
            "LIMIT 1",
            {"mid": memory_uid},
        )
        if rows:
            return rows[0]
        return None

    # ── Vector search ──────────────────────────────────────────────

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
            labels=self.MEMORY_LABELS,
            tag=tag,
            limit=limit,
        )
        from codegraph_memory.models.relationships import _inflate_code_node
        output: list[dict] = []
        for r in results:
            node = r["node"]
            if node is not None:
                data = node.serialize()
                data["similarity_score"] = r.get("score", 0.0)
                output.append(data)
        return output
