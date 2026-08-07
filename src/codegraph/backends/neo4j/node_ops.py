"""Neo4j node CRUD operations.

Extracted from ``codegraph.models.tags.CodeGraphNode``.
Updated to use ``PropertyRegistry`` for property introspection,
supporting both neomodel and the new ``Property``/``Relationship`` descriptors.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from neomodel import db
from neomodel.sync_.node import StructuredNode
from neomodel import RelationshipTo, RelationshipFrom

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.models.tags import CodeGraphNode
from codegraph.models.descriptors import (
    Property as CGProperty,
    DateTimeProperty as CGDateTimeProperty,
    Relationship as CGRelationship,
    PropertyRegistry,
)


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _node_labels(node_type: type) -> list[str]:
    """Return Neo4j labels for a node type.

    Uses neomodel's ``inherited_labels()`` when available (neomodel
    ``StructuredNode`` subclasses).  Falls back to ``[node_type.__name__]``
    for pure-Python classes using the new descriptor system.
    """
    if hasattr(node_type, "inherited_labels"):
        return node_type.inherited_labels()
    # Pure-Python: use class name as the sole label
    return [node_type.__name__]


def best_class_for_labels(labels: set[str]) -> type | None:
    """Pick the most specific registered class matching a raw node's labels.

    A class matches when its label chain intersects the raw labels.
    Among matches, prefer classes whose own leaf name is present in the
    raw labels (i.e. the exact stored type — e.g. a raw ``AttributeNode``
    carries ``{AttributeNode, MemberNode}``, so ``AttributeNode`` wins
    over its ``MemberNode``-labelled siblings), then the deepest MRO.

    Returns ``None`` when no registered class matches.
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
    """Deflate a property value for Neo4j storage.

    Handles both neomodel properties (which have their own
    ``.deflate()``) and our new descriptors.  For our
    ``DateTimeProperty``, converts ``datetime`` to Unix timestamp.
    """
    # Neomodel properties have their own deflate
    if hasattr(prop, "deflate"):
        return prop.deflate(value)
    # Our DateTimeProperty: datetime → Unix timestamp
    if isinstance(prop, CGDateTimeProperty) and isinstance(value, datetime):
        return value.timestamp()
    # Our Property / UniqueId: pass through
    return value


def _is_relationship_descriptor(prop: Any) -> bool:
    """Check whether *prop* is a relationship descriptor (ours or neomodel's)."""
    return isinstance(prop, (RelationshipTo, RelationshipFrom, CGRelationship))


def _inflate_props(node_type: type, raw_props: dict[str, Any]) -> dict[str, Any]:
    """Convert raw Neo4j property values to Python values for a node type.

    Handles our ``DateTimeProperty`` (timestamps stored by
    ``_deflate_value`` must come back as ``datetime``).  Neomodel
    properties are handled by neomodel's own inflate path.
    """
    if not raw_props:
        return {}
    declared = PropertyRegistry.properties_of(node_type)
    props = dict(raw_props)
    for name, prop in declared.items():
        if isinstance(prop, CGDateTimeProperty) and name in props:
            val = props[name]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                try:
                    props[name] = datetime.fromtimestamp(val)
                except (OverflowError, OSError, ValueError):
                    pass
    return props

def _build_save_payload(node: "CodeGraphNode") -> tuple[str, str, dict]:
    """Compute the labels, deterministic uid, and props for *node*.

    Mirrors ``Neo4jNodeOps.save()`` exactly (same uid derivation,
    same PropertyRegistry prop building, same empty-value skipping,
    same deflation) so the batched bulk-write path stores byte-identical
    rows to the per-node path.  Sets ``node.uid`` in place, matching
    ``save()``.

    Returns:
        ``(labels, uid, props)`` — *labels* is the ``:``-joined Neo4j
        label chain, *props* includes the ``uid`` key.
    """
    node_type = type(node)

    # Ensure qualified_name is set before computing uid.
    if PropertyRegistry.has_property(node_type, "qualified_name"):
        if not getattr(node, "qualified_name", ""):
            node.qualified_name = node._compute_qualified_name()

    computed = node._compute_uid()
    node.uid = computed
    labels = ":".join(_node_labels(node_type))

    # Build property dict using PropertyRegistry (supports both old and new)
    props: dict = {}
    declared = PropertyRegistry.properties_of(node_type)
    for pname, prop in declared.items():
        if _is_relationship_descriptor(prop):
            continue
        val = getattr(node, pname, None)
        if val is None or val == "" or val == []:
            continue
        props[pname] = _deflate_value(prop, val)
    props["uid"] = computed
    return labels, computed, props


class Neo4jNodeOps:
    """Node CRUD + query operations for the Neo4j backend.

    Each method is mechanically extracted from CodeGraphNode, replacing
    ``self`` → ``node``, ``cls`` → ``node_type``, ``db.cypher_query`` →
    ``self._conn.execute_raw``.
    """

    def __init__(self, conn: Neo4jConnection):
        self._conn = conn

    # ── Node CRUD ────────────────────────────────────────────────────

    def save(self, node: "CodeGraphNode") -> "CodeGraphNode":
        """Save a node to Neo4j, computing uid from identity fields.

        Uses MERGE on uid for idempotent create-or-update.
        Uses ``PropertyRegistry`` for introspection — works with
        both neomodel and new ``Property`` descriptors.

        Raises ``ValueError`` if ``source`` or the primary identity
        field is empty — a deterministic uid cannot be derived and
        the node is not viable.

        Returns the saved node.
        """
        labels, computed, props = _build_save_payload(node)

        query = (
            f"MERGE (n:{labels} {{uid: $uid}})"
            f" SET n += $props RETURN n"
        )
        results, _ = db.cypher_query(
            query, {"uid": computed, "props": props}
        )
        if results and results[0]:
            node.element_id_property = results[0][0].element_id
        return node

    def delete(self, node: "CodeGraphNode") -> None:
        """Delete a node from Neo4j, cascading to composed children first.

        Any node reachable via an outgoing COMPOSES relationship is
        deleted recursively (depth-first, leaves first) before this node.
        After cascading, all remaining relationships are disconnected
        to clear in-memory caches of related nodes.
        """

        if not hasattr(node, "element_id_property"):
            raise ValueError(
                f"Cannot delete unsaved {type(node).__name__} instance. "
                "Save the node first before calling delete()."
            )

        # Cascade: delete all composed children
        for child in self.get_composed_children(node):
            if hasattr(child, "element_id_property") and not getattr(child, "deleted", False):
                self.delete(child)

        # Disconnect all remaining relationships to clear caches
        seen: set[str] = set()
        _, declared_rels = PropertyRegistry.of(type(node))
        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom, CGRelationship)):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                if isinstance(val, CGRelationship):
                    # Pure-Python: delete edges via raw Cypher
                    if not hasattr(node, "element_id_property"):
                        continue
                    if val.direction == "INCOMING":
                        rel_match = f"MATCH (n)<-[r:{val.relation_type}]-()"
                    else:
                        rel_match = f"MATCH (n)-[r:{val.relation_type}]->()"
                    db.cypher_query(
                        f"{rel_match} WHERE elementId(n) = $eid DELETE r",
                        {"eid": node.element_id},
                    )
                else:
                    # Neomodel: use manager
                    manager = getattr(node, name)
                    try:
                        for connected in manager.all():
                            try:
                                manager.disconnect(connected)
                            except Exception:
                                pass
                    except Exception:
                        pass

        if hasattr(node, "element_id_property"):
            # DETACH DELETE via Cypher (works for both neomodel and pure-Python)
            db.cypher_query(
                "MATCH (n) WHERE elementId(n) = $eid DETACH DELETE n",
                {"eid": node.element_id},
            )
            node.deleted = True

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return all nodes reachable via outgoing COMPOSES edges.

        Uses neomodel relationship managers when available; falls back
        to raw Cypher for pure-Python classes.
        """
        if not hasattr(node, "element_id_property"):
            return []

        children: list["CodeGraphNode"] = []
        seen: set[str] = set()
        _, declared_rels = PropertyRegistry.of(type(node))

        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if name in seen:
                    continue
                # Check both neomodel and new descriptors
                if isinstance(val, CGRelationship):
                    if val.relation_type != "COMPOSES" or val.direction != "OUTGOING":
                        continue
                    seen.add(name)
                    # Raw Cypher fallback for new descriptors
                    results, _ = db.cypher_query(
                        "MATCH (n)-[:COMPOSES]->(c) "
                        "WHERE elementId(n) = $eid RETURN c",
                        {"eid": node.element_id},
                    )
                    for row in results:
                        raw = row[0]
                        if raw is None:
                            continue
                        child = self._inflate_by_labels(raw)
                        if child is not None:
                            children.append(child)
                elif isinstance(val, RelationshipTo):
                    if val.definition["relation_type"] != "COMPOSES":
                        continue
                    seen.add(name)
                    children.extend(getattr(node, name).all())

        return children

    def get(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> "CodeGraphNode | None":
        """Get a single node by field filters.

        Uses neomodel's ``.nodes.get_or_none()`` for neomodel
        ``StructuredNode`` subclasses; uses raw Cypher for
        pure-Python classes (which have a backend-delegating
        ``.nodes`` shim that must NOT be re-entered here).
        """
        if issubclass(node_type, StructuredNode):
            return node_type.nodes.get_or_none(**filters)
        # Pure-Python: build a MATCH query from filters
        label = _node_labels(node_type)[0]
        clauses = []
        params = {}
        for key, value in filters.items():
            param_name = f"filter_{key}"
            clauses.append(f"n.{key} = ${param_name}")
            params[param_name] = value
        query = f"MATCH (n:`{label}`) WHERE {' AND '.join(clauses)} RETURN n LIMIT 1"
        # resolve_objects=False: raw Bolt nodes (resolve_objects would
        # raise NodeClassNotDefined for pure-Python labels).
        results, _ = db.cypher_query(query, params)
        if not results:
            return None
        return self.inflate(results[0][0], node_type)

    def find_all(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* matching field filters (or all).

        Raw Cypher for both neomodel and pure-Python classes — this is
        the backend implementation behind ``cls.nodes.filter()``.
        """
        label = _node_labels(node_type)[0]
        clauses = []
        params = {}
        for key, value in filters.items():
            param_name = f"filter_{key}"
            clauses.append(f"n.{key} = ${param_name}")
            params[param_name] = value
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"MATCH (n:`{label}`) {where} RETURN n"
        results, _ = db.cypher_query(query, params)
        return [self.inflate(r[0], node_type) for r in results if r[0]]

    def find_all_by_uids(
        self,
        node_type: type["CodeGraphNode"],
        uids: list[str],
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* whose ``uid`` is in *uids*.

        One batched query — the bulk counterpart of :meth:`get`, used
        by the 1-hop neighbor expansion in ``bulk_load_by_tag`` to
        avoid a per-node round trip.
        """
        if not uids:
            return []
        label = _node_labels(node_type)[0]
        query = f"MATCH (n:`{label}`) WHERE n.uid IN $uids RETURN n"
        results, _ = db.cypher_query(query, {"uids": uids})
        return [self.inflate(r[0], node_type) for r in results if r[0]]

    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        """Inflate a raw Neo4j result row into a CodeGraphNode.

        Uses neomodel's ``.inflate()`` when available; for pure-Python
        classes, extracts property values from the Bolt node, converts
        timestamps back to ``datetime`` for ``DateTimeProperty``, and
        constructs a new instance (attaching ``element_id``).
        """
        if issubclass(node_type, StructuredNode):
            return node_type.inflate(raw)
        # Pure-Python: find the most-derived registered class whose
        # labels overlap the raw node's labels.
        labels = set(raw.labels) if hasattr(raw, "labels") else set()
        target_type = best_class_for_labels(labels) or node_type

        raw_props = dict(raw.items()) if hasattr(raw, "items") else {}
        props = _inflate_props(target_type, raw_props)
        instance = target_type(**props)
        if hasattr(raw, "element_id"):
            instance.element_id_property = raw.element_id
        return instance

    # ── Node queries ─────────────────────────────────────────────────
    #
    # Property-guard checks are NOT needed here — the Backend ABC
    # validates that all registered types declare the expected
    # properties before delegating to these methods.

    def find_by_tag(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        """Fetch all nodes of node_type whose tags array contains tag."""
        label = _node_labels(node_type)[0]
        query = f"MATCH (n:`{label}`) WHERE $tag IN n.tags RETURN n"
        results, _ = db.cypher_query(query, {"tag": tag})
        return [self.inflate(row[0], node_type) for row in results]

    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching tag."""
        result: list["CodeGraphNode"] = []
        for node_cls in CodeGraphNode._registry.values():
            result.extend(self.find_by_tag(node_cls, tag))
        return result

    def _inflate_unique(
        self,
        rows: list,
        node_cls: type["CodeGraphNode"],
        seen: set[str],
    ) -> list["CodeGraphNode"]:
        """Inflate *rows* from one label-scoped query, deduping by element_id.

        Nodes stored under multiple labels (e.g. a ClassNode carries
        ``ClassNode`` and ``CompoundNode``) are matched by several
        per-label queries; this keeps each node exactly once.  The first
        (most specific) label query wins; ``inflate`` independently picks
        the best class from the raw node's labels.
        """
        out: list["CodeGraphNode"] = []
        for r in rows:
            if not r or not r[0]:
                continue
            raw = r[0]
            uid = getattr(raw, "element_id", None)
            if uid is None:
                uid = id(raw)
            if uid in seen:
                continue
            seen.add(uid)
            inflated = self.inflate(raw, node_cls)
            if inflated is not None:
                out.append(inflated)
        return out

    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all types matching source (no duplicates)."""
        result: list["CodeGraphNode"] = []
        seen: set[str] = set()
        for node_cls in CodeGraphNode._registry.values():
            label = _node_labels(node_cls)[0]
            try:
                query = f"MATCH (n:`{label}`) WHERE n.source = $src RETURN n"
                rows, _ = db.cypher_query(query, {"src": source})
                result.extend(self._inflate_unique(rows, node_cls, seen))
            except Exception:
                pass
        return result

    def find_all_by_kind(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        """Fetch all nodes matching kind (and optionally tag)."""
        result: list["CodeGraphNode"] = []
        seen: set[str] = set()
        for node_cls in CodeGraphNode._registry.values():
            label = _node_labels(node_cls)[0]
            try:
                tag_filter = ""
                params: dict = {"kind": kind}
                if tag is not None:
                    tag_filter = "AND $tag IN coalesce(n.tags, [])"
                    params["tag"] = tag
                query = (
                    f"MATCH (n:`{label}`) "
                    f"WHERE n.kind = $kind {tag_filter} RETURN n"
                )
                rows, _ = db.cypher_query(query, params)
                result.extend(self._inflate_unique(rows, node_cls, seen))
            except Exception:
                pass
        return result

    # ── uid-based node queries ────────────────────────────────────

    def find_by_uid(self, uid: str) -> "CodeGraphNode | None":
        """Find any node by its deterministic uid.

        Inflates by labels — works for both neomodel and pure-Python
        node types.
        """
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid RETURN n LIMIT 1",
            {"uid": uid},
        )
        if not results:
            return None
        return self._inflate_by_labels(results[0][0])

    def get_labels(self, uid: str) -> set[str]:
        """Return Neo4j labels for a node by uid."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid RETURN labels(n) AS lbls",
            {"uid": uid},
        )
        if not results:
            return set()
        return set(results[0][0])

    def set_labels(self, uid: str, labels: list[str]) -> None:
        """Replace all labels on a node.

        First queries current labels, adds new ones, removes stale ones.
        """
        if not labels:
            return
        old = self.get_labels(uid)
        if not old:
            return
        new = set(labels)
        to_add = new - old
        to_remove = old - new
        if to_add:
            add_clause = " ".join(f"SET n:`{l}`" for l in sorted(to_add))
            db.cypher_query(
                f"MATCH (n) WHERE n.uid = $uid {add_clause}",
                {"uid": uid},
            )
        for label in sorted(to_remove):
            db.cypher_query(
                f"MATCH (n) WHERE n.uid = $uid REMOVE n:`{label}`",
                {"uid": uid},
            )

    def remove_labels(self, uid: str, labels: list[str]) -> None:
        """Remove specific labels from a node."""
        if not labels:
            return
        for label in labels:
            db.cypher_query(
                f"MATCH (n) WHERE n.uid = $uid REMOVE n:`{label}`",
                {"uid": uid},
            )

    def update_properties(
        self, uid: str, props: dict, *, add_labels: list[str] | None = None
    ) -> bool:
        """SET properties and optionally add labels on a node by uid."""
        if not props and not add_labels:
            return False
        params: dict = {"uid": uid}
        set_parts: list[str] = []
        for key, val in props.items():
            param = f"prop_{key}"
            set_parts.append(f"n.{key} = ${param}")
            params[param] = val
        label_ops = ""
        if add_labels:
            label_ops = " ".join(f"SET n:`{l}`" for l in add_labels)
        query = (
            f"MATCH (n) WHERE n.uid = $uid "
            f"{label_ops} "
            f"SET {', '.join(set_parts)} "
            f"RETURN n"
        )
        results, _ = db.cypher_query(query, params)
        return len(results) > 0

    def delete_by_uid(self, uid: str) -> bool:
        """Delete a node (DETACH DELETE) by uid."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid "
            "DETACH DELETE n RETURN count(n) AS cnt",
            {"uid": uid},
        )
        return results and results[0][0] > 0

    def delete_by_source(self, source: str) -> int:
        """Delete every node carrying *source* in ONE query (DETACH).

        The aggregate counterpart of :meth:`delete_by_uid` — used by
        ``clear_source`` at scale; per-node deletes were ~26ms/node.
        """
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.source = $src "
            "DETACH DELETE n RETURN count(n) AS cnt",
            {"src": source},
        )
        return results[0][0] if results else 0

    def delete_by_uids(self, uids: list[str]) -> int:
        """Delete all nodes with the given uids in ONE query (DETACH).

        Idempotent — missing uids are ignored.  Used by stale-node
        pruning in incremental re-index (per-node deletes were
        ~26ms/node).
        """
        if not uids:
            return 0
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid IN $uids "
            "DETACH DELETE n RETURN count(n) AS cnt",
            {"uids": uids},
        )
        return results[0][0] if results else 0

    def find_uids_by_tag(self, tag: str) -> list[str]:
        """Return all uids for nodes whose tags array contains tag."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE $tag IN coalesce(n.tags, []) RETURN n.uid AS uid",
            {"tag": tag},
        )
        return [r[0] for r in results]

    # ── uid ↔ name ↔ qualified_name resolution ─────────────────

    def find_uid_by_name(self, name: str, label: str | None = None) -> str | None:
        """Look up uid for a node by name, optionally label-qualified."""
        if label:
            results, _ = db.cypher_query(
                f"MATCH (n:`{label}`) WHERE n.name = $name "
                "RETURN n.uid AS uid LIMIT 1",
                {"name": name},
            )
        else:
            results, _ = db.cypher_query(
                "MATCH (n) WHERE n.name = $name "
                "RETURN n.uid AS uid LIMIT 1",
                {"name": name},
            )
        return results[0][0] if results else None

    def find_uid_by_qualified_name(self, qualified_name: str) -> str | None:
        """Look up uid for a node by qualified_name."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.qualified_name = $qn "
            "RETURN n.uid AS uid LIMIT 1",
            {"qn": qualified_name},
        )
        return results[0][0] if results else None

    def find_all_by_qualified_name(
        self, qualified_name: str
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *qualified_name*."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.qualified_name = $qn RETURN n",
            {"qn": qualified_name},
        )
        out: list[CodeGraphNode] = []
        for row in results:
            node = self._inflate_by_labels(row[0])
            if node is not None:
                out.append(node)
        return out

    def _inflate_by_labels(self, raw) -> "CodeGraphNode | None":
        """Inflate a raw Bolt node by matching its labels to the registry.

        Handles both neomodel classes (via their own ``.inflate()``)
        and pure-Python classes (constructed from properties).
        """
        labels = set(raw.labels) if hasattr(raw, "labels") else set()
        target_type = best_class_for_labels(labels)
        if target_type is None:
            return None
        if issubclass(target_type, StructuredNode):
            return target_type.inflate(raw)
        raw_props = dict(raw.items()) if hasattr(raw, "items") else {}
        props = _inflate_props(target_type, raw_props)
        instance = target_type(**props)
        if hasattr(raw, "element_id"):
            instance.element_id_property = raw.element_id
        return instance

    def find_qualified_name_by_uid(self, uid: str) -> str | None:
        """Look up qualified_name for a node by uid."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid "
            "RETURN n.qualified_name AS qn LIMIT 1",
            {"uid": uid},
        )
        return results[0][0] if results else None

    # ── Edge deletion ──────────────────────────────────────────

    def delete_outgoing_relationships(
        self, source_uid: str, rel_type: str
    ) -> int:
        """Delete all outgoing relationships of rel_type from node."""
        results, _ = db.cypher_query(
            f"MATCH (n)-[r:{rel_type}]->() "
            "WHERE n.uid = $uid "
            "DELETE r "
            "RETURN count(r) AS cnt",
            {"uid": source_uid},
        )
        return results[0][0] if results else 0

    # ── Existence check ────────────────────────────────────────

    def node_exists(self, uid: str) -> bool:
        """Check whether a node with given uid exists."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid RETURN count(n) AS cnt",
            {"uid": uid},
        )
        return results[0][0] > 0 if results else False

    # ── Tag-condition queries ───────────────────────────────────

    def find_uids_by_tag_condition(
        self,
        tag: str,
        *,
        condition_clause: str = "",
        params: dict | None = None,
    ) -> list[str]:
        """Return uids for nodes with tag + optional condition."""
        cypher = "MATCH (n) WHERE $tag IN coalesce(n.tags, []) "
        if condition_clause:
            cypher += f"AND {condition_clause} "
        cypher += "RETURN n.uid AS uid"
        results, _ = db.cypher_query(cypher, {"tag": tag, **(params or {})})
        return [r[0] for r in results]

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

        Falls back to a CONTAINS search if the index doesn't exist.
        """
        try:
            cypher = (
                f"CALL db.index.fulltext.queryNodes('{index_name}', $query) "
                "YIELD node, score "
            )
            params: dict = {"query": query, "limit": limit}
            if tag:
                cypher += "WHERE $tag IN node.tags "
                params["tag"] = tag
            cypher += "RETURN node, score ORDER BY score DESC LIMIT $limit"
            results, _ = db.cypher_query(cypher, params, resolve_objects=True)
            return [
                {"node": r[0], "score": r[1]}
                for r in results
                if r[0] is not None
            ]
        except Exception:
            # Fallback: CONTAINS search
            label_clause = f"m:{labels}" if labels else "m"
            tag_clause = ""
            params: dict = {"query": query, "limit": limit}
            if tag:
                tag_clause = "AND $tag IN m.tags "
                params["tag"] = tag
            cypher = (
                f"MATCH ({label_clause}) "
                "WHERE (toLower(m.content) CONTAINS toLower($query) "
                "OR toLower(m.qualified_name) CONTAINS toLower($query)) "
                f"{tag_clause}"
                "RETURN m AS node, 1.0 AS score "
                "LIMIT $limit"
            )
            results, _ = db.cypher_query(cypher, params)
            out = []
            for r in results:
                if r[0] is None:
                    continue
                node = self._inflate_by_labels(r[0])
                if node is not None:
                    out.append({"node": node, "score": 1.0})
            return out

    # ── Bulk label queries ───────────────────────────────────

    def get_all_node_labels(self) -> list[dict]:
        """Return qualified_name, labels, and uid for every node."""
        results, _ = db.cypher_query(
            "MATCH (n) "
            "RETURN coalesce(n.qualified_name, '(none)') AS qualified_name, "
            "labels(n) AS labels, n.uid AS uid "
            "ORDER BY qualified_name",
        )
        return [
            {"qualified_name": r[0], "labels": r[1], "uid": r[2]}
            for r in results
        ]

    def find_nodes_with_labels(self, labels: list[str]) -> list[dict]:
        """Find nodes that carry ALL of the specified labels.

        Returns ``[{"qualified_name": str, "labels": list[str], "uid": str}]``.
        """
        label_pattern = ":".join(f"`{l}`" for l in labels)
        results, _ = db.cypher_query(
            f"MATCH (n:{label_pattern}) "
            "RETURN coalesce(n.qualified_name, '(none)') AS qualified_name, "
            "labels(n) AS labels, n.uid AS uid",
        )
        return [
            {"qualified_name": r[0], "labels": r[1], "uid": r[2]}
            for r in results
        ]

    def count_all_nodes(self) -> int:
        """Return the total number of nodes in the graph."""
        results, _ = db.cypher_query("MATCH (n) RETURN count(n) AS c")
        return results[0][0] if results else 0

    # ── Vector / semantic search ────────────────────────────────

    def search_vector(
        self,
        embedding: list[float],
        *,
        index_name: str = "",
        labels: str = "",
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Vector similarity search across node embeddings.

        Returns empty list if vector index is not available.
        """
        if not embedding:
            return []
        try:
            cypher = (
                f"CALL db.index.vector.queryNodes('{index_name}', $limit, $embedding) "
                "YIELD node, score "
            )
            params: dict = {"embedding": embedding, "limit": limit}
            if tag:
                cypher += "WHERE $tag IN node.tags "
                params["tag"] = tag
            cypher += "RETURN node, score ORDER BY score DESC"
            results, _ = db.cypher_query(cypher, params)
            out = []
            for r in results:
                if r[0] is None:
                    continue
                node = self._inflate_by_labels(r[0])
                if node is not None:
                    out.append({"node": node, "score": r[1]})
            return out
        except Exception:
            return []
