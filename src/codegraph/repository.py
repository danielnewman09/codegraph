"""GraphRepository — data access layer for the codebase graph.

Provides scope-based read methods that return LayerGraph objects, plus a
single bulk write method.  Uses neomodel ORM for all queries.
"""

from __future__ import annotations

from codegraph.constants import Layer
from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
)
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

_COMPOUND_TYPES = [ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode]
_MEMBER_TYPES = [MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode]
_NAMESPACE_TYPES = [NamespaceNode]


class GraphRepository:
    """Data access layer for the codebase graph.

    All read methods return LayerGraph objects.  The single write method
    delegates to LayerGraph.to_neo4j().
    """

    # ── Private helpers ────────────────────────────────────────────────

    @staticmethod
    def _get_node_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search compound and namespace types by qualified_name.

        Args:
            qualified_name: The fully-qualified name to search for.

        Returns:
            First matching CodeGraphNode instance, or None if not found.
        """
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _get_member_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search member types by qualified_name.

        Args:
            qualified_name: The fully-qualified name to search for.

        Returns:
            First matching CodeGraphNode instance, or None if not found.
        """
        for node_cls in _MEMBER_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _build_layer_graph(seeds: list[CodeGraphNode]) -> LayerGraph:
        """Build a LayerGraph from seed nodes plus 1-hop neighbors.

        Args:
            seeds: List of seed CodeGraphNode instances to start from.

        Returns:
            A LayerGraph containing seed nodes and their 1-hop neighbors,
            with COMPOSES edges creating nesting and other edges as
            references.
        """
        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}

        # Phase 1: add seed nodes
        for node in seeds:
            key = LayerGraph._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

        # Phase 2: expand 1-hop neighbors
        for node in list(seeds):
            for edge_info in node.serialize_edges():
                target_uid = edge_info["target_uid"]
                target_type = edge_info["target_type"]
                if target_uid not in uid_to_key:
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = target_cls.nodes.get_or_none(
                                **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = LayerGraph._node_key(neighbor)
                                nodes[neighbor_key] = neighbor
                                uid_to_key[target_uid] = neighbor_key

        # Phase 3: build CompositeEntry instances
        key_to_entry: dict[str, CompositeEntry] = {}
        for key, node in nodes.items():
            key_to_entry[key] = CompositeEntry(node=node)

        # Phase 4: walk edges and build nesting / references
        child_keys: set[str] = set()
        for node in nodes.values():
            source_key = LayerGraph._node_key(node)
            source_entry = key_to_entry[source_key]

            for edge_info in node.serialize_edges():
                relation_type = edge_info["relation_type"]
                target_uid = edge_info["target_uid"]
                target_type = edge_info["target_type"]
                target_key = uid_to_key.get(target_uid)

                if target_key is None or target_key not in key_to_entry:
                    continue

                if relation_type == "COMPOSES":
                    target_entry = key_to_entry[target_key]
                    if target_type not in source_entry.children:
                        source_entry.children[target_type] = {}
                    source_entry.children[target_type][target_key] = target_entry
                    child_keys.add(target_key)
                else:
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )

        # Phase 5: root entries = nodes not composed by another node
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        # Phase 6: derive layer
        layer: Layer = "design"
        for node in seeds:
            if "layer" in type(node).defined_properties():
                layer = getattr(node, "layer", "design") or "design"  # type: ignore[assignment]
                break

        return LayerGraph(layer=layer, entries=root_entries)

    # ── Public: scope-based read methods ──────────────────────────────

    def get_by_layer(self, layer: Layer) -> LayerGraph:
        """Fetch all nodes in a layer plus their 1-hop neighbors.

        Args:
            layer: The layer to query (``"design"``, ``"as-built"``, ``"dependency"``).

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = CodeGraphNode.fetch_all_by_layer(layer)
        return self._build_layer_graph(seeds)

    def get_by_source(self, source: str) -> LayerGraph:
        """Fetch all nodes from a given source project plus neighbors.

        Args:
            source: The source project name (e.g. "codegraph", "llvm").

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = CodeGraphNode.fetch_all_by_source(source)
        return self._build_layer_graph(seeds)

    def get_by_namespace(self, qualified_name: str) -> LayerGraph:
        """Fetch a namespace, its composed entities, and their 1-hop neighbors.

        Retrieves a namespace and all entities it composes (classes, interfaces,
        enums, unions, modules, functions, and sub-namespaces), plus their
        1-hop neighbors.

        Args:
            qualified_name: The namespace's fully-qualified name.

        Returns:
            A LayerGraph containing the namespace and related nodes,
            or an empty LayerGraph if not found.
        """
        ns = NamespaceNode.nodes.get_or_none(qualified_name=qualified_name)
        if ns is None:
            return LayerGraph(layer="design")
        seeds = (
            [ns]
            + list(ns.classes.all())
            + list(ns.interfaces.all())
            + list(ns.enums.all())
            + list(ns.unions.all())
            + list(ns.modules.all())
            + list(ns.functions.all())
            + list(ns.namespaces.all())
        )
        return self._build_layer_graph(seeds)

    def get_by_compound(self, qualified_name: str) -> LayerGraph:
        """Fetch a compound node and its 1-hop neighbors.

        Args:
            qualified_name: The compound's fully-qualified name.

        Returns:
            A LayerGraph containing the compound and its neighbors,
            or an empty LayerGraph if not found.
        """
        compound = self._get_node_by_qualified_name(qualified_name)
        if compound is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([compound])

    def get_by_neighbourhood(self, qualified_name: str) -> LayerGraph:
        """Fetch a node of any type and its 1-hop neighbourhood.

        Args:
            qualified_name: The node's fully-qualified name.

        Returns:
            A LayerGraph containing the node and its 1-hop neighbourhood,
            or an empty LayerGraph if not found.
        """
        node = self._get_node_by_qualified_name(qualified_name)
        if node is None:
            node = self._get_member_by_qualified_name(qualified_name)
        if node is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([node])

    def get_by_kind(self, kind: str, layer: Layer | None = None) -> LayerGraph:
        """Fetch all nodes of a given kind, optionally filtered by layer.

        Args:
            kind: The node kind to filter by (e.g. "class", "method").
            layer: Optional layer to additionally filter by.

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = CodeGraphNode.fetch_all_by_kind(kind, layer=layer)
        return self._build_layer_graph(seeds)

    # ── Public: write method ──────────────────────────────────────────

    @staticmethod
    def save_layer_graph(graph: LayerGraph) -> None:
        """Persist a LayerGraph to Neo4j. Delegates to LayerGraph.to_neo4j().

        Args:
            graph: The LayerGraph to persist.
        """
        graph.to_neo4j()