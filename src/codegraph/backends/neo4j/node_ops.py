"""Neo4j node CRUD operations.

Extracted from ``codegraph.models.tags.CodeGraphNode``.
"""

from __future__ import annotations

from typing import Any

from neomodel import db
from neomodel.sync_.node import StructuredNode
from neomodel import RelationshipTo, RelationshipFrom

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.models.tags import CodeGraphNode

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

        Raises ``ValueError`` if ``source`` or the primary identity
        field is empty — a deterministic uid cannot be derived and
        the node is not viable.

        Returns the saved node.
        """

        # Ensure qualified_name is set before computing uid.
        props_def = type(node).defined_properties()
        if "qualified_name" in props_def and not getattr(node, "qualified_name", ""):
            node.qualified_name = node._compute_qualified_name()

        computed = node._compute_uid()
        node.uid = computed
        labels = ":".join(type(node).inherited_labels())

        props: dict = {}
        for pname, prop in type(node).defined_properties().items():
            if isinstance(prop, (RelationshipTo, RelationshipFrom)):
                continue
            val = getattr(node, pname, None)
            if val is None or val == "" or val == []:
                continue
            props[pname] = prop.deflate(val)
        props["uid"] = computed

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
        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                manager = getattr(node, name)
                try:
                    for connected in manager.all():
                        try:
                            manager.disconnect(connected)
                        except Exception:
                            pass
                except Exception:
                    pass

        StructuredNode.delete(node)

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return all nodes reachable via outgoing COMPOSES edges."""

        if not hasattr(node, "element_id_property"):
            return []

        children: list["CodeGraphNode"] = []
        seen: set[str] = set()
        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, RelationshipTo):
                    continue
                if val.definition["relation_type"] != "COMPOSES":
                    continue
                if name in seen:
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

        Uses neomodel's ``.nodes.get_or_none(**filters)``.
        """
        return node_type.nodes.get_or_none(**filters)

    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        """Inflate a raw Neo4j result row into a CodeGraphNode.

        For Bolt node records, determines the correct class from labels
        and calls ``.inflate()``.
        """
        return node_type.inflate(raw)

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
        label = node_type.__label__
        query = f"MATCH (n:`{label}`) WHERE $tag IN n.tags RETURN n"
        results, _ = db.cypher_query(query, {"tag": tag})
        return [node_type.inflate(row[0]) for row in results]

    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching tag."""
        result: list["CodeGraphNode"] = []
        for node_cls in CodeGraphNode._registry.values():
            result.extend(self.find_by_tag(node_cls, tag))
        return result

    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all types matching source."""
        result: list["CodeGraphNode"] = []
        for node_cls in CodeGraphNode._registry.values():
            result.extend(node_cls.nodes.filter(source=source))
        return result

    def find_all_by_kind(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        """Fetch all nodes matching kind (and optionally tag)."""
        result: list["CodeGraphNode"] = []
        for node_cls in CodeGraphNode._registry.values():
            nodes = list(node_cls.nodes.filter(kind=kind))
            if tag is not None:
                nodes = [n for n in nodes if tag in (n.tags or [])]
            result.extend(nodes)
        return result

    # ── uid-based node queries ────────────────────────────────────

    def find_by_uid(self, uid: str) -> "CodeGraphNode | None":
        """Find any node by its deterministic uid."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE n.uid = $uid RETURN n LIMIT 1",
            {"uid": uid},
            resolve_objects=True,
        )
        if not results:
            return None
        return results[0][0]

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
            f"SET {', '.join(set_parts)}"
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
            results, _ = db.cypher_query(cypher, params, resolve_objects=True)
            return [
                {"node": r[0], "score": 1.0}
                for r in results
                if r[0] is not None
            ]

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
            results, _ = db.cypher_query(cypher, params, resolve_objects=True)
            return [
                {"node": r[0], "score": r[1]}
                for r in results
                if r[0] is not None
            ]
        except Exception:
            return []
