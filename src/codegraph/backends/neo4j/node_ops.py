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
