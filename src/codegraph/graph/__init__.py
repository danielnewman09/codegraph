"""LayerGraph — layer-aware graph container for codebase views.

A Python-only container that holds all nodes and edges in a design view,
keyed by a stable local identifier. Supports deserialization from JSON,
persistence to Neo4j, and querying from Neo4j by layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.models.tags import CodeGraphNode


@dataclass
class LayerGraph:
    """A Python-only container for all nodes in a design view, filtered by layer.

    Nodes are keyed by a stable local identifier (name for most nodes,
    path for FileNode). Edges are stored as logical tuples for deferred
    persistence via ``to_neo4j()``.

    Attributes:
        layer: The design view layer ("design", "as-built", or "dependency").
        nodes: Dict mapping stable local keys to CodeGraphNode instances.
        edges: List of logical edge dicts for deferred Neo4j persistence.
    """

    layer: str  # "design" | "as-built" | "dependency"
    nodes: dict[str, CodeGraphNode] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)

    @staticmethod
    def _node_key(obj) -> str:
        """Derive a stable local key from a node instance or raw dict.

        For dicts (raw JSON data), uses ``type`` and ``path``/``name``.
        For CodeGraphNode instances, uses ``path`` for FileNode, ``name``
        otherwise.
        """
        if isinstance(obj, dict):
            if obj.get("type") == "FileNode":
                return obj["path"]
            return obj["name"]
        # CodeGraphNode instance
        if obj.__class__.__name__ == "FileNode":
            return obj.path
        return obj.name

    @classmethod
    def from_json(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from a JSON array (as produced by ``to_json()``).

        Pure deserialization — no database interaction. Infers layer from
        the first node that has a ``layer`` field (fallback: ``"design"``).

        Accepts edges in two formats:
        - Fixture format: ``target_local_id`` (name or path) + ``target_type``
        - Serialized format: ``target_uid`` (unique id) + ``target_type``
        """
        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}  # uid → node_key lookup
        edges: list[dict] = []
        layer = "design"

        for node_data in data:
            node = CodeGraphNode.from_json(node_data)
            key = cls._node_key(node_data)
            nodes[key] = node

            # Build uid → key mapping for roundtrip format
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

            # Collect logical edges for later persistence
            for edge in node_data.get("edges", []):
                # Resolve target key: prefer target_local_id (fixture format),
                # fall back to target_uid (serialized format)
                target_key = edge.get("target_local_id")
                if target_key is None and "target_uid" in edge:
                    target_key = uid_to_key.get(edge["target_uid"])
                edges.append({
                    "source_key": key,
                    "relation_type": edge["relation_type"],
                    "target_key": target_key,
                    "target_type": edge["target_type"],
                })

            # Infer layer from node data
            if layer == "design" and "layer" in node_data:
                layer = node_data["layer"]

        return cls(layer=layer, nodes=nodes, edges=edges)

    def to_neo4j(self) -> None:
        """Persist all nodes and edges to Neo4j.

        Saves each node, then connects all edges using
        ``CodeGraphNode.find_relationship_manager()``.
        """
        # Phase 1: Save all nodes
        for node in self.nodes.values():
            node.save()

        # Phase 2: Connect all edges
        for edge in self.edges:
            source = self.nodes[edge["source_key"]]
            target = self.nodes[edge["target_key"]]
            manager = CodeGraphNode.find_relationship_manager(
                source, edge["relation_type"], target
            )
            manager.connect(target)

    def to_json(self) -> list[dict]:
        """Serialize all nodes + edges to a JSON-compatible list of dicts.

        Each dict includes ``type``, properties, and ``edges``.
        Calls ``node.serialize()`` on each node (which includes live edges
        from Neo4j if the node has been saved).

        For nodes that have not been persisted to Neo4j, the ``edges``
        key will be an empty list.

        Returns:
            A list of serialized node dicts suitable for JSON output.
        """
        return [node.serialize() for node in self.nodes.values()]

    @classmethod
    def from_neo4j(cls, layer: str) -> "LayerGraph":
        """Query Neo4j for all nodes where ``.layer == layer``, plus their
        first-level neighbors. Collect into a LayerGraph.

        This includes both endpoints of any edge touching a layer-matched
        node, even if the neighbor's layer is different.

        Args:
            layer: The layer to query for (e.g. "design", "as-built",
                "dependency").

        Returns:
            A LayerGraph containing all matching nodes and their first-level
            neighbors.
        """
        # Fetch all layer-matched nodes
        matched_nodes = CodeGraphNode.fetch_all_by_layer(layer)

        nodes: dict[str, CodeGraphNode] = {}
        seen_uids: set[str] = set()

        # Add all layer-matched nodes
        for node in matched_nodes:
            key = cls._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                seen_uids.add(uid)

        # Expand to first-level neighbors
        for node in matched_nodes:
            edges = node.serialize_edges()
            for edge in edges:
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    # Fetch neighbor from Neo4j by UID
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = target_cls.nodes.get_or_none(
                                **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = cls._node_key(neighbor)
                                nodes[neighbor_key] = neighbor

        return cls(layer=layer, nodes=nodes)