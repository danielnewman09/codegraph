"""Neo4j memory-layer operations.

Memory nodes (DecisionNode, ConstraintNode, RationaleNode, AssumptionNode,
TradeoffNode, InsightNode) link to code nodes via MOTIVATES, CONSTRAINS,
EXPLAINS, ASSUMES, TRADES_OFF, and INSIGHT_INTO relationships.  Memory-to-
memory edges use SUPERSEDES, REFINES, and CONTRADICTS.

These operations are separated from the main node/rel ops because they
deal with a distinct domain model that belongs to ``codegraph_memory``.
"""

from __future__ import annotations

from neomodel import db

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph_memory.models.relationships import _inflate_code_node


class Neo4jMemoryOps:
    """Memory-layer operations for the Neo4j backend.

    All methods operate by uid — the canonical cross-backend key.
    """

    def __init__(self, conn: Neo4jConnection):
        self._conn = conn

    # ── Memory→code edges: find related nodes ─────────────────────

    def find_related_nodes(
        self,
        target_key: str,
        rel_pattern: str,
        *,
        source_labels: str | None = None,
    ) -> list[dict]:
        """Find source nodes that have a relationship matching
        *rel_pattern* to the code node identified by *target_key*.

        *rel_pattern* is a pipe-separated relationship list, e.g.
        ``"MOTIVATES|CONSTRAINTS|EXPLAINS"``.

        Optionally restrict to source nodes with *source_labels*,
        e.g. ``"DecisionNode|ConstraintNode"``.

        Returns ``[{"node": CodeGraphNode, "rel_type": str}]``.
        """
        label_clause = f"m:{source_labels}" if source_labels else "m"
        results, _ = db.cypher_query(
            f"MATCH ({label_clause})-[r:{rel_pattern}]->(c) "
            "WHERE c.canonical_key = $key "
            "RETURN m, type(r) AS rel_type",
            {"uid": target_key},
        )
        nodes: list[dict] = []
        for row in results:
            node = _inflate_code_node(row[0])
            if node is not None:
                nodes.append({"node": node, "rel_type": row[1]})
        return nodes

    # ── Memory→memory edges: labeled MERGE ────────────────────────

    def merge_labeled_relationship(
        self,
        source_key: str,
        source_label: str,
        rel_type: str,
        target_key: str,
        target_label: str,
    ) -> None:
        """Idempotently create a relationship between two labeled nodes.

        The labels qualify the MATCH so that two nodes of different
        types with the same uid (which shouldn't happen, but is a
        safety net) are disambiguated.  Used for memory-to-memory
        edges: SUPERSEDES, REFINES, CONTRADICTS.
        """
        db.cypher_query(
            f"MATCH (n:`{source_label}`) WHERE n.canonical_key = $skey "
            f"MATCH (o:`{target_label}`) WHERE o.canonical_key = $tkey "
            f"MERGE (n)-[:{rel_type}]->(o)",
            {"suid": source_key, "tuid": target_key},
        )

    # ── Memory nodes by tag ─────────────────────────────────────

    MEMORY_LABELS = (
        "DecisionNode|ConstraintNode|RationaleNode|"
        "AssumptionNode|TradeoffNode|InsightNode"
    )

    def find_by_tag(self, tag: str) -> list:
        """Return all memory nodes with *tag*."""
        results, _ = db.cypher_query(
            f"MATCH (m:{self.MEMORY_LABELS}) "
            "WHERE $tag IN m.tags RETURN m",
            {"tag": tag},
        )
        nodes: list = []
        for row in results:
            node = _inflate_code_node(row[0])
            if node is not None:
                nodes.append(node)
        return nodes

    # ── Composite traversal + memory queries ─────────────────────

    MEMORY_REL_PATTERN = (
        "MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO"
    )

    def find_linked_to_ancestors(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list[dict]:
        """Find memory nodes linked to ancestors of *uid* (COMPOSES↑)."""
        results, _ = db.cypher_query(
            f"MATCH (target)<-[:COMPOSES*1..{max_depth}]-(ancestor) "
            "WHERE target.canonical_key = $key "
            f"MATCH (m)-[r:{self.MEMORY_REL_PATTERN}]->(ancestor) "
            "RETURN ancestor.canonical_key AS source_key, m, type(r) AS rel_type",
            {"uid": uid},
        )
        nodes: list[dict] = []
        for row in results:
            memory = _inflate_code_node(row[1])
            if memory is not None:
                nodes.append({
                    "memory": memory,
                    "source_key": row[0],
                    "rel_type": row[2],
                })
        return nodes

    def find_linked_to_descendants(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list:
        """Find memory nodes linked to descendants of *uid* (COMPOSES↓)."""
        results, _ = db.cypher_query(
            f"MATCH (parent)-[:COMPOSES*0..{max_depth}]->(target) "
            "WHERE parent.canonical_key = $key "
            f"MATCH (m)-[:{self.MEMORY_REL_PATTERN}]->(target) "
            "RETURN DISTINCT m",
            {"uid": uid},
        )
        nodes: list = []
        for row in results:
            node = _inflate_code_node(row[0])
            if node is not None:
                nodes.append(node)
        return nodes

    # ── Memory ↔ code node linking ───────────────────────────────

    def link_to_code_node(
        self,
        memory_uid: str,
        code_uid: str,
        rel_type: str,
    ) -> None:
        """MERGE a relationship from memory node to code node."""
        db.cypher_query(
            f"MATCH (m) WHERE m.canonical_key = $mkey "
            f"MATCH (c) WHERE c.canonical_key = $ckey "
            f"MERGE (m)-[:{rel_type}]->(c)",
            {"mid": memory_uid, "cid": code_uid},
        )

    def find_linked_code_node(
        self,
        memory_uid: str,
    ) -> dict | None:
        """Find the code node linked to a memory node (non-meta edge)."""
        results, _ = db.cypher_query(
            "MATCH (m)-[r]->(c) "
            "WHERE m.canonical_key = $mkey "
            "AND NOT type(r) IN ['SUPERSEDES', 'CONTRADICTS', 'REFINES'] "
            "RETURN c.canonical_key AS uid, c.qualified_name AS qn, type(r) AS rel_type "
            "LIMIT 1",
            {"mid": memory_uid},
        )
        if results:
            r = results[0]
            return {"uid": r[0], "qualified_name": r[1], "rel_type": r[2]}
        return None

    # ── Alias with canonical ordering (rel_type before labels) ───

    # NOTE: Backend.merge_relationship_by_labels() has a different
    # parameter order than merge_labeled_relationship().  Both methods
    # exist on the ABC and both delegate to the same Cypher here.
    def merge_relationship_by_labels(
        self,
        source_key: str,
        rel_type: str,
        target_key: str,
        source_label: str,
        target_label: str,
    ) -> None:
        """Alias of merge_labeled_relationship with canonical ordering:
        (source_key, rel_type, target_key, source_label, target_label)."""
        self.merge_labeled_relationship(
            source_key, source_label, rel_type, target_key, target_label,
        )
