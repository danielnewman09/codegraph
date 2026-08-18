"""SQLite node CRUD + query operations.

Ports the semantics of ``codegraph.backends.neo4j.node_ops.Neo4jNodeOps``
to SQL over the single ``nodes`` table + ``node_labels``/``node_tags``
join tables.  All registered model classes are pure-Python descriptors
(no neomodel), so the dual-mode code paths in the Neo4j ops are not
needed here.

Storage contract:

- ``properties`` JSON is the single source of truth; STORED generated
  columns (``source`` / ``qualified_name`` / ``kind``) derive from it.
- ``labels`` JSON (the inherited label chain) mirrors into
  ``node_labels``; ``tags`` mirror into ``node_tags``.  The join tables
  serve queries; the JSON columns serve inflate.
- Datetimes deflate to Unix timestamps (mirroring
  ``_deflate_value`` / ``_inflate_props``).
- ``element_id_property`` is set from the INTEGER PK on save so
  ``hasattr(node, "element_id_property")`` gates (cascade delete,
  equality) work unchanged.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.models.descriptors import (
    DateTimeProperty,
    PropertyRegistry,
)
from codegraph.models.tags import CodeGraphNode

log = logging.getLogger(__name__)

# Generated-column names that can be filtered directly.
_GENERATED_COLUMNS = frozenset({"source", "qualified_name", "kind", "canonical_key"})

# Properties whose text contributes to the FTS "content" column.
_SEARCHABLE_TEXT_PROPS = (
    "name",
    "brief_description",
    "detailed_description",
    "description",
    "content",
    "definition",
    "test_name",
    "test_module",
)

# Property names that hold float-vector embeddings.
_EMBEDDING_PROPS = ("doc_embedding", "impl_embedding")

_NODE_COLS = "n.id, n.canonical_key, n.labels, n.properties"


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _node_labels(node_type: type) -> list[str]:
    """Return the inherited label chain for a node type.

    Every registered class subclasses CodeGraphNode, which provides
    ``inherited_labels()`` (e.g. ``["ClassNode", "CompoundNode"]``).
    """
    return node_type.inherited_labels()


def best_class_for_labels(labels: set[str]) -> type | None:
    """Pick the most specific registered class matching a raw node's labels.

    Identical semantics to the Neo4j implementation: a class matches
    when its label chain intersects the raw labels; among matches,
    prefer classes whose own leaf name is present in the raw labels
    (e.g. a raw ``{AttributeNode, MemberNode}`` inflates to
    ``AttributeNode``, not a same-depth sibling), then the deepest MRO.
    """
    candidates = [
        cls
        for cls in CodeGraphNode._registry.values()
        if labels & set(_node_labels(cls))
    ]
    if not candidates:
        return None
    leaf_matches = [cls for cls in candidates if cls.__name__ in labels]
    pool = leaf_matches or candidates
    return max(pool, key=lambda c: len(c.__mro__))


def _deflate_value(prop: Any, value: Any) -> Any:
    """Deflate a property value for JSON storage.

    ``DateTimeProperty`` → Unix timestamp.  Everything else passes
    through (``json.dumps`` handles str/int/float/bool/list/dict).
    """
    if isinstance(prop, DateTimeProperty) and isinstance(value, datetime):
        return value.timestamp()
    return value


def _inflate_props(node_type: type, raw_props: dict[str, Any]) -> dict[str, Any]:
    """Convert raw JSON property values to Python values.

    Unix timestamps stored by ``_deflate_value`` come back as
    ``datetime`` for ``DateTimeProperty`` fields.
    """
    if not raw_props:
        return {}
    declared = PropertyRegistry.properties_of(node_type)
    props = dict(raw_props)
    for name, prop in declared.items():
        if isinstance(prop, DateTimeProperty) and name in props:
            val = props[name]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                try:
                    props[name] = datetime.fromtimestamp(val)
                except (OverflowError, OSError, ValueError):
                    pass
    return props


def _serialize_props(node: CodeGraphNode) -> dict[str, Any]:
    """Deflate every declared property of *node* into a JSON-safe dict.

    Skips None / "" / [] (mirrors Neo4jNodeOps.save).  The uid
    (a declared UniqueId property) is included so the properties JSON
    is a complete round-trip source.
    """
    node_type = type(node)
    props: dict[str, Any] = {}
    for pname, prop in PropertyRegistry.properties_of(node_type).items():
        val = getattr(node, pname, None)
        if val is None or val == "" or val == []:
            continue
        props[pname] = _deflate_value(prop, val)
    return props


def _tags_of(node: CodeGraphNode) -> list[str]:
    """Return the node's tags list if declared, else []."""
    if PropertyRegistry.has_property(type(node), "tags"):
        tags = getattr(node, "tags", None)
        if tags:
            return list(tags)
    return []


def _fts_content(node: CodeGraphNode) -> str:
    """Build the FTS content string for a node."""
    parts: list[str] = []
    declared = PropertyRegistry.properties_of(type(node))
    for pname in _SEARCHABLE_TEXT_PROPS:
        if pname not in declared:
            continue
        val = getattr(node, pname, None)
        if isinstance(val, str) and val:
            parts.append(val)
    return " ".join(parts)


def _uid_to_id(conn, uid: str) -> int | None:
    """Compatibility shim (WP C): a canonical key IS the storage key."""
    row = conn.execute(
        sa.text("SELECT id FROM nodes WHERE canonical_key = :key"),
        {"key": uid},
    ).first()
    return row[0] if row else None


def _row_to_node(row: Any, conn=None) -> CodeGraphNode | None:
    """Build a node instance from a ``nodes`` table row.

    *row* may be a SQLAlchemy Row or a dict; *conn* is optional and
    used to attach the stored embedding back onto the instance.
    """
    if row is None:
        return None
    from codegraph.backends.sqlite.connection import row_to_dict

    d = row_to_dict(row)
    labels = set(json.loads(d["labels"]) or [])
    target_type = best_class_for_labels(labels)
    if target_type is None:
        return None
    props = _inflate_props(target_type, json.loads(d["properties"] or "{}"))
    instance = target_type(**props)
    instance.element_id_property = d["id"]
    if conn is not None:
        _attach_embedding(instance, d["id"], conn)
    return instance


def _attach_embedding(instance: CodeGraphNode, node_id: int, conn) -> None:
    """Set the embedding property from node_embeddings when present.

    The BLOB table is the canonical store; this rehydrates the model
    attribute so reads match the Neo4j backend (embeddings as node
    properties) without doubling storage in the JSON blob.
    """
    declared = PropertyRegistry.properties_of(type(instance))
    emb_name = next((p for p in _EMBEDDING_PROPS if p in declared), None)
    if emb_name is None:
        return
    try:
        from codegraph.backends.sqlite.search import unpack_embedding

        row = conn.execute(
            sa.text("SELECT embedding FROM node_embeddings WHERE node_id = :nid"),
            {"nid": node_id},
        ).first()
        if row is not None and row[0]:
            setattr(instance, emb_name, unpack_embedding(row[0]).tolist())
    except Exception:
        # Embeddings are an enhancement — never break reads on them.
        log.debug("Failed to attach embedding for node %s", node_id, exc_info=True)


def _deflect_filter_value(value: Any) -> Any:
    """Normalise a filter value for JSON comparison."""
    if isinstance(value, datetime):
        return value.timestamp()
    return value


class SqliteNodeOps:
    """Node CRUD + query operations for the SQLite backend."""

    def __init__(self, conn: SqliteConnection):
        self._conn = conn

    # ── Node CRUD ────────────────────────────────────────────────────

    def save(self, node: CodeGraphNode) -> CodeGraphNode:
        """Save a node keyed by its canonical key (WP C).

        Upserts by ``canonical_key`` (``INSERT ... ON CONFLICT(canonical_key)
        DO UPDATE``), mirrors labels/tags into the join tables, refreshes
        the FTS row, and stores any declared embedding.  Sets
        ``element_id_property`` from the INTEGER PK.  Canonical identity
        is mandatory — the model guarantees a valid key before the
        backend sees the node.
        """
        node_type = type(node)

        if (PropertyRegistry.has_property(node_type, "qualified_name")
                and not getattr(node, "qualified_name", "")):
            node.qualified_name = node._compute_qualified_name()

        key = getattr(node, "canonical_key", "") or ""
        if not key:
            from codegraph.identity import IdentityError

            raise IdentityError(
                f"cannot save {type(node).__name__}: no canonical key"
            )
        labels = _node_labels(node_type)
        props = _serialize_props(node)

        with self._conn.session() as conn:
            row = conn.execute(
                sa.text(
                    "INSERT INTO nodes (canonical_key, labels, properties) "
                    "VALUES (:key, :labels, :properties) "
                    "ON CONFLICT(canonical_key) DO UPDATE SET "
                    # Properties merge (Neo4j's ``SET n += $props``
                    # semantics): new keys win, existing keys not present
                    # in the new row are preserved.
                    "properties = json_patch(nodes.properties, excluded.properties) "
                    "RETURNING id, canonical_key, labels, properties"
                ),
                {
                    "key": key,
                    "labels": json.dumps(labels),
                    "properties": json.dumps(props),
                },
            ).first()
            node_id = row[0]
            stored_key = row[1]
            stored_labels = json.loads(row[2])
            stored_props = json.loads(row[3] or "{}")

            self._sync_labels(conn, node_id, stored_labels)
            self._sync_tags(conn, node_id, stored_props.get("tags") or [])
            self._sync_fts_from_props(conn, stored_key, node_id, stored_props)
            self._sync_embedding(conn, node_id, stored_props)

        node.element_id_property = node_id
        return node

    def _sync_labels(self, conn, node_id: int, labels: list[str]) -> None:
        conn.execute(
            sa.text("DELETE FROM node_labels WHERE node_id = :nid"),
            {"nid": node_id},
        )
        if labels:
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO node_labels (node_id, label) VALUES (:nid, :lbl)"
                ),
                [{"nid": node_id, "lbl": lbl} for lbl in labels],
            )

    def _sync_tags(self, conn, node_id: int, tags: list[str]) -> None:
        conn.execute(
            sa.text("DELETE FROM node_tags WHERE node_id = :nid"),
            {"nid": node_id},
        )
        if tags:
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO node_tags (node_id, tag) VALUES (:nid, :tag)"
                ),
                [{"nid": node_id, "tag": t} for t in tags],
            )

    def _sync_fts(self, conn, uid: str, node: CodeGraphNode, tags: list[str]) -> None:
        conn.execute(
            sa.text("DELETE FROM fts_nodes WHERE canonical_key = :ckey"),
            {"ckey": uid},
        )
        conn.execute(
            sa.text(
                "INSERT INTO fts_nodes (canonical_key, content, qualified_name, tags) "
                "VALUES (:ckey, :content, :qname, :tags)"
            ),
            {
                "ckey": uid,
                "content": _fts_content(node),
                "qname": getattr(node, "qualified_name", "") or "",
                "tags": " ".join(tags),
            },
        )

    def _sync_fts_from_props(
        self, conn, uid: str, node_id: int, props: dict[str, Any]
    ) -> None:
        """Refresh the FTS row from an updated properties dict.

        Used by ``update_properties`` when the underlying properties
        (tags or searchable text) changed without a full ``save()``.
        """
        conn.execute(
            sa.text("DELETE FROM fts_nodes WHERE canonical_key = :ckey"),
            {"ckey": uid},
        )
        content_parts = [
            str(props[p])
            for p in _SEARCHABLE_TEXT_PROPS
            if props.get(p)
        ]
        conn.execute(
            sa.text(
                "INSERT INTO fts_nodes (canonical_key, content, qualified_name, tags) "
                "VALUES (:ckey, :content, :qname, :tags)"
            ),
            {
                "ckey": uid,
                "content": " ".join(content_parts),
                "qname": str(props.get("qualified_name", "") or ""),
                "tags": " ".join(str(t) for t in (props.get("tags") or [])),
            },
        )

    def _sync_embedding(self, conn, node_id: int, props: dict[str, Any]) -> None:
        conn.execute(
            sa.text("DELETE FROM node_embeddings WHERE node_id = :nid"),
            {"nid": node_id},
        )
        emb_name = next((p for p in _EMBEDDING_PROPS if p in props), None)
        if emb_name is not None and props.get(emb_name):
            from codegraph.backends.sqlite.search import pack_embedding

            values = props[emb_name]
            blob = pack_embedding(values)
            conn.execute(
                sa.text(
                    "INSERT INTO node_embeddings (node_id, dim, embedding, updated_at) "
                    "VALUES (:nid, :dim, :blob, unixepoch())"
                ),
                {"nid": node_id, "dim": len(values), "blob": blob},
            )

    def delete(self, node: CodeGraphNode) -> None:
        """Delete a node, cascading to COMPOSES children first.

        Children are deleted recursively (leaves first) before the node;
        FK cascades remove edges, label/tag rows, and embeddings; the
        FTS row is removed explicitly (FTS shadow tables don't cascade).
        """
        if not hasattr(node, "element_id_property"):
            raise ValueError(
                f"Cannot delete unsaved {type(node).__name__} instance. "
                "Save the node first before calling delete()."
            )

        for child in self.get_composed_children(node):
            if hasattr(child, "element_id_property") and not getattr(child, "deleted", False):
                self.delete(child)

        key = node.canonical_key
        with self._conn.session() as conn:
            if key:
                conn.execute(
                    sa.text("DELETE FROM fts_nodes WHERE canonical_key = :ckey"),
                    {"ckey": key},
                )
            conn.execute(
                sa.text("DELETE FROM nodes WHERE id = :nid"),
                {"nid": node.element_id_property},
            )
        node.deleted = True

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
                        "SELECT t.id, t.canonical_key, t.labels, t.properties "
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

    def get(
        self,
        node_type: type[CodeGraphNode],
        **filters: Any,
    ) -> CodeGraphNode | None:
        """Get a single node by field filters."""
        rows = self._select_nodes(node_type, filters, limit=1)
        if not rows:
            return None
        return _row_to_node(rows[0], self._conn)

    def find_all(
        self,
        node_type: type[CodeGraphNode],
        **filters: Any,
    ) -> list[CodeGraphNode]:
        """Return all nodes of *node_type* matching field filters (or all)."""
        rows = self._select_nodes(node_type, filters)
        with self._conn.connect() as conn:
            return [
                n for n in (_row_to_node(r, conn) for r in rows) if n is not None
            ]

    def _select_nodes(
        self,
        node_type: type[CodeGraphNode],
        filters: dict[str, Any],
        limit: int | None = None,
    ) -> list:
        """SELECT nodes of *node_type* (by primary label) matching filters."""
        label = _node_labels(node_type)[0]
        where = ["nl.label = :label"]
        params: dict[str, Any] = {"label": label}
        for i, (key, value) in enumerate(filters.items(), start=1):
            pname = f"f{i}"
            if key in _GENERATED_COLUMNS:
                where.append(f"n.{key} = :{pname}")
            else:
                where.append(f"json_extract(n.properties, '$.{key}') = :{pname}")
            params[pname] = _deflect_filter_value(value)
        sql = (
            f"SELECT {_NODE_COLS} FROM nodes n "
            "JOIN node_labels nl ON nl.node_id = n.id "
            f"WHERE {' AND '.join(where)}"
        )
        if limit is not None:
            sql += f" LIMIT {limit}"
        with self._conn.connect() as conn:
            return list(conn.execute(sa.text(sql), params))

    def inflate(
        self,
        raw: Any,
        node_type: type[CodeGraphNode],
    ) -> CodeGraphNode:
        """Build a CodeGraphNode from a raw backend result row.

        *raw* may be a ``nodes`` table row (dict-like), a uid string,
        or an already-inflated node.
        """
        if isinstance(raw, CodeGraphNode):
            return raw
        with self._conn.connect() as conn:
            if isinstance(raw, str):
                row = conn.execute(
                    sa.text(
                        "SELECT id, canonical_key, labels, properties FROM nodes WHERE canonical_key = :key"
                    ),
                    {"key": raw},
                ).first()
            else:
                row = raw
            node = _row_to_node(row, conn)
        if node is None:
            if isinstance(raw, str):
                raise KeyError(f"No node with key {raw} in SQLite store")
            raise ValueError("Cannot inflate raw row: no registered class matched")
        return node

    # ── Tag queries ──────────────────────────────────────────────────

    def find_by_tag(
        self,
        node_type: type[CodeGraphNode],
        tag: str,
    ) -> list[CodeGraphNode]:
        """Fetch all nodes of *node_type* whose tags contain *tag*."""
        label = _node_labels(node_type)[0]
        sql = (
            f"SELECT {_NODE_COLS} FROM nodes n "
            "JOIN node_labels nl ON nl.node_id = n.id "
            "JOIN node_tags nt ON nt.node_id = n.id "
            "WHERE nl.label = :label AND nt.tag = :tag"
        )
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), {"label": label, "tag": tag}))
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    def find_all_by_tag(self, tag: str) -> list[CodeGraphNode]:
        """Fetch all nodes across all registered types matching *tag*."""
        sql = (
            f"SELECT {_NODE_COLS} FROM nodes n "
            "JOIN node_tags nt ON nt.node_id = n.id "
            "WHERE nt.tag = :tag"
        )
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), {"tag": tag}))
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    def find_all_by_source(self, source: str) -> list[CodeGraphNode]:
        """Fetch all nodes across all types matching *source* (indexed)."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(f"SELECT {_NODE_COLS} FROM nodes n WHERE n.source = :src"),
                    {"src": source},
                )
            )
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    def find_all_by_kind(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list[CodeGraphNode]:
        """Fetch all nodes matching *kind* (and optionally *tag*)."""
        where = ["n.kind = :kind"]
        params: dict[str, Any] = {"kind": kind}
        sql = f"SELECT {_NODE_COLS} FROM nodes n "
        if tag is not None:
            sql += "JOIN node_tags nt ON nt.node_id = n.id "
            where.append("nt.tag = :tag")
            params["tag"] = tag
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(sa.text(sql + "WHERE " + " AND ".join(where)), params)
            )
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    # ── uid-based node queries ────────────────────────────────────

    def find_by_uid(self, uid: str) -> CodeGraphNode | None:
        """Compatibility shim (WP C): a canonical key IS the storage key."""
        return self.find_by_key(uid)

    def find_by_key(self, key: str) -> CodeGraphNode | None:
        """Find any node by its canonical key (WP3.2).

        Uses the generated ``canonical_key`` column + unique partial
        index; ``LIMIT 1`` guards against a database that predates the
        unique index.
        """
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text(
                    f"SELECT {_NODE_COLS} FROM nodes n "
                    "WHERE n.canonical_key = :key LIMIT 1"
                ),
                {"key": key},
            ).first()
            if row is None:
                return None
            return _row_to_node(row, conn)

    def get_labels(self, uid: str) -> set[str]:
        """Return the label chain for a node by uid."""
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text("SELECT labels FROM nodes WHERE canonical_key = :key"),
                {"key": uid},
            ).first()
        if row is None:
            return set()
        return set(json.loads(row[0]) or [])

    def set_labels(self, uid: str, labels: list[str]) -> None:
        """Replace all labels on a node."""
        if not labels:
            return
        with self._conn.session() as conn:
            row = conn.execute(
                sa.text("SELECT id FROM nodes WHERE canonical_key = :key"),
                {"key": uid},
            ).first()
            if row is None:
                return
            node_id = row[0]
            conn.execute(
                sa.text("UPDATE nodes SET labels = :lbls WHERE id = :nid"),
                {"lbls": json.dumps(labels), "nid": node_id},
            )
            self._sync_labels(conn, node_id, labels)

    def remove_labels(self, uid: str, labels: list[str]) -> None:
        """Remove specific labels from a node."""
        if not labels:
            return
        with self._conn.session() as conn:
            row = conn.execute(
                sa.text("SELECT id, labels FROM nodes WHERE canonical_key = :key"),
                {"key": uid},
            ).first()
            if row is None:
                return
            node_id, raw = row[0], row[1]
            current = json.loads(raw) or []
            remove = set(labels)
            remaining = [l for l in current if l not in remove]
            conn.execute(
                sa.text("UPDATE nodes SET labels = :lbls WHERE id = :nid"),
                {"lbls": json.dumps(remaining), "nid": node_id},
            )
            for lbl in labels:
                conn.execute(
                    sa.text(
                        "DELETE FROM node_labels WHERE node_id = :nid AND label = :lbl"
                    ),
                    {"nid": node_id, "lbl": lbl},
                )

    def update_properties(
        self, uid: str, props: dict, *, add_labels: list[str] | None = None
    ) -> bool:
        """SET properties (and optionally add labels) on a node by uid.

        When *props* contains a new ``uid`` value (scaffold→design
        migration re-keys nodes), the uid column and the FTS key are
        updated in the same transaction so lookups stay consistent.
        """
        if not props and not add_labels:
            return False
        with self._conn.session() as conn:
            row = conn.execute(
                sa.text("SELECT id, labels, properties FROM nodes WHERE canonical_key = :key"),
                {"key": uid},
            ).first()
            if row is None:
                return False
            node_id, raw_labels, raw = row[0], row[1], row[2]
            current = json.loads(raw or "{}")
            target_type = best_class_for_labels(set(json.loads(raw_labels) or []))
            declared = (
                PropertyRegistry.properties_of(target_type)
                if target_type is not None
                else {}
            )
            for key, value in props.items():
                current[key] = _deflate_value(declared.get(key), value)
            conn.execute(
                sa.text("UPDATE nodes SET properties = :props WHERE id = :nid"),
                {"props": json.dumps(current), "nid": node_id},
            )
            new_uid = props.get("uid")
            if new_uid and str(new_uid) != uid:
                # Re-key: the uid column must match the properties JSON.
                conn.execute(
                    sa.text("UPDATE nodes SET uid = :new_uid WHERE id = :nid"),
                    {"new_uid": str(new_uid), "nid": node_id},
                )
                conn.execute(
                    sa.text("UPDATE fts_nodes SET canonical_key = :new_uid WHERE canonical_key = :old_uid"),
                    {"new_uid": str(new_uid), "old_uid": uid},
                )
                uid = str(new_uid)
            if "tags" in props:
                tags = current.get("tags") or []
                self._sync_tags(conn, node_id, list(tags))
            # Refresh the FTS row if any searchable text/tag changed.
            if any(k in props for k in ("tags", "name", "qualified_name")
                   + _SEARCHABLE_TEXT_PROPS):
                self._sync_fts_from_props(conn, uid, node_id, current)
            if add_labels:
                merged = list(dict.fromkeys((json.loads(raw_labels) or []) + add_labels))
                conn.execute(
                    sa.text("UPDATE nodes SET labels = :lbls WHERE id = :nid"),
                    {"lbls": json.dumps(merged), "nid": node_id},
                )
                self._sync_labels(conn, node_id, merged)
        return True

    def delete_by_uid(self, uid: str) -> bool:
        """Compatibility shim (WP C): a canonical key IS the storage key."""
        return self.delete_by_key(uid)

    def delete_by_key(self, key: str) -> bool:
        """DETACH-style delete of a node by canonical key (WP3.2)."""
        with self._conn.session() as conn:
            row = conn.execute(
                sa.text("SELECT id, canonical_key FROM nodes WHERE canonical_key = :key"),
                {"key": key},
            ).first()
            if row is None:
                return False
            node_id, stored_key = row[0], row[1]
            conn.execute(
                sa.text("DELETE FROM fts_nodes WHERE canonical_key = :ckey"),
                {"ckey": stored_key},
            )
            conn.execute(sa.text("DELETE FROM nodes WHERE id = :nid"), {"nid": node_id})
        return True

    def delete_by_source(self, source: str) -> int:
        """Delete every node carrying *source* in one statement.

        Uses the persisted generated ``source`` column (``idx_nodes_source``);
        edges cascade via FK.  FTS rows are removed in the same transaction.
        """
        with self._conn.session() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM fts_nodes WHERE canonical_key IN "
                    "(SELECT canonical_key FROM nodes WHERE source = :src)"
                ),
                {"src": source},
            )
            result = conn.execute(
                sa.text("DELETE FROM nodes WHERE source = :src"),
                {"src": source},
            )
        return result.rowcount

    def delete_by_uids(self, uids: list[str]) -> int:
        """Delete all nodes with the given uids in one statement per chunk.

        Edges cascade via FK; FTS rows removed in the same transaction.
        Chunked at 900 uids to stay under SQLite's variable limit.
        """
        if not uids:
            return 0
        total = 0
        uid_list = list(uids)
        with self._conn.session() as conn:
            for j in range(0, len(uid_list), 900):
                chunk = uid_list[j:j + 900]
                binds = ", ".join(f":u{i}" for i in range(len(chunk)))
                params = {f"u{i}": u for i, u in enumerate(chunk)}
                conn.execute(
                    sa.text(
                        f"DELETE FROM fts_nodes WHERE canonical_key IN ({binds})"
                    ),
                    params,
                )
                result = conn.execute(
                    sa.text(
                        f"DELETE FROM nodes WHERE canonical_key IN ({binds})"
                    ),
                    params,
                )
                total += result.rowcount
        return total

    def find_uids_by_tag(self, tag: str) -> list[str]:
        """Return all uids for nodes whose tags contain *tag* (indexed)."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT n.canonical_key FROM nodes n "
                        "JOIN node_tags nt ON nt.node_id = n.id "
                        "WHERE nt.tag = :tag"
                    ),
                    {"tag": tag},
                )
            )
        return [r[0] for r in rows]

    def find_uids_by_tag_condition(
        self,
        tag: str,
        *,
        condition_clause: str = "",
        params: dict | None = None,
    ) -> list[str]:
        """Return uids for nodes with *tag* plus an optional SQL condition.

        *condition_clause* is backend-native SQL over the ``nodes`` row
        aliased as ``n`` (the Neo4j equivalent takes Cypher).
        """
        sql = (
            "SELECT n.canonical_key FROM nodes n "
            "JOIN node_tags nt ON nt.node_id = n.id "
            "WHERE nt.tag = :tag"
        )
        if condition_clause:
            sql += f" AND ({condition_clause})"
        with self._conn.connect() as conn:
            rows = list(conn.execute(sa.text(sql), {"tag": tag, **(params or {})}))
        return [r[0] for r in rows]

    # ── uid ↔ name ↔ qualified_name resolution ─────────────────

    def find_uid_by_name(self, name: str, label: str | None = None) -> str | None:
        """Look up uid for a node by name, optionally label-qualified."""
        params: dict[str, Any] = {"name": name}
        if label:
            sql = (
                "SELECT n.canonical_key FROM nodes n "
                "JOIN node_labels nl ON nl.node_id = n.id "
                "WHERE nl.label = :label "
                "AND json_extract(n.properties, '$.name') = :name"
            )
            params["label"] = label
        else:
            sql = (
                "SELECT n.canonical_key FROM nodes n "
                "WHERE json_extract(n.properties, '$.name') = :name"
            )
        with self._conn.connect() as conn:
            row = conn.execute(sa.text(sql + " LIMIT 1"), params).first()
        return row[0] if row else None

    def find_uid_by_qualified_name(self, qualified_name: str) -> str | None:
        """Look up uid for a node by qualified_name (indexed)."""
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text("SELECT canonical_key FROM nodes WHERE qualified_name = :qn LIMIT 1"),
                {"qn": qualified_name},
            ).first()
        return row[0] if row else None

    def find_all_by_qualified_name(
        self, qualified_name: str
    ) -> list[CodeGraphNode]:
        """Return all nodes matching *qualified_name*."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        f"SELECT {_NODE_COLS} FROM nodes n "
                        "WHERE n.qualified_name = :qn"
                    ),
                    {"qn": qualified_name},
                )
            )
            return [n for n in (_row_to_node(r, conn) for r in rows) if n is not None]

    def find_qualified_name_by_uid(self, uid: str) -> str | None:
        """Look up qualified_name for a node by uid."""
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text("SELECT qualified_name FROM nodes WHERE canonical_key = :key LIMIT 1"),
                {"key": uid},
            ).first()
        return row[0] if row else None

    # ── Edge helpers ─────────────────────────────────────────────

    def delete_outgoing_relationships(
        self, source_uid: str, rel_type: str
    ) -> int:
        """Delete all outgoing relationships of *rel_type* from a node."""
        with self._conn.session() as conn:
            node_id = _uid_to_id(conn, source_uid)
            if node_id is None:
                return 0
            result = conn.execute(
                sa.text("DELETE FROM edges WHERE source_id = :nid AND rel_type = :rt"),
                {"nid": node_id, "rt": rel_type},
            )
        return result.rowcount or 0

    def node_exists(self, uid: str) -> bool:
        """Check whether a node with given uid exists."""
        with self._conn.connect() as conn:
            row = conn.execute(
                sa.text("SELECT 1 FROM nodes WHERE canonical_key = :key LIMIT 1"),
                {"key": uid},
            ).first()
        return row is not None

    # ── Bulk label queries ───────────────────────────────────────

    def get_all_node_labels(self) -> list[dict[str, Any]]:
        """Return qualified_name, labels, and uid for every node."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT qualified_name, labels, canonical_key FROM nodes "
                        "ORDER BY qualified_name"
                    )
                )
            )
        return [
            {
                "qualified_name": r[0] or "(none)",
                "labels": json.loads(r[1]) or [],
                "uid": r[2],
            }
            for r in rows
        ]

    def find_nodes_with_labels(self, labels: list[str]) -> list[dict[str, Any]]:
        """Find nodes that carry ALL of the specified labels."""
        if not labels:
            return []
        binds = ", ".join(f":l{i}" for i in range(len(labels)))
        params = {f"l{i}": l for i, l in enumerate(labels)}
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        f"SELECT n.qualified_name, n.labels, n.canonical_key FROM nodes n "
                        f"JOIN node_labels nl ON nl.node_id = n.id "
                        f"WHERE nl.label IN ({binds}) "
                        f"GROUP BY n.id "
                        f"HAVING COUNT(DISTINCT nl.label) = {len(labels)} "
                        f"ORDER BY n.qualified_name"
                    ),
                    params,
                )
            )
        return [
            {
                "qualified_name": r[0] or "(none)",
                "labels": json.loads(r[1]) or [],
                "uid": r[2],
            }
            for r in rows
        ]

    def count_all_nodes(self) -> int:
        """Return the total number of nodes in the graph."""
        with self._conn.connect() as conn:
            return conn.execute(sa.text("SELECT COUNT(*) FROM nodes")).scalar_one()

    # ── Full-text search ───────────────────────────────────────

    def search_fulltext(
        self,
        query: str,
        *,
        index_name: str = "",
        labels: str = "",
        tag: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search with optional label/tag filters.

        Uses the FTS5 shadow table; falls back to a LIKE scan when the
        MATCH syntax rejects the query (mirrors Neo4j's CONTAINS
        fallback).  Returns ``[{"node": CodeGraphNode, "score": float}]``
        with higher score = better.
        """
        from codegraph.backends.sqlite.search import fts_search

        return fts_search(
            self._conn,
            query,
            labels=labels,
            tag=tag,
            limit=limit,
        )

    # ── Vector search ──────────────────────────────────────────

    def search_vector(
        self,
        embedding: list[float],
        *,
        index_name: str = "",
        labels: str = "",
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Vector similarity search (numpy-exact, filter-then-KNN).

        Returns ``[{"node": CodeGraphNode, "score": float}]`` ordered by
        descending cosine similarity, or [] if no embeddings exist.
        """
        from codegraph.backends.sqlite.search import vector_search

        if not embedding:
            return []
        return vector_search(
            self._conn,
            embedding,
            labels=labels,
            tag=tag,
            limit=limit,
        )
