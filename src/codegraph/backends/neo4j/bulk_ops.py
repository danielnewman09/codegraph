"""Neo4j bulk operations — save/load LayerGraphs.

Extracted from ``codegraph.graph.LayerGraph.to_neo4j()`` and
``codegraph.graph.LayerGraph.from_neo4j()``.
"""

from __future__ import annotations

import logging

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.node_ops import Neo4jNodeOps
from codegraph.backends.neo4j.rel_ops import Neo4jRelOps

from codegraph.graph import CompositeEntry
from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode

log = logging.getLogger(__name__)


class Neo4jBulkOps:
    """Bulk save/load operations for LayerGraph -> Neo4j."""

    def __init__(
        self,
        conn: Neo4jConnection,
        node_ops: Neo4jNodeOps,
        rel_ops: Neo4jRelOps,
    ):
        self._conn = conn
        self._node_ops = node_ops
        self._rel_ops = rel_ops

    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Persist all nodes and relationships in a LayerGraph to Neo4j.

        Walks the entry tree depth-first.  Saves every node, then
        connects COMPOSES children and reference edges.
        """

        # Build flat indexes for resolving reference targets.
        flat: dict[str, CompositeEntry] = {}
        qname_index: dict[str, CompositeEntry] = {}
        for entry in layer_graph._all_entries():
            key = LayerGraph._node_key(entry.node)
            flat[key] = entry
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                qname_index[qname] = entry

        # Phase 1: save all nodes
        for entry in layer_graph._all_entries():
            self._node_ops.save(entry.node)

        # Phase 2: connect relationships
        for entry in layer_graph._all_entries():
            source_node = entry.node

            # Connect COMPOSES children
            for _target_type, type_children in entry.children.items():
                for _child_key, child_entry in type_children.items():
                    self._rel_ops.connect(
                        source_node, "COMPOSES", child_entry.node
                    )

            # Connect references
            for relation_type, target_key, target_type in entry.references:
                target_entry = flat.get(target_key) or qname_index.get(target_key)
                if target_entry is not None:
                    self._rel_ops.connect(
                        source_node, relation_type, target_entry.node
                    )


    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with tag plus 1-hop neighbors.

        Returns a flat list of nodes.  Tree construction is done by
        ``LayerGraph.from_backend()``.
        """

        nodes: dict[str, "CodeGraphNode"] = {}
        uid_to_key: dict[str, str] = {}
        seen_uids: set[str] = set()

        # Fetch all tag-matched nodes
        matched_nodes = self._node_ops.find_all_by_tag(tag)

        for node in matched_nodes:
            key = _node_key_safe(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key
                seen_uids.add(uid)

        # Expand to first-level neighbors
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
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = self._node_ops.get(
                                target_cls, **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = _node_key_safe(neighbor)
                                nodes[neighbor_key] = neighbor
                                uid_to_key[target_uid] = neighbor_key

        # Second pass: pull in namespace parents of non-project 1-hop neighbours
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
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            parent_ns = self._node_ops.get(
                                target_cls, **{uid_prop: target_uid}
                            )
                            if parent_ns:
                                ns_key = _node_key_safe(parent_ns)
                                nodes[ns_key] = parent_ns
                                uid_to_key[target_uid] = ns_key

        return list(nodes.values())


def _node_key_safe(obj) -> str:
    """Derive a stable local key from a node instance.

    Delegates to LayerGraph._node_key() but avoids circular imports
    by using the static version.
    """
    return LayerGraph._node_key(obj)
