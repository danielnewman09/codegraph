"""SQLite relationship operations.

Ports ``codegraph.backends.neo4j.rel_ops.Neo4jRelOps`` to SQL over the
``edges`` table.  Edges are INTEGER-FK rows with a UNIQUE
``(source_id, rel_type, target_id)`` triple, so MERGE semantics are
``INSERT OR IGNORE``; the composite indexes cover forward/backward
traversal and type-wide queries.
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from codegraph.backends.interface import EdgeDescriptor
from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.backends.sqlite.node_ops import (
    _row_to_node,
    best_class_for_labels,
)
from codegraph.models.tags import CodeGraphNode

log = logging.getLogger(__name__)


def _labels_for(cls: type) -> list[str]:
    """Return the inherited label chain for a node type."""
    return cls.inherited_labels()


class SqliteRelOps:
    """Relationship CRUD + traversal operations for the SQLite backend."""

    def __init__(self, conn: SqliteConnection):
        self._conn = conn

    # ── Relationship management ──────────────────────────────────────

    def connect(
        self,
        source: CodeGraphNode,
        rel_type: str,
        target: CodeGraphNode,
    ) -> None:
        """Create a relationship between two saved nodes.

        Idempotent (INSERT OR IGNORE on the UNIQUE triple).  Raises
        ValueError if either endpoint is unsaved — mirroring the Neo4j
        pure-Python path.
        """
        if not hasattr(source, "element_id_property") or not hasattr(target, "element_id_property"):
            raise ValueError(
                f"Cannot connect unsaved nodes: source saved="
                f"{hasattr(source, 'element_id_property')}, "
                f"target saved={hasattr(target, 'element_id_property')}"
            )
        with self._conn.session() as conn:
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO edges (source_id, rel_type, target_id) "
                    "VALUES (:sid, :rt, :tid)"
                ),
                {"sid": source.element_id_property, "rt": rel_type,
                 "tid": target.element_id_property},
            )

    def disconnect(
        self,
        source: CodeGraphNode,
        rel_type: str,
        target: CodeGraphNode,
    ) -> None:
        """Remove a single relationship between two nodes."""
        if not hasattr(source, "element_id_property") or not hasattr(target, "element_id_property"):
            return
        with self._conn.session() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM edges "
                    "WHERE source_id = :sid AND rel_type = :rt AND target_id = :tid"
                ),
                {"sid": source.element_id_property, "rt": rel_type,
                 "tid": target.element_id_property},
            )

    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """Idempotently create a relationship between two nodes by uid.

        Optionally sets *edge_properties* (JSON).  Returns 1 if both
        endpoints exist, 0 otherwise.
        """
        with self._conn.session() as conn:
            src_id = self._uid_to_id(conn, source_uid)
            tgt_id = self._uid_to_id(conn, target_uid)
            if src_id is None or tgt_id is None:
                return 0
            props_json = json.dumps(edge_properties or {})
            conn.execute(
                sa.text(
                    "INSERT INTO edges (source_id, rel_type, target_id, properties) "
                    "VALUES (:sid, :rt, :tid, :props) "
                    "ON CONFLICT(source_id, rel_type, target_id) DO UPDATE SET "
                    "properties = excluded.properties"
                ),
                {"sid": src_id, "rt": rel_type, "tid": tgt_id, "props": props_json},
            )
        return 1

    def _uid_to_id(self, conn, uid: str) -> int | None:
        row = conn.execute(
            sa.text("SELECT id FROM nodes WHERE uid = :uid"),
            {"uid": uid},
        ).first()
        return row[0] if row else None

    # ── Traversal ───────────────────────────────────────────────────

    def get_ancestors(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges upward from uid (depth 1..max_depth).

        Returns ``[{"uid": str, "labels": list[str]}]``.
        """
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "WITH RECURSIVE "
                        "anc(anc_id, depth) AS ( "
                        "  SELECT e.source_id, 1 FROM edges e "
                        "  JOIN nodes n ON n.id = e.target_id "
                        "  WHERE n.uid = :uid AND e.rel_type = 'COMPOSES' "
                        "  UNION ALL "
                        "  SELECT e.source_id, a.depth + 1 FROM edges e "
                        "  JOIN anc a ON e.target_id = a.anc_id "
                        "  WHERE e.rel_type = 'COMPOSES' AND a.depth < :maxd "
                        ") "
                        "SELECT n.uid AS uid, n.labels AS labels "
                        "FROM anc JOIN nodes n ON n.id = anc.anc_id "
                        "GROUP BY n.uid"
                    ),
                    {"uid": uid, "maxd": max_depth},
                )
            )
        return [
            {"uid": r[0], "labels": json.loads(r[1]) or []}
            for r in rows
        ]

    def get_descendants(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges downward from uid (depth 1..max_depth).

        Returns ``[{"uid": str, "labels": list[str]}]``.
        """
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "WITH RECURSIVE "
                        "desc(desc_id, depth) AS ( "
                        "  SELECT e.target_id, 1 FROM edges e "
                        "  JOIN nodes n ON n.id = e.source_id "
                        "  WHERE n.uid = :uid AND e.rel_type = 'COMPOSES' "
                        "  UNION ALL "
                        "  SELECT e.target_id, d.depth + 1 FROM edges e "
                        "  JOIN desc d ON e.source_id = d.desc_id "
                        "  WHERE e.rel_type = 'COMPOSES' AND d.depth < :maxd "
                        ") "
                        "SELECT n.uid AS uid, n.labels AS labels "
                        "FROM desc JOIN nodes n ON n.id = desc.desc_id "
                        "GROUP BY n.uid"
                    ),
                    {"uid": uid, "maxd": max_depth},
                )
            )
        return [
            {"uid": r[0], "labels": json.loads(r[1]) or []}
            for r in rows
        ]

    # ── Relationship queries ─────────────────────────────────────────

    def get_composed_children(
        self,
        node: CodeGraphNode,
    ) -> list[CodeGraphNode]:
        """Return all nodes reachable via outgoing COMPOSES edges."""
        if not hasattr(node, "element_id_property"):
            return []
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT t.id, t.uid, t.labels, t.properties "
                        "FROM edges e "
                        "JOIN nodes t ON t.id = e.target_id "
                        "WHERE e.source_id = :sid AND e.rel_type = 'COMPOSES'"
                    ),
                    {"sid": node.element_id_property},
                )
            )
            return [
                n for n in (_row_to_node(r, conn) for r in rows) if n is not None
            ]

    def get_all_edges(
        self,
        node: CodeGraphNode,
    ) -> list[EdgeDescriptor]:
        """Return ALL edges (incoming + outgoing) from node."""
        if not hasattr(node, "element_id_property"):
            return []
        return self._query_edges(node, outgoing=True) + self._query_edges(node, outgoing=False)

    def get_all_edges_outgoing(
        self,
        node: CodeGraphNode,
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges from node."""
        if not hasattr(node, "element_id_property"):
            return []
        return self._query_edges(node, outgoing=True)

    def _query_edges(
        self,
        node: CodeGraphNode,
        outgoing: bool,
    ) -> list[EdgeDescriptor]:
        """Query edges touching *node*, resolving target types by labels."""
        if outgoing:
            join_sql = "JOIN nodes t ON t.id = e.target_id"
            where_sql = "e.source_id = :sid"
        else:
            join_sql = "JOIN nodes t ON t.id = e.source_id"
            where_sql = "e.target_id = :sid"
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        f"SELECT e.rel_type AS rel_type, t.uid AS tuid, "
                        f"t.labels AS tlbls, e.properties AS eprops "
                        f"FROM edges e {join_sql} WHERE {where_sql}"
                    ),
                    {"sid": node.element_id_property},
                )
            )
        edges: list[EdgeDescriptor] = []
        for row in rows:
            rel_type, tuid, tlbls, eprops = row[0], row[1], row[2], row[3]
            labels = set(json.loads(tlbls) or [])
            target_type = "CodeGraphNode"
            best = best_class_for_labels(labels)
            if best is not None:
                target_type = best.__name__
            edges.append(EdgeDescriptor(
                relation_type=rel_type,
                target_uid=tuid,
                target_type=target_type,
                is_outgoing=outgoing,
                attributes=json.loads(eprops) if eprops else {},
            ))
        return edges
