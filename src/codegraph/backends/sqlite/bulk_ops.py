"""SQLite bulk operations — save/load LayerGraphs.

Ports ``codegraph.backends.neo4j.bulk_ops.Neo4jBulkOps`` with a batched
write path: ``executemany`` upserts in a single transaction, edges +
label/tag rows rebuilt in the same transaction, WAL + synchronous=NORMAL
for fast commits.
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.backends.sqlite.node_ops import (
    SqliteNodeOps,
    _EMBEDDING_PROPS,
    _SEARCHABLE_TEXT_PROPS,
    _node_labels,
    _serialize_props,
)
from codegraph.backends.sqlite.rel_ops import SqliteRelOps
from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode

log = logging.getLogger(__name__)


class SqliteBulkOps:
    """Bulk save/load operations for LayerGraph <-> SQLite."""

    def __init__(
        self,
        conn: SqliteConnection,
        node_ops: SqliteNodeOps,
        rel_ops: SqliteRelOps,
    ):
        self._conn = conn
        self._node_ops = node_ops
        self._rel_ops = rel_ops

    def bulk_save(self, layer_graph: LayerGraph) -> None:
        """Persist all nodes and relationships in a LayerGraph.

        Phase 1: batch-upsert every node (one transaction, executemany),
        resolving the INTEGER PKs back onto the instances.  Phase 2:
        connect COMPOSES children and reference edges in the same
        transaction.
        """
        entries = list(layer_graph._all_entries())
        if not entries:
            return

        # Indexes for resolving reference targets by key or qualified_name.
        flat: dict[str, object] = {}
        qname_index: dict[str, object] = {}
        for entry in entries:
            key = LayerGraph._node_key(entry.node)
            flat[key] = entry
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                qname_index[qname] = entry

        with self._conn.session() as conn:
            # ── Phase 1: nodes ────────────────────────────────────
            node_rows = [
                {
                    "uid": _prep_uid(entry.node),
                    "labels": json.dumps(_node_labels(type(entry.node))),
                    "properties": json.dumps(_serialize_props(entry.node)),
                }
                for entry in entries
            ]
            conn.execute(
                sa.text(
                    "INSERT INTO nodes (uid, labels, properties) "
                    "VALUES (:uid, :labels, :properties) "
                    "ON CONFLICT(uid) DO UPDATE SET "
                    # Merge (Neo4j ``SET n += $props``): new keys win,
                    # existing keys not re-ingested are preserved; labels
                    # are only mutated via set_labels().
                    "properties = json_patch(nodes.properties, excluded.properties)"
                ),
                node_rows,
            )

            # Resolve uid → id and stamp element_id_property, capturing
            # the STORED labels + merged properties for the mirror tables.
            uids = [r["uid"] for r in node_rows]
            binds = ", ".join(f":u{i}" for i in range(len(uids)))
            id_rows = list(
                conn.execute(
                    sa.text(
                        f"SELECT id, uid, labels, properties FROM nodes "
                        f"WHERE uid IN ({binds})"
                    ),
                    {f"u{i}": u for i, u in enumerate(uids)},
                )
            )
            uid_to_id: dict[str, int] = {}
            stored: dict[int, dict] = {}
            for r in id_rows:
                uid_to_id[r[1]] = r[0]
                stored[r[0]] = {
                    "labels": json.loads(r[2]) or [],
                    "props": json.loads(r[3] or "{}"),
                }
            # Stamp every entry by its (possibly colliding) uid — entries
            # sharing a uid MERGE to the same DB row, mirroring Neo4j's
            # MERGE-on-uid save semantics.
            for entry in entries:
                entry.node.element_id_property = uid_to_id[entry.node.uid]

            # ── Phase 2: relationships ────────────────────────────
            edge_rows: list[dict] = []
            seen_edges: set[tuple[int, str, int]] = set()
            label_rows: list[dict] = []
            tag_rows: list[dict] = []
            fts_rows: list[dict] = []
            emb_rows: list[dict] = []

            def _edge(src_id: int, rel_type: str, tgt_id: int) -> None:
                key = (src_id, rel_type, tgt_id)
                if key in seen_edges:
                    return
                seen_edges.add(key)
                edge_rows.append({"sid": src_id, "rt": rel_type, "tid": tgt_id})

            for entry in entries:
                src_id = entry.node.element_id_property
                node_data = stored.get(src_id, {"labels": [], "props": {}})
                label_rows.extend(
                    {"nid": src_id, "lbl": l}
                    for l in node_data["labels"]
                )
                tag_rows.extend(
                    {"nid": src_id, "tag": t}
                    for t in (node_data["props"].get("tags") or [])
                )

                for _target_type, type_children in entry.children.items():
                    for _child_key, child_entry in type_children.items():
                        _edge(src_id, "COMPOSES", child_entry.node.element_id_property)

                for relation_type, target_key, _target_type in entry.references:
                    target_entry = flat.get(target_key) or qname_index.get(target_key)
                    if target_entry is not None:
                        _edge(src_id, relation_type, target_entry.node.element_id_property)

                # Derived-store rows collected here so the FTS/embedding
                # maintenance below is batched (one pass over entries).
                props = node_data["props"]
                fts_rows.append(
                    {
                        "uid": entry.node.uid,
                        "content": " ".join(
                            str(props[p])
                            for p in _SEARCHABLE_TEXT_PROPS
                            if props.get(p)
                        ),
                        "qname": str(props.get("qualified_name", "") or ""),
                        "tags": " ".join(str(t) for t in (props.get("tags") or [])),
                    }
                )
                emb_name = next((p for p in _EMBEDDING_PROPS if p in props), None)
                if emb_name is not None and props.get(emb_name):
                    from codegraph.backends.sqlite.search import pack_embedding

                    emb_rows.append(
                        {
                            "nid": src_id,
                            "dim": len(props[emb_name]),
                            "blob": pack_embedding(props[emb_name]),
                        }
                    )

            # ── Mirror tables: labels + tags ───────────────────────
            # Scoped per-node (matching ``_sync_labels``/``_sync_tags``
            # in node_ops): only THIS batch's rows are replaced, so
            # nodes persisted by earlier ``bulk_save`` calls keep their
            # label/tag mirror rows.  A blanket ``DELETE FROM
            # node_labels`` would erase the labels/tags of every other
            # node in the store on each incremental ingest.
            batch_ids = sorted(
                {entry.node.element_id_property for entry in entries}
            )
            for table in ("node_labels", "node_tags"):
                for chunk in _chunks(batch_ids, _DELETE_CHUNK):
                    binds = ", ".join(f":n{i}" for i in range(len(chunk)))
                    conn.execute(
                        sa.text(
                            f"DELETE FROM {table} WHERE node_id IN ({binds})"
                        ),
                        {f"n{i}": nid for i, nid in enumerate(chunk)},
                    )
            if label_rows:
                conn.execute(
                    sa.text(
                        "INSERT OR IGNORE INTO node_labels (node_id, label) "
                        "VALUES (:nid, :lbl)"
                    ),
                    label_rows,
                )
            if tag_rows:
                conn.execute(
                    sa.text(
                        "INSERT OR IGNORE INTO node_tags (node_id, tag) "
                        "VALUES (:nid, :tag)"
                    ),
                    tag_rows,
                )
            if edge_rows:
                conn.execute(
                    sa.text(
                        "INSERT OR IGNORE INTO edges (source_id, rel_type, target_id) "
                        "VALUES (:sid, :rt, :tid)"
                    ),
                    edge_rows,
                )

            # Derived stores (FTS shadow table + embeddings) refreshed in
            # the same transaction, from the STORED merged properties so
            # re-ingested nodes keep preserved fields.
            #
            # Batched (was per-node): a per-node ``DELETE FROM fts_nodes
            # WHERE uid = :uid`` forces a full FTS5 index scan per row —
            # FTS5 virtual tables cannot seek on a non-rowid column —
            # i.e. O(n²) index visits and minutes at 57k nodes.  Chunked
            # IN-deletes keep the identical per-node semantics at O(n)
            # index visits.
            fts_uids = [r["uid"] for r in fts_rows]
            for chunk in _chunks(fts_uids, _DELETE_CHUNK):
                binds = ", ".join(f":u{i}" for i in range(len(chunk)))
                conn.execute(
                    sa.text(f"DELETE FROM fts_nodes WHERE uid IN ({binds})"),
                    {f"u{i}": u for i, u in enumerate(chunk)},
                )
            if fts_rows:
                conn.execute(
                    sa.text(
                        "INSERT INTO fts_nodes (uid, content, qualified_name, tags) "
                        "VALUES (:uid, :content, :qname, :tags)"
                    ),
                    fts_rows,
                )

            emb_ids = [r["nid"] for r in emb_rows]
            for chunk in _chunks(emb_ids, _DELETE_CHUNK):
                binds = ", ".join(f":n{i}" for i in range(len(chunk)))
                conn.execute(
                    sa.text(f"DELETE FROM node_embeddings WHERE node_id IN ({binds})"),
                    {f"n{i}": c for i, c in enumerate(chunk)},
                )
            if emb_rows:
                conn.execute(
                    sa.text(
                        "INSERT INTO node_embeddings (node_id, dim, embedding, updated_at) "
                        "VALUES (:nid, :dim, :blob, unixepoch())"
                    ),
                    emb_rows,
                )

    def bulk_load_by_tag(self, tag: str) -> list[CodeGraphNode]:
        """Load all nodes with *tag* plus 1-hop neighbors.

        Returns a flat list of nodes; tree construction is done by
        ``LayerGraph.from_backend()``.
        """
        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}
        seen_uids: set[str] = set()

        matched_nodes = self._node_ops.find_all_by_tag(tag)

        for node in matched_nodes:
            key = LayerGraph._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key
                seen_uids.add(uid)

        # Expand to first-level neighbors.
        for node in matched_nodes:
            for edge in self._rel_ops.get_all_edges(node):
                if edge.relation_type == "HAS_IMPLEMENTATION":
                    continue
                target_uid = edge.target_uid
                target_type = edge.target_type
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        neighbor = self._node_ops.get(target_cls, uid=target_uid)
                        if neighbor:
                            neighbor_key = LayerGraph._node_key(neighbor)
                            nodes[neighbor_key] = neighbor
                            uid_to_key[target_uid] = neighbor_key

        # Second pass: pull in namespace parents of non-project 1-hop neighbours.
        initial_uids = {n._uid_value() for n in matched_nodes}
        for node in list(nodes.values()):
            if node._uid_value() in initial_uids:
                continue
            for edge in self._rel_ops.get_all_edges(node):
                if edge.relation_type != "COMPOSES":
                    continue
                if edge.is_outgoing:
                    continue  # only interested in incoming (parent→ns)
                target_uid = edge.target_uid
                target_type = edge.target_type
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        parent_ns = self._node_ops.get(target_cls, uid=target_uid)
                        if parent_ns:
                            ns_key = LayerGraph._node_key(parent_ns)
                            nodes[ns_key] = parent_ns
                            uid_to_key[target_uid] = ns_key

        return list(nodes.values())


def _chunks(items: list, size: int) -> list[list]:
    """Split *items* into consecutive chunks of at most *size*."""
    return [items[i : i + size] for i in range(0, len(items), size)]


# IN-clause delete batch size.  The mirror-table/FTS/embedding deletes
# run ``DELETE ... WHERE id IN (...`` per chunk; one statement per chunk
# keeps SQLAlchemy compile overhead low while staying far under every
# SQLite build's SQLITE_MAX_VARIABLE_NUMBER (32766 default; this build
# raises it to 250000).
_DELETE_CHUNK = 5000


def _prep_uid(node: CodeGraphNode) -> str:
    """Compute and stamp the uid before batching the row."""
    node_type = type(node)
    from codegraph.models.descriptors import PropertyRegistry

    if (PropertyRegistry.has_property(node_type, "qualified_name")
            and not getattr(node, "qualified_name", "")):
        node.qualified_name = node._compute_qualified_name()
    computed = node._compute_uid()
    node.uid = computed
    return computed
