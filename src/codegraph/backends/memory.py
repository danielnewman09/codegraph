"""In-memory backend — stores CodeGraphNode instances in Python dicts.

Useful for unit testing, rapid prototyping, and CLI dry-runs.
Implements the full ``Backend`` ABC with zero external dependencies.

Usage::

    from codegraph.backends.memory import InMemoryBackend
    from codegraph.backends import set_backend

    backend = InMemoryBackend()
    set_backend(backend)

    node = ClassNode(name="Widget", source="test")
    node.save()  # stores in memory
    node.delete()  # removes from memory
"""

from __future__ import annotations

import logging

from codegraph.backends.interface import Backend, BackendConfig, EdgeDescriptor

log = logging.getLogger(__name__)


class InMemoryBackend(Backend):
    """Stores all nodes and edges in Python dicts with no persistence.

    Nodes are stored as live ``CodeGraphNode`` instances keyed by uid.
    Edges are stored as adjacency lists keyed by source uid.
    """

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self, config: BackendConfig) -> None:
        """No-op — nothing to set up."""
        self._nodes: dict[str, "CodeGraphNode"] = {}
        self._edges_out: dict[str, list[EdgeDescriptor]] = {}
        self._edges_in: dict[str, list[EdgeDescriptor]] = {}

    def health_check(self) -> bool:
        """Always healthy."""
        return True

    # ── Node CRUD ────────────────────────────────────────────────────

    def save(self, node: "CodeGraphNode") -> "CodeGraphNode":
        """Store the node in memory, computing uid if needed.

        Raises ValueError if source or identity fields are empty.
        """
        from codegraph.models.tags import CodeGraphNode

        # Ensure qualified_name is set before computing uid.
        props_def = type(node).defined_properties()
        if "qualified_name" in props_def and not getattr(node, "qualified_name", ""):
            node.qualified_name = node._compute_qualified_name()

        node.uid = node._compute_uid()
        self._nodes[node.uid] = node
        return node

    def delete(self, node: "CodeGraphNode") -> None:
        """Delete node after cascading to COMPOSES children."""
        # Cascade: delete composed children first
        for child in self.get_composed_children(node):
            self.delete(child)

        # Remove all edges involving this node
        uid = node._uid_value()
        if uid:
            self._edges_out.pop(uid, None)
            self._edges_in.pop(uid, None)
            # Remove edges where this node is the target
            for src_uid, edges in list(self._edges_out.items()):
                self._edges_out[src_uid] = [
                    e for e in edges if e.target_uid != uid
                ]
            for src_uid, edges in list(self._edges_in.items()):
                self._edges_in[src_uid] = [
                    e for e in edges if e.target_uid != uid
                ]
            self._nodes.pop(uid, None)

    def get(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> "CodeGraphNode | None":
        """Find a single node by field filters."""
        for node in self._nodes.values():
            if not isinstance(node, node_type):
                continue
            if all(
                getattr(node, key, None) == value
                for key, value in filters.items()
            ):
                return node
        return None

    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        """Return the raw node as-is (already a live instance)."""
        if isinstance(raw, node_type):
            return raw
        uid = raw if isinstance(raw, str) else str(raw)
        node = self._nodes.get(uid)
        if node is None:
            raise KeyError(f"No node with uid {uid} in memory store")
        return node

    # ── Tag queries ──────────────────────────────────────────────────

    def _find_by_tag_impl(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        return [
            n for n in self._nodes.values()
            if isinstance(n, node_type) and tag in (n.tags or [])
        ]

    def _find_all_by_tag_impl(self, tag: str) -> list["CodeGraphNode"]:
        return [
            n for n in self._nodes.values()
            if hasattr(n, "tags") and tag in (n.tags or [])
        ]

    def _find_all_by_source_impl(self, source: str) -> list["CodeGraphNode"]:
        return [
            n for n in self._nodes.values()
            if getattr(n, "source", None) == source
        ]

    def _find_all_by_kind_impl(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        results = [
            n for n in self._nodes.values()
            if getattr(n, "kind", None) == kind
        ]
        if tag is not None:
            results = [n for n in results if tag in (getattr(n, "tags", None) or [])]
        return results

    # ── Relationship operations ──────────────────────────────────────

    def connect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Create a relationship between two saved nodes.

        Validates via the neomodel relationship manager (same as Neo4j).
        """
        from codegraph.backends.neo4j.rel_ops import Neo4jRelOps
        manager = Neo4jRelOps._find_manager(source, rel_type, target)
        manager.connect(target)

        # Also track in our in-memory adjacency list
        src_uid = source._uid_value()
        tgt_uid = target._uid_value()
        if src_uid and tgt_uid:
            edge = EdgeDescriptor(
                relation_type=rel_type,
                target_uid=tgt_uid,
                target_type=type(target).__name__,
                is_outgoing=True,
            )
            self._edges_out.setdefault(src_uid, []).append(edge)
            in_edge = EdgeDescriptor(
                relation_type=rel_type,
                target_uid=src_uid,
                target_type=type(source).__name__,
                is_outgoing=False,
            )
            self._edges_in.setdefault(tgt_uid, []).append(in_edge)

    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Remove a single relationship."""
        src_uid = source._uid_value()
        tgt_uid = target._uid_value()
        if src_uid:
            self._edges_out[src_uid] = [
                e for e in self._edges_out.get(src_uid, [])
                if not (e.relation_type == rel_type and e.target_uid == tgt_uid)
            ]
        if tgt_uid:
            self._edges_in[tgt_uid] = [
                e for e in self._edges_in.get(tgt_uid, [])
                if not (e.relation_type == rel_type and e.target_uid == src_uid)
            ]

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return nodes reachable via outgoing COMPOSES edges."""
        uid = node._uid_value()
        if not uid:
            return []
        return [
            self._nodes[e.target_uid]
            for e in self._edges_out.get(uid, [])
            if e.relation_type == "COMPOSES" and e.target_uid in self._nodes
        ]

    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return all edges (incoming and outgoing)."""
        uid = node._uid_value()
        if not uid:
            return []
        return self._edges_out.get(uid, []) + self._edges_in.get(uid, [])

    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges."""
        uid = node._uid_value()
        if not uid:
            return []
        return self._edges_out.get(uid, [])

    # ── Bulk operations ──────────────────────────────────────────────

    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Save all nodes and relationships from a LayerGraph."""
        from codegraph.graph import CompositeEntry

        def _save_entry(entry: CompositeEntry) -> None:
            self.save(entry.node)
            for children in entry.children.values():
                for child_entry in children.values():
                    _save_entry(child_entry)
                    self.connect(entry.node, "COMPOSES", child_entry.node)

        for entry in layer_graph.entries.values():
            _save_entry(entry)

        # Connect reference edges
        for entry in layer_graph.entries.values():
            _connect_refs(entry, layer_graph)

        def _connect_refs(entry: CompositeEntry, graph) -> None:
            for rel_type, target_key, _target_type in entry.references:
                target_entry = graph.entries.get(target_key)
                if target_entry is not None:
                    self.connect(entry.node, rel_type, target_entry.node)
            for children in entry.children.values():
                for child_entry in children.values():
                    _connect_refs(child_entry, graph)

    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with *tag* plus 1-hop neighbors."""
        seeds = self._find_all_by_tag_impl(tag)
        seen = {n._uid_value() for n in seeds if n._uid_value()}
        result = list(seeds)

        for seed in seeds:
            seed_uid = seed._uid_value()
            if not seed_uid:
                continue
            for edge in self._edges_out.get(seed_uid, []):
                neighbor = self._nodes.get(edge.target_uid)
                if neighbor and neighbor._uid_value() not in seen:
                    seen.add(neighbor._uid_value())
                    result.append(neighbor)
            for edge in self._edges_in.get(seed_uid, []):
                neighbor = self._nodes.get(edge.target_uid)
                if neighbor and neighbor._uid_value() not in seen:
                    seen.add(neighbor._uid_value())
                    result.append(neighbor)

        return result

    # ── Raw query ────────────────────────────────────────────────────

    def wipe(self) -> None:
        """Clear all stored nodes and edges from memory."""
        self._nodes.clear()
        self._edges_out.clear()
        self._edges_in.clear()

    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Not supported for in-memory backend.

        Raises NotImplementedError — use the typed query methods instead.
        """
        raise NotImplementedError(
            "execute_raw is not supported for the in-memory backend. "
            "Use save(), get(), find_by_tag(), etc. instead."
        )
