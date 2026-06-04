"""GraphRepository — data access layer for the codebase graph.

Provides scope-based read methods that return LayerGraph objects, plus a
single bulk write method.  Uses neomodel ORM for all queries.
"""

from __future__ import annotations

from codegraph.graph import LayerGraph
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

        Returns first match or None.
        """
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _get_member_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search member types by qualified_name.

        Returns first match or None.
        """
        for node_cls in _MEMBER_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _build_layer_graph(seeds: list[CodeGraphNode]) -> LayerGraph:
        """Build a LayerGraph from seed nodes plus 1-hop neighbors.

        1. Collect seed nodes keyed by _node_key.
        2. Expand 1-hop neighbors via serialize_edges().
        3. Collect edges where both endpoints are present.
        4. Infer layer from first seed with a 'layer' property.
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

        # Phase 3: collect edges where both endpoints are present
        edges: list[dict] = []
        keys_present = set(nodes.keys())
        for node in nodes.values():
            source_key = LayerGraph._node_key(node)
            for edge_info in node.serialize_edges():
                target_uid = edge_info["target_uid"]
                target_key = uid_to_key.get(target_uid)
                if target_key is not None and target_key in keys_present:
                    edges.append({
                        "source_key": source_key,
                        "relation_type": edge_info["relation_type"],
                        "target_key": target_key,
                        "target_type": edge_info["target_type"],
                    })

        # Phase 4: derive layer
        layer = "design"
        for node in seeds:
            if "layer" in type(node).defined_properties():
                layer = getattr(node, "layer", "design") or "design"
                break

        return LayerGraph(layer=layer, nodes=nodes, edges=edges)

    # ── Public: scope-based read methods ──────────────────────────────

    def get_by_layer(self, layer: str) -> LayerGraph:
        """Fetch all nodes in a layer plus their 1-hop neighbors."""
        seeds = CodeGraphNode.fetch_all_by_layer(layer)
        return self._build_layer_graph(seeds)

    def get_by_source(self, source: str) -> LayerGraph:
        """Fetch all nodes from a given source project plus neighbors."""
        seeds = CodeGraphNode.fetch_all_by_source(source)
        return self._build_layer_graph(seeds)

    def get_by_namespace(self, qualified_name: str) -> LayerGraph:
        """Fetch a namespace, its compounds, and their 1-hop neighbors."""
        ns = NamespaceNode.nodes.get_or_none(qualified_name=qualified_name)
        if ns is None:
            return LayerGraph(layer="design")
        seeds = [ns] + list(ns.compounds.all())
        return self._build_layer_graph(seeds)

    def get_by_compound(self, qualified_name: str) -> LayerGraph:
        """Fetch a compound node and its 1-hop neighbors."""
        compound = self._get_node_by_qualified_name(qualified_name)
        if compound is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([compound])

    def get_by_neighbourhood(self, qualified_name: str) -> LayerGraph:
        """Fetch a node of any type and its 1-hop neighbourhood."""
        node = self._get_node_by_qualified_name(qualified_name)
        if node is None:
            node = self._get_member_by_qualified_name(qualified_name)
        if node is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([node])

    def get_by_kind(self, kind: str, layer: str | None = None) -> LayerGraph:
        """Fetch all nodes of a given kind, optionally filtered by layer."""
        seeds = CodeGraphNode.fetch_all_by_kind(kind, layer=layer)
        return self._build_layer_graph(seeds)

    # ── Public: write method ──────────────────────────────────────────

    @staticmethod
    def save_layer_graph(graph: LayerGraph) -> None:
        """Persist a LayerGraph to Neo4j. Delegates to LayerGraph.to_neo4j()."""
        graph.to_neo4j()