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
from codegraph.models.tags import CodeGraphNode


class Neo4jMemoryOps:
    """Memory-layer operations for the Neo4j backend.

    All methods operate by uid — the canonical cross-backend key.
    """

    def __init__(self, conn: Neo4jConnection):
        self._conn = conn

    # ── Memory→code edges: find related nodes ─────────────────────

    def find_related_nodes(
        self,
        target_uid: str,
        rel_pattern: str,
        *,
        source_labels: str | None = None,
    ) -> list[dict]:
        """Find source nodes that have a relationship matching
        *rel_pattern* to the code node identified by *target_uid*.

        *rel_pattern* is a pipe-separated relationship list, e.g.
        ``"MOTIVATES|CONSTRAINTS|EXPLAINS"``.

        Optionally restrict to source nodes with *source_labels*,
        e.g. ``"DecisionNode|ConstraintNode"``.

        Returns ``[{"node": CodeGraphNode, "rel_type": str}]``.
        """
        label_clause = f"m:{source_labels}" if source_labels else "m"
        results, _ = db.cypher_query(
            f"MATCH ({label_clause})-[r:{rel_pattern}]->(c) "
            "WHERE c.uid = $uid "
            "RETURN m, type(r) AS rel_type",
            {"uid": target_uid},
            resolve_objects=True,
        )
        nodes: list[dict] = []
        for row in results:
            node = CodeGraphNode.inflate(row[0])
            if node is not None:
                nodes.append({"node": node, "rel_type": row[1]})
        return nodes

    # ── Memory→memory edges: labeled MERGE ────────────────────────

    def merge_labeled_relationship(
        self,
        source_uid: str,
        source_label: str,
        rel_type: str,
        target_uid: str,
        target_label: str,
    ) -> None:
        """Idempotently create a relationship between two labeled nodes.

        The labels qualify the MATCH so that two nodes of different
        types with the same uid (which shouldn't happen, but is a
        safety net) are disambiguated.  Used for memory-to-memory
        edges: SUPERSEDES, REFINES, CONTRADICTS.
        """
        db.cypher_query(
            f"MATCH (n:`{source_label}`) WHERE n.uid = $suid "
            f"MATCH (o:`{target_label}`) WHERE o.uid = $tuid "
            f"MERGE (n)-[:{rel_type}]->(o)",
            {"suid": source_uid, "tuid": target_uid},
        )

    # ── Alias with canonical ordering (rel_type before labels) ───

    # NOTE: Backend.merge_relationship_by_labels() has a different
    # parameter order than merge_labeled_relationship().  Both methods
    # exist on the ABC and both delegate to the same Cypher here.
    def merge_relationship_by_labels(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        source_label: str,
        target_label: str,
    ) -> None:
        """Alias of merge_labeled_relationship with canonical ordering:
        (source_uid, rel_type, target_uid, source_label, target_label)."""
        self.merge_labeled_relationship(
            source_uid, source_label, rel_type, target_uid, target_label,
        )
