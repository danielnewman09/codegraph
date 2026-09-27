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

    def __init__(self) -> None:
        """Initialise storage eagerly so the backend is usable immediately."""
        self._nodes: dict[str, "CodeGraphNode"] = {}
        # Canonical-key index (WP B): ``_nodes`` is keyed by the node's
        # canonical key — the sole storage identity.
        self._edges_out: dict[str, list[EdgeDescriptor]] = {}
        self._edges_in: dict[str, list[EdgeDescriptor]] = {}
        self._graph_repo: "InMemoryGraphRepository | None" = None
        self._memory_repo: "InMemoryMemoryRepository | None" = None
        self._requirements_repo: "InMemoryRequirementsRepository | None" = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def apply_schema(self) -> None:
        """In-memory backend needs no schema."""
        return None

    def initialize(self, config: BackendConfig) -> None:
        """No-op — nothing to set up."""
        pass

    def health_check(self) -> bool:
        """Always healthy."""
        return True

    def close(self) -> None:
        """No-op — no connection to tear down."""
        pass

    def reconnect(self) -> None:
        """No-op — nothing to re-establish."""
        pass

    # ── Repositories ──────────────────────────────────────────────────

    @property
    def graph(self) -> "GraphRepository":
        if self._graph_repo is None:
            self._graph_repo = InMemoryGraphRepository(self)
        return self._graph_repo

    @property
    def memory(self) -> "MemoryRepository":
        if self._memory_repo is None:
            self._memory_repo = InMemoryMemoryRepository(self)
        return self._memory_repo

    @property
    def requirements(self) -> "RequirementsRepository":
        if self._requirements_repo is None:
            self._requirements_repo = InMemoryRequirementsRepository(self)
        return self._requirements_repo

    # ── Node CRUD ────────────────────────────────────────────────────

    def save(
        self, node: "CodeGraphNode", *, derive_qualified_name: bool = True
    ) -> "CodeGraphNode":
        """Store the node in memory, computing uid if needed.

        ``derive_qualified_name`` separates the interactive write path from the
        bulk transport path.  ``qualified_name`` is a declared property that some
        node classes compute from their own fields (a ``FileNode`` uses its
        ``path``); ``save()`` fills it in for a node being written by hand, while
        ``bulk_save()`` writes a serialized document *verbatim* — a document that
        states an empty ``qualified_name`` must be stored with an empty
        ``qualified_name``, because unlike the SQL backends this backend keeps the
        live object, so a value derived here would become the stored value and the
        store would hold a property the document never carried.

        Raises ValueError if source or identity fields are empty.
        """
        from codegraph.models.descriptors import PropertyRegistry

        # Ensure qualified_name is set before keying.
        if (
            derive_qualified_name
            and PropertyRegistry.has_property(type(node), "qualified_name")
            and not getattr(node, "qualified_name", "")
        ):
            node.qualified_name = node._compute_qualified_name()

        # Canonical identity is mandatory (WP A): the model guarantees a
        # valid key before the backend sees the node.
        key = getattr(node, "canonical_key", "") or ""
        if not key:
            from codegraph.identity import IdentityError

            raise IdentityError(
                f"cannot save {type(node).__name__}: no canonical key"
            )
        # Upsert by key (MERGE semantics — the key is deterministic from
        # the node's identity, so a same-key save is the same logical
        # node; genuine cross-identity collisions cannot share a key).
        self._nodes[key] = node
        # Honor the element-id contract the other backends provide ("the
        # persisted node's element id, or None if unsaved"): serialize()
        # and update() gate on it.
        node.element_id_property = f"memory:{key}"
        return node

    def delete(self, node: "CodeGraphNode") -> None:
        """Delete node after cascading to COMPOSES children."""
        # Cascade: delete composed children first
        for child in self.get_composed_children(node):
            self.delete(child)

        # Remove all edges involving this node
        key = getattr(node, "canonical_key", "") or ""
        if key:
            self._edges_out.pop(key, None)
            self._edges_in.pop(key, None)
            # Remove edges where this node is the target
            for src_key, edges in list(self._edges_out.items()):
                self._edges_out[src_key] = [
                    e for e in edges if e.target_key != key
                ]
            for src_key, edges in list(self._edges_in.items()):
                self._edges_in[src_key] = [
                    e for e in edges if e.target_key != key
                ]
            self._nodes.pop(key, None)

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

    def find_all(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* matching field filters (or all)."""
        results = []
        for node in self._nodes.values():
            if not isinstance(node, node_type):
                continue
            if all(
                getattr(node, key, None) == value
                for key, value in filters.items()
            ):
                results.append(node)
        return results

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
        attributes: dict | None = None,
    ) -> None:
        """Create a relationship between two saved nodes.

        Validates that the relationship is declared on the source type
        (same semantics as the Neo4j backend), then tracks the edge in
        the in-memory adjacency lists.  *attributes* is optional
        relationship-level metadata (e.g. the include spelling on
        INCLUDES edges).

        The declaration check is this method's contract; the bulk path
        (:meth:`bulk_save`) is transport and does not re-check it — see
        :meth:`bulk_save`.
        """
        from codegraph.models.descriptors import find_relationship_descriptor

        descriptor = find_relationship_descriptor(
            type(source), rel_type, type(target)
        )
        if descriptor is None:
            raise ValueError(
                f"No '{rel_type}' relationship from "
                f"{type(source).__name__} to {type(target).__name__}"
            )
        self._record_edge(source, rel_type, target, attributes)

    def _record_edge(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
        attributes: dict | None = None,
    ) -> None:
        """Adjacency bookkeeping shared by :meth:`connect` and :meth:`bulk_save`.

        MERGE semantics, like every other backend: the relationship
        ``(source, rel_type, target)`` exists at most once, so saving the same
        graph twice cannot grow the edge set.  An identical re-record is a
        no-op; the first recorded attribute map wins, matching the SQLite bulk
        save's first-observation rule.
        """
        src_key = getattr(source, "canonical_key", "") or ""
        tgt_key = getattr(target, "canonical_key", "") or ""
        if not (src_key and tgt_key):
            return
        existing = self._edges_out.get(src_key, [])
        if any(
            edge.relation_type == rel_type and edge.target_key == tgt_key
            for edge in existing
        ):
            return
        self._edges_out.setdefault(src_key, []).append(EdgeDescriptor(
            relation_type=rel_type,
            target_key=tgt_key,
            target_type=type(target).__name__,
            is_outgoing=True,
            attributes=dict(attributes or {}),
        ))
        self._edges_in.setdefault(tgt_key, []).append(EdgeDescriptor(
            relation_type=rel_type,
            target_key=src_key,
            target_type=type(source).__name__,
            is_outgoing=False,
            attributes=dict(attributes or {}),
        ))

    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Remove a single relationship."""
        src_key = getattr(source, "canonical_key", "") or ""
        tgt_key = getattr(target, "canonical_key", "") or ""
        if src_key:
            self._edges_out[src_key] = [
                e for e in self._edges_out.get(src_key, [])
                if not (e.relation_type == rel_type and e.target_key == tgt_key)
            ]
        if tgt_key:
            self._edges_in[tgt_key] = [
                e for e in self._edges_in.get(tgt_key, [])
                if not (e.relation_type == rel_type and e.target_key == src_key)
            ]

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return nodes reachable via outgoing COMPOSES edges."""
        key = getattr(node, "canonical_key", "") or ""
        if not key:
            return []
        return [
            self._nodes[e.target_key]
            for e in self._edges_out.get(key, [])
            if e.relation_type == "COMPOSES" and e.target_key in self._nodes
        ]

    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return all edges (incoming and outgoing)."""
        key = getattr(node, "canonical_key", "") or ""
        if not key:
            return []
        return self._edges_out.get(key, []) + self._edges_in.get(key, [])

    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges."""
        key = getattr(node, "canonical_key", "") or ""
        if not key:
            return []
        return self._edges_out.get(key, [])

    # ── Bulk operations ──────────────────────────────────────────────

    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Persist every node and relationship the LayerGraph carries.

        This is the bulk transport path and mirrors the SQLite/Neo4j bulk
        saves: it stores the graph as its producer assembled it, without the
        per-edge declaration check :meth:`connect` performs.  The pure-Python
        model treats ``Relationship`` descriptors as advisory metadata (see
        ``Neo4jRelOps.connect``), and an indexed graph legitimately carries
        compositions the descriptor table has not caught up with — a class
        nesting an ``enum`` is the everyday case.  Refusing them here would
        make this the only backend that cannot hold an indexed graph, which is
        a harness limitation rather than a model guarantee.

        Reference targets resolve through the *flat* index, not the root-entry
        map: an edge to a composed node (a test step calling a method nested
        under its class) is not a root, and looking it up in
        ``layer_graph.entries`` alone dropped the edge silently.
        """
        from codegraph.graph import CompositeEntry, LayerGraph

        flat = layer_graph._flat_index()

        def _connect_refs(entry: CompositeEntry) -> None:
            for rel_type, target_key, _target_type in entry.references:
                target_entry = flat.get(target_key)
                if target_entry is not None:
                    self._record_edge(
                        entry.node, rel_type, target_entry.node,
                        attributes=entry.edge_attrs.get((rel_type, target_key)),
                    )
            for children in entry.children.values():
                for child_entry in children.values():
                    _connect_refs(child_entry)

        def _save_entry(entry: CompositeEntry) -> None:
            # Transport, not interactive authoring: the document's property
            # values are stored as written (see ``save`` for why).
            self.save(entry.node, derive_qualified_name=False)
            for children in entry.children.values():
                for child_entry in children.values():
                    _save_entry(child_entry)
                    self._record_edge(
                        entry.node, "COMPOSES", child_entry.node,
                        attributes=entry.edge_attrs.get(
                            ("COMPOSES",
                             LayerGraph._node_key(child_entry.node)),
                        ),
                    )

        for entry in layer_graph.entries.values():
            _save_entry(entry)

        # Connect reference edges
        for entry in layer_graph.entries.values():
            _connect_refs(entry)

    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with *tag* plus 1-hop neighbors."""
        seeds = self._find_all_by_tag_impl(tag)
        seen = {n.canonical_key for n in seeds if n.canonical_key}
        result = list(seeds)

        for seed in seeds:
            seed_key = seed.canonical_key
            if not seed_key:
                continue
            for edge in self._edges_out.get(seed_key, []):
                neighbor = self._nodes.get(edge.target_key)
                if neighbor and neighbor.canonical_key not in seen:
                    seen.add(neighbor.canonical_key)
                    result.append(neighbor)
            for edge in self._edges_in.get(seed_key, []):
                neighbor = self._nodes.get(edge.target_key)
                if neighbor and neighbor.canonical_key not in seen:
                    seen.add(neighbor.canonical_key)
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


# ══════════════════════════════════════════════════════════════════════════
# In-memory repository implementations
#
# These implement the full Backend ABC surface.  Node CRUD, relationships,
# and traversal delegate to the backend's dict store.  Query-heavy methods
# that require a Cypher/SQL engine (full-text, vector, layer-graph builders)
# raise ``NotImplementedError`` — the in-memory backend is for unit tests,
# prototyping, and dry-runs, not analytics.
# ══════════════════════════════════════════════════════════════════════════


class InMemoryGraphRepository:
    """In-memory implementation of ``GraphRepository``."""

    def __init__(self, backend: "InMemoryBackend") -> None:
        self._backend = backend

    # ── uid / qualified_name resolution ───────────────────────────

    def resolve_uid(self, qualified_name: str) -> str | None:
        """Compatibility shim — deprecated (WP C).  Returns the canonical
        key of the first node matching *qualified_name*."""
        node = self.find_by_qualified_name(qualified_name)
        return node.canonical_key if node else None

    def resolve_uid_by_name(self, name: str, *, label: str | None = None) -> str | None:
        for node in self._backend._nodes.values():
            if getattr(node, "name", None) == name:
                if label is None or label in type(node).inherited_labels():
                    return node.canonical_key
        return None

    def resolve_qualified_name(self, uid: str) -> str | None:
        node = self._backend._nodes.get(uid)
        return getattr(node, "qualified_name", None) if node else None

    # ── Node lookup ───────────────────────────────────────────────

    def find_by_uid(self, uid: str) -> "CodeGraphNode | None":
        """Compatibility shim (WP C): the canonical key IS the storage key."""
        return self._backend._nodes.get(uid)

    def find_by_key(self, key: str) -> "CodeGraphNode | None":
        return self._backend._nodes.get(key)

    def resolve_key(self, identity) -> str:
        """Resolve an identity to its canonical key (deterministic)."""
        return identity.key()

    def find_by_qualified_name(self, qualified_name: str) -> "CodeGraphNode | None":
        for node in self._backend._nodes.values():
            if getattr(node, "qualified_name", None) == qualified_name:
                return node
        return None

    def find_all_by_qualified_name(self, qualified_name: str) -> list["CodeGraphNode"]:
        return [
            n for n in self._backend._nodes.values()
            if getattr(n, "qualified_name", None) == qualified_name
        ]

    # ── Node label operations ─────────────────────────────────────

    def get_labels(self, uid: str) -> set[str]:
        node = self._backend._nodes.get(uid)
        if node is None:
            return set()
        return set(type(node).inherited_labels())

    def set_labels(self, uid: str, labels: list[str]) -> None:
        pass  # in-memory: labels are derived from the class

    def remove_labels(self, uid: str, labels: list[str]) -> None:
        pass

    # ── Bulk queries ─────────────────────────────────────────────

    def get_all_node_labels(self) -> list[dict[str, Any]]:
        return [
            {
                "qualified_name": getattr(n, "qualified_name", "") or "",
                "labels": list(type(n).inherited_labels()),
                "uid": n.canonical_key,
            }
            for n in self._backend._nodes.values()
        ]

    def find_nodes_with_labels(self, labels: list[str]) -> list[dict[str, Any]]:
        label_set = set(labels)
        return [
            {
                "qualified_name": getattr(n, "qualified_name", "") or "",
                "labels": list(type(n).inherited_labels()),
                "uid": n.canonical_key,
            }
            for n in self._backend._nodes.values()
            if label_set.issubset(type(n).inherited_labels())
        ]

    def count_all_nodes(self, tag: str | None = None) -> int:
        """Count all nodes, optionally filtered by *tag* (parity with
        sqlite/neo4j)."""
        if tag is None:
            return len(self._backend._nodes)
        return sum(
            1 for n in self._backend._nodes.values()
            if tag in (getattr(n, "tags", None) or [])
        )

    def list_sources(self) -> list[dict[str, Any]]:
        """Return distinct ``source`` values with node counts, desc."""
        counts: dict[str, int] = {}
        for node in self._backend._nodes.values():
            src = getattr(node, "source", None)
            if src:
                counts[src] = counts.get(src, 0) + 1
        return [
            {"source": src, "count": cnt}
            for src, cnt in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

    # ── Node mutation ─────────────────────────────────────────────

    def update_properties(
        self, uid: str, props: dict, *, add_labels: list[str] | None = None
    ) -> bool:
        node = self._backend._nodes.get(uid)
        if node is None:
            return False
        for key, value in props.items():
            setattr(node, key, value)
        return True

    def delete_by_uid(self, uid: str) -> bool:
        node = self._backend._nodes.get(uid)
        if node is None:
            return False
        self._backend.delete(node)
        return True

    def delete_by_key(self, key: str) -> bool:
        """Delete a node (edges cascade) by canonical key."""
        node = self._backend._nodes.get(key)
        if node is None:
            return False
        self._backend.delete(node)
        return True

    def delete_by_source(self, source: str) -> int:
        """Delete every node carrying *source* (edges cascade)."""
        stale = [n for n in self._backend._nodes.values()
                 if getattr(n, "source", None) == source]
        for node in stale:
            self._backend.delete(node)
        return len(stale)

    def delete_by_uids(self, uids: list[str]) -> int:
        """Delete all nodes with the given uids (edges cascade)."""
        deleted = 0
        for uid in list(dict.fromkeys(uids)):
            if self.delete_by_uid(uid):
                deleted += 1
        return deleted

    # ── Relationships ─────────────────────────────────────────────

    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """Compatibility shim (WP C): uids ARE canonical keys here."""
        return self.merge_relationship_by_key(
            source_uid, rel_type, target_uid,
            edge_properties=edge_properties,
        )

    def merge_relationship_by_key(
        self,
        source_key: str,
        rel_type: str,
        target_key: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """MERGE a relationship between two nodes by canonical key."""
        source = self._backend._nodes.get(source_key)
        target = self._backend._nodes.get(target_key)
        if source is None or target is None:
            return 0
        for e in self._backend._edges_out.get(source_key, []):
            if e.relation_type == rel_type and e.target_key == target_key:
                return 0
        self._backend.connect(source, rel_type, target)
        return 1

    def merge_labeled_relationship(
        self,
        source_uid: str,
        source_label: str,
        rel_type: str,
        target_uid: str,
        target_label: str,
    ) -> None:
        self.merge_relationship_by_key(source_uid, rel_type, target_uid)

    # ── Traversal ─────────────────────────────────────────────────

    def get_ancestors(self, uid: str, max_depth: int = 10) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        frontier = [uid]
        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for cur in frontier:
                for e in self._backend._edges_in.get(cur, []):
                    if e.relation_type != "COMPOSES":
                        continue
                    if e.target_key in seen:
                        continue
                    seen.add(e.target_key)
                    node = self._backend._nodes.get(e.target_key)
                    results.append({
                        "uid": e.target_key,
                        "labels": list(type(node).inherited_labels()) if node else [],
                    })
                    next_frontier.append(e.target_key)
            frontier = next_frontier
        return results

    def get_descendants(self, uid: str, max_depth: int = 10) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        frontier = [uid]
        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for cur in frontier:
                for e in self._backend._edges_out.get(cur, []):
                    if e.relation_type != "COMPOSES":
                        continue
                    if e.target_key in seen:
                        continue
                    seen.add(e.target_key)
                    node = self._backend._nodes.get(e.target_key)
                    results.append({
                        "uid": e.target_key,
                        "labels": list(type(node).inherited_labels()) if node else [],
                    })
                    next_frontier.append(e.target_key)
            frontier = next_frontier
        return results

    # ── Tag queries ───────────────────────────────────────────────

    def find_uids_by_tag(self, tag: str) -> list[str]:
        """Returns canonical keys of nodes carrying *tag* (WP C)."""
        return [
            n.canonical_key for n in self._backend._nodes.values()
            if tag in (getattr(n, "tags", None) or [])
        ]

    def find_uids_by_tag_and_condition(
        self,
        tag: str,
        *,
        condition_clause: str = "",
        params: dict | None = None,
    ) -> list[str]:
        raise NotImplementedError(
            "find_uids_by_tag_and_condition is not supported for the "
            "in-memory backend (condition_clause is Cypher)."
        )

    # ── Related-node queries ──────────────────────────────────────

    def find_related_nodes(
        self,
        target_uid: str,
        rel_pattern: str,
        *,
        params: dict | None = None,
    ) -> list[dict]:
        raise NotImplementedError(
            "find_related_nodes is not supported for the in-memory backend."
        )

    # ── Search ────────────────────────────────────────────────────

    def search_fulltext(
        self,
        query: str,
        *,
        labels: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        raise NotImplementedError(
            "search_fulltext is not supported for the in-memory backend."
        )

    def search_vector(
        self,
        embedding: list[float],
        *,
        index_name: str = "memory_doc_embeddings",
        labels: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        raise NotImplementedError(
            "search_vector is not supported for the in-memory backend."
        )

    # ── LayerGraph builders ───────────────────────────────────────

    def _build_layer_graph(self, nodes: list["CodeGraphNode"]) -> "LayerGraph":
        from codegraph.graph import CompositeEntry, LayerGraph

        graph = LayerGraph(tags=frozenset())
        for node in nodes:
            graph.entries[LayerGraph._node_key(node)] = CompositeEntry(node=node)
        for node in nodes:
            key = node.canonical_key
            for e in self._backend._edges_out.get(key, []):
                target = self._backend._nodes.get(e.target_key)
                if target is not None:
                    source_entry = graph.entries.get(LayerGraph._node_key(node))
                    target_entry = graph.entries.get(LayerGraph._node_key(target))
                    if source_entry is None or target_entry is None:
                        continue
                    if e.relation_type == "COMPOSES":
                        t = type(target).__name__
                        source_entry.children.setdefault(t, {})[
                            LayerGraph._node_key(target)
                        ] = target_entry
                    else:
                        source_entry.references.append(
                            (e.relation_type, LayerGraph._node_key(target),
                             type(target).__name__)
                        )
        return graph

    def get_by_tag(self, tag: "Tag") -> "LayerGraph":
        return self._build_layer_graph(self._backend._find_all_by_tag_impl(tag))

    def get_by_source(self, source: str) -> "LayerGraph":
        return self._build_layer_graph(self._backend._find_all_by_source_impl(source))

    def get_by_namespace(self, qualified_name: str) -> "LayerGraph":
        raise NotImplementedError(
            "get_by_namespace is not supported for the in-memory backend."
        )

    def get_by_compound(self, qualified_name: str) -> "LayerGraph":
        raise NotImplementedError(
            "get_by_compound is not supported for the in-memory backend."
        )

    def get_by_neighbourhood(self, qualified_name: str) -> "LayerGraph":
        raise NotImplementedError(
            "get_by_neighbourhood is not supported for the in-memory backend."
        )

    def get_by_kind(
        self, kind: str, *, tag: str | None = None
    ) -> "LayerGraph":
        nodes = self._backend._find_all_by_kind_impl(kind, tag)
        return self._build_layer_graph(nodes)

    def get_hlr_subtree(self, uid: str, tag: str = "") -> "LayerGraph":
        raise NotImplementedError(
            "get_hlr_subtree is not supported for the in-memory backend."
        )

    # ── Direct node queries ───────────────────────────────────────

    def find_by_tag(
        self, tag: str, node_type: type["CodeGraphNode"] | None = None
    ) -> list["CodeGraphNode"]:
        if node_type is None:
            return self._backend._find_all_by_tag_impl(tag)
        return self._backend._find_by_tag_impl(node_type, tag)

    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        return self._backend._find_all_by_tag_impl(tag)

    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        return self._backend._find_all_by_source_impl(source)

    def find_all_by_kind(
        self, kind: str, *, tag: str | None = None
    ) -> list["CodeGraphNode"]:
        return self._backend._find_all_by_kind_impl(kind, tag)

    # ── Composition traversal (delegate to backend) ───────────────

    def composed_children(
        self,
        node: "CodeGraphNode",
        child_type: type["CodeGraphNode"],
    ) -> list["CodeGraphNode"]:
        return [
            c for c in self._backend.get_composed_children(node)
            if isinstance(c, child_type)
        ]

    def incoming_composers(
        self, node: "CodeGraphNode"
    ) -> list["CodeGraphNode"]:
        key = node.canonical_key
        return [
            self._backend._nodes[e.target_key]
            for e in self._backend._edges_in.get(key, [])
            if e.relation_type == "COMPOSES" and e.target_key in self._backend._nodes
        ]

    def outgoing_by_relation(
        self, node: "CodeGraphNode", rel_type: str
    ) -> list["CodeGraphNode"]:
        key = node.canonical_key
        return [
            self._backend._nodes[e.target_key]
            for e in self._backend._edges_out.get(key, [])
            if e.relation_type == rel_type and e.target_key in self._backend._nodes
        ]

    def save_layer_graph(self, graph: "LayerGraph") -> None:
        self._backend.bulk_save(graph)

    def count_relationships(
        self,
        rel_types: list[str],
        *,
        source_labels: list[str] | None = None,
        target_labels: list[str] | None = None,
        target_tag: str | None = None,
    ) -> int:
        """Count stored relationships whose type is in *rel_types*.

        Signature parity with the abstract ``GraphRepository`` contract: the
        SQLite and Neo4j implementations take a *list* of relationship types
        plus optional source-label / target-label / target-tag filters, and a
        backend-neutral caller has to be able to ask that one question of
        every backend.  A node's labels are its inherited label chain, its tag
        set the ``tags`` property; a filter matches when any listed label/tag
        is present, as the SQL ``IN`` filters do.
        """
        if not rel_types:
            return 0
        wanted = set(rel_types)
        nodes = self._backend._nodes

        def _labels(key: str) -> set[str]:
            node = nodes.get(key)
            if node is None:
                return set()
            return set(node.inherited_labels())

        def _tags(key: str) -> list:
            node = nodes.get(key)
            return list(getattr(node, "tags", None) or []) if node else []

        total = 0
        for src_key, edges in self._backend._edges_out.items():
            for edge in edges:
                if edge.relation_type not in wanted:
                    continue
                if source_labels and not set(source_labels) & _labels(src_key):
                    continue
                if target_labels and not set(target_labels) & _labels(
                    edge.target_key
                ):
                    continue
                if target_tag and target_tag not in _tags(edge.target_key):
                    continue
                total += 1
        return total

    def find_nodes_with_labels_and_count(
        self, labels: list[str], *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        nodes = self.find_nodes_with_labels(labels)
        if limit is not None:
            nodes = nodes[:limit]
        return nodes


class InMemoryMemoryRepository:
    """In-memory implementation of ``MemoryRepository``.

    Node-level operations delegate to the backend; graph-query methods
    (traversal by Cypher patterns) raise ``NotImplementedError``.
    """

    def __init__(self, backend: "InMemoryBackend") -> None:
        self._backend = backend

    def find_for_code_node(self, uid: str) -> list[dict]:
        raise NotImplementedError(
            "find_for_code_node is not supported for the in-memory backend."
        )

    def find_for_code_node_by_qname(
        self, qualified_name: str
    ) -> list[dict]:
        raise NotImplementedError(
            "find_for_code_node_by_qname is not supported for the in-memory backend."
        )

    def find_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        return self._backend._find_all_by_tag_impl(tag)

    def merge_edge(
        self, source_uid: str, rel_type: str, target_uid: str
    ) -> None:
        source = self._backend._nodes.get(source_uid)
        target = self._backend._nodes.get(target_uid)
        if source is not None and target is not None:
            self._backend.connect(source, rel_type, target)

    def find_linked_to_ancestors(
        self, code_uid: str, limit: int = 50
    ) -> list[dict]:
        raise NotImplementedError(
            "find_linked_to_ancestors is not supported for the in-memory backend."
        )

    def find_linked_to_descendants(
        self, code_uid: str, limit: int = 50
    ) -> list[dict]:
        raise NotImplementedError(
            "find_linked_to_descendants is not supported for the in-memory backend."
        )

    def search_content(
        self,
        query: str,
        *,
        label: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        raise NotImplementedError(
            "search_content is not supported for the in-memory backend."
        )

    def link_to_code_node(
        self, memory_uid: str, rel_type: str, code_uid: str
    ) -> None:
        self.merge_edge(memory_uid, rel_type, code_uid)

    def find_linked_code_node(
        self, memory_uid: str, rel_type: str
    ) -> "CodeGraphNode | None":
        uid = memory_uid
        for e in self._backend._edges_out.get(uid, []):
            if e.relation_type == rel_type:
                return self._backend._nodes.get(e.target_key)
        return None

    def search_semantic(
        self,
        embedding: list[float],
        *,
        label: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        raise NotImplementedError(
            "search_semantic is not supported for the in-memory backend."
        )


class InMemoryRequirementsRepository:
    """In-memory implementation of ``RequirementsRepository``.

    HLR/LLR tree traversal, scaffold lifecycle, and verification edge
    management are Cypher-shaped queries — raise ``NotImplementedError``.
    """

    def __init__(self, backend: "InMemoryBackend") -> None:
        self._backend = backend

    def get_hlr_tree(self, hlr_uid: str) -> dict:
        raise NotImplementedError(
            "get_hlr_tree is not supported for the in-memory backend."
        )

    def find_scaffold_uids(self, tag: str = "scaffold") -> list[str]:
        return [
            n._uid_value() for n in self._backend._nodes.values()
            if tag in (getattr(n, "tags", None) or [])
        ]

    def find_scaffold_parents_of_referenced(
        self, tag: str = "scaffold"
    ) -> list[dict]:
        raise NotImplementedError(
            "find_scaffold_parents_of_referenced is not supported for the "
            "in-memory backend."
        )

    def retag_scaffold_to_design(self, uid: str) -> None:
        node = self._backend._nodes.get(uid)
        if node is None:
            return
        tags = list(getattr(node, "tags", None) or [])
        tags = [t for t in tags if t != "scaffold"]
        if "design" not in tags:
            tags.append("design")
        node.tags = tags

    def delete_scaffold(self, uid: str) -> None:
        self._backend.delete_by_uid(uid)

    def merge_verification(
        self,
        test_uid: str,
        target_uid: str,
        *,
        rel_type: str = "VERIFIES",
        attributes: dict | None = None,
    ) -> None:
        self._backend.graph.merge_relationship(test_uid, rel_type, target_uid)

    def replace_callee(self, step_uid: str, new_callee_uid: str) -> None:
        raise NotImplementedError(
            "replace_callee is not supported for the in-memory backend."
        )

    def merge_depends_on(
        self, source_uid: str, target_uid: str
    ) -> None:
        self._backend.graph.merge_relationship(source_uid, "DEPENDS_ON", target_uid)

    def find_unresolved_verifications(self) -> list[dict]:
        raise NotImplementedError(
            "find_unresolved_verifications is not supported for the in-memory backend."
        )

    def find_unresolved_callee_steps(self) -> list[dict]:
        raise NotImplementedError(
            "find_unresolved_callee_steps is not supported for the in-memory backend."
        )
