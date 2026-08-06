"""SQLite memory-layer operations.

Memory nodes (DecisionNode, ConstraintNode, RationaleNode, AssumptionNode,
TradeoffNode, InsightNode) link to code nodes via MOTIVATES, CONSTRAINS,
EXPLAINS, ASSUMES, TRADES_OFF, and INSIGHT_INTO.  Memory-to-memory edges
use SUPERSEDES, REFINES, and CONTRADICTS.

Ports ``codegraph.backends.neo4j.memory_ops.Neo4jMemoryOps`` to SQL.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.backends.sqlite.node_ops import _row_to_node

log = logging.getLogger(__name__)

# TODO: These should be defined in codegraph memory and imported from there
MEMORY_LABELS = "DecisionNode|ConstraintNode|RationaleNode|AssumptionNode|TradeoffNode|InsightNode"
MEMORY_REL_PATTERN = "MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO"


def _rel_list(pattern: str) -> list[str]:
    """Split a pipe-separated relationship pattern into a list."""
    return [r for r in pattern.split("|") if r]


class SqliteMemoryOps:
    """Memory-layer operations for the SQLite backend.

    All methods operate by uid — the canonical cross-backend key.
    """

    MEMORY_LABELS = MEMORY_LABELS
    MEMORY_REL_PATTERN = MEMORY_REL_PATTERN

    def __init__(self, conn: SqliteConnection):
        self._conn = conn

    # ── Memory→code edges: find related nodes ─────────────────────

    def find_related_nodes(
        self,
        target_uid: str,
        rel_pattern: str,
        *,
        source_labels: str | None = None,
    ) -> list[dict]:
        """Find source nodes with a relationship matching *rel_pattern*
        to the node identified by *target_uid*.

        Returns ``[{"node": CodeGraphNode, "rel_type": str}]``.
        """
        rels = _rel_list(rel_pattern)
        if not rels:
            return []
        rel_binds = ", ".join(f":r{i}" for i in range(len(rels)))
        params: dict = {f"r{i}": r for i, r in enumerate(rels)}
        params["tuid"] = target_uid
        sql = (
            "SELECT m.id, m.uid, m.labels, m.properties, e.rel_type AS rel_type "
            "FROM edges e "
            "JOIN nodes m ON m.id = e.source_id "
            "JOIN nodes t ON t.id = e.target_id "
            f"WHERE t.uid = :tuid AND e.rel_type IN ({rel_binds}) "
        )
        if source_labels:
            labels = _rel_list(source_labels)
            lbl_binds = ", ".join(f":l{i}" for i in range(len(labels)))
            sql += "AND EXISTS (SELECT 1 FROM node_labels nl WHERE nl.node_id = m.id " \
                   f"AND nl.label IN ({lbl_binds})) "
            params.update({f"l{i}": l for i, l in enumerate(labels)})
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), params))
        nodes: list[dict] = []
        from codegraph.backends.sqlite.connection import row_to_dict

        for row in rows:
            d = row_to_dict(row)
            node = _row_to_node(row, conn)
            if node is not None:
                nodes.append({"node": node, "rel_type": d["rel_type"]})
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

        Labels are advisory in SQLite (uid is unique); the UNIQUE edge
        triple gives MERGE semantics.
        """
        with self._conn.session() as conn:
            src = conn.execute(
                sa.text("SELECT id FROM nodes WHERE uid = :uid"), {"uid": source_uid}
            ).first()
            tgt = conn.execute(
                sa.text("SELECT id FROM nodes WHERE uid = :uid"), {"uid": target_uid}
            ).first()
            if src is None or tgt is None:
                return
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO edges (source_id, rel_type, target_id) "
                    "VALUES (:sid, :rt, :tid)"
                ),
                {"sid": src[0], "rt": rel_type, "tid": tgt[0]},
            )

    # ── Memory nodes by tag ─────────────────────────────────────

    def find_by_tag(self, tag: str) -> list:
        """Return all memory nodes with *tag*."""
        labels = _rel_list(MEMORY_LABELS)
        lbl_binds = ", ".join(f":l{i}" for i in range(len(labels)))
        sql = (
            "SELECT DISTINCT n.id, n.uid, n.labels, n.properties FROM nodes n "
            "JOIN node_labels nl ON nl.node_id = n.id "
            "JOIN node_tags nt ON nt.node_id = n.id "
            f"WHERE nl.label IN ({lbl_binds}) AND nt.tag = :tag"
        )
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(sa.text(sql), {**{f"l{i}": l for i, l in enumerate(labels)}, "tag": tag})
            )
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    # ── Composite traversal + memory queries ─────────────────────

    def find_linked_to_ancestors(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list[dict]:
        """Find memory nodes linked to ancestors of *uid* (COMPOSES↑).

        Returns ``[{memory, source_uid, rel_type}]``.
        """
        rels = _rel_list(MEMORY_REL_PATTERN)
        rel_binds = ", ".join(f":r{i}" for i in range(len(rels)))
        params: dict = {f"r{i}": r for i, r in enumerate(rels)}
        params["uid"] = uid
        params["maxd"] = max_depth
        sql = (
            "WITH RECURSIVE anc(anc_id, depth) AS ( "
            "  SELECT e.source_id, 1 FROM edges e "
            "  JOIN nodes n ON n.id = e.target_id "
            "  WHERE n.uid = :uid AND e.rel_type = 'COMPOSES' "
            "  UNION ALL "
            "  SELECT e.source_id, a.depth + 1 FROM edges e "
            "  JOIN anc a ON e.target_id = a.anc_id "
            "  WHERE e.rel_type = 'COMPOSES' AND a.depth < :maxd "
            ") "
            "SELECT a.anc_id AS source_id, n.uid AS source_uid, "
            "m.id AS id, m.uid AS uid, "
            "m.labels AS labels, m.properties AS properties, "
            "e.rel_type AS rel_type "
            "FROM anc a "
            "JOIN nodes n ON n.id = a.anc_id "
            "JOIN edges e ON e.target_id = a.anc_id "
            "JOIN nodes m ON m.id = e.source_id "
            f"WHERE e.rel_type IN ({rel_binds})"
        )
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), params))
        results: list[dict] = []
        from codegraph.backends.sqlite.connection import row_to_dict

        for row in rows:
            d = row_to_dict(row)
            memory = _row_to_node(row, conn)
            if memory is not None:
                results.append({
                    "memory": memory,
                    "source_uid": d["source_uid"],
                    "rel_type": d["rel_type"],
                })
        return results

    def find_linked_to_descendants(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list:
        """Find distinct memory nodes linked to descendants of *uid*
        (COMPOSES↓, including *uid* itself at depth 0)."""
        rels = _rel_list(MEMORY_REL_PATTERN)
        rel_binds = ", ".join(f":r{i}" for i in range(len(rels)))
        params: dict = {f"r{i}": r for i, r in enumerate(rels)}
        params["uid"] = uid
        params["maxd"] = max_depth
        sql = (
            "WITH RECURSIVE desc(desc_id, depth) AS ( "
            "  SELECT n.id, 0 FROM nodes n WHERE n.uid = :uid "
            "  UNION ALL "
            "  SELECT e.target_id, d.depth + 1 FROM edges e "
            "  JOIN desc d ON e.source_id = d.desc_id "
            "  WHERE e.rel_type = 'COMPOSES' AND d.depth < :maxd "
            ") "
            "SELECT DISTINCT m.id AS id, m.uid AS uid, m.labels AS labels, "
            "m.properties AS properties "
            "FROM desc d "
            "JOIN edges e ON e.target_id = d.desc_id "
            "JOIN nodes m ON m.id = e.source_id "
            f"WHERE e.rel_type IN ({rel_binds})"
        )
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), params))
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    # ── Memory ↔ code node linking ───────────────────────────────

    def link_to_code_node(
        self,
        memory_uid: str,
        code_uid: str,
        rel_type: str,
    ) -> None:
        """MERGE a relationship from memory node to code node."""
        with self._conn.session() as conn:
            src = conn.execute(
                sa.text("SELECT id FROM nodes WHERE uid = :uid"), {"uid": memory_uid}
            ).first()
            tgt = conn.execute(
                sa.text("SELECT id FROM nodes WHERE uid = :uid"), {"uid": code_uid}
            ).first()
            if src is None or tgt is None:
                return
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO edges (source_id, rel_type, target_id) "
                    "VALUES (:sid, :rt, :tid)"
                ),
                {"sid": src[0], "rt": rel_type, "tid": tgt[0]},
            )

    def find_linked_code_node(
        self,
        memory_uid: str,
    ) -> dict | None:
        """Find the code node linked to a memory node (non-meta edge)."""
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT t.uid AS uid, t.qualified_name AS qn, e.rel_type AS rel_type "
                    "FROM edges e "
                    "JOIN nodes m ON m.id = e.source_id "
                    "JOIN nodes t ON t.id = e.target_id "
                    "WHERE m.uid = :mid "
                    "AND e.rel_type NOT IN ('SUPERSEDES', 'CONTRADICTS', 'REFINES') "
                    "LIMIT 1"
                ),
                {"mid": memory_uid},
            ).first()
        if row is None:
            return None
        return {"uid": row[0], "qualified_name": row[1], "rel_type": row[2]}
