"""GraphRepository — data access layer for the codebase graph.

Provides scope-based read methods that return LayerGraph objects, plus a
single bulk write method.  Uses the active backend for all queries.
"""

from __future__ import annotations



from codegraph.backends import get_backend
from codegraph.backends.interface import Backend
from codegraph.constants import Tag
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

    Accepts an optional ``Backend`` in the constructor.  When not
    provided, uses the globally-configured backend via ``get_backend()``.

    All read methods return LayerGraph objects.  The single write method
    delegates to the backend's ``bulk_save()``.
    """

    def __init__(self, backend: "Backend | None" = None):
        if backend is None:
            backend = get_backend()
        self._backend = backend

    # ── Private helpers ────────────────────────────────────────────────

    @staticmethod
    def _get_node_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search compound and namespace types by qualified_name.

        Uses the active backend for the lookup.

        Args:
            qualified_name: The fully-qualified name to search for.

        Returns:
            First matching CodeGraphNode instance, or None if not found.
        """
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = get_backend().get(node_cls, qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _get_member_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search member types by qualified_name.

        Uses the active backend for the lookup.

        Args:
            qualified_name: The fully-qualified name to search for.

        Returns:
            First matching CodeGraphNode instance, or None if not found.
        """
        for node_cls in _MEMBER_TYPES:
            node = get_backend().get(node_cls, qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    def get_hlr_subtree(self, uid: str, tag: str = "") -> LayerGraph:
        """Fetch the full requirements subtree for an HLR, optionally filtered by tag.

        Performs multi-hop COMPOSES traversal starting from the HLR:
        HLR → LLRs → TestNodes → AssertionNodes / TestStepNodes.
        Then expands 1-hop neighbours on the leaf nodes to include
        scaffold/design nodes referenced by LEFT_OPERAND, RIGHT_OPERAND,
        and CALLEE edges.

        Args:
            uid: The HLR's ``uid`` (deterministic unique ID).
            tag: Optional tag to filter the subtree by.  When provided, only
                nodes that carry this tag (plus their ancestors to preserve
                tree structure) are included.  Use ``"scaffold"`` to see
                scaffold nodes, ``"design"`` for design nodes, etc.

        Returns:
            A LayerGraph containing the full requirements tree and its
            scaffold neighbours, or an empty LayerGraph if the HLR is
            not found.
        """
        from codegraph_requirements.models import HLR

        hlr = get_backend().get(HLR, uid=uid)
        if hlr is None:
            return LayerGraph(tags=frozenset({"design"}))

        # Phase 1: multi-hop COMPOSES traversal from HLR
        seen_uids: set[str] = set()
        queue: list[CodeGraphNode] = [hlr]
        composes_reachable: list[CodeGraphNode] = []

        while queue:
            node = queue.pop(0)
            uid = node._uid_value()
            if not uid or uid in seen_uids:
                continue
            seen_uids.add(uid)
            composes_reachable.append(node)

            for child in get_backend().get_composed_children(node):
                child_uid = child._uid_value()
                if child_uid and child_uid not in seen_uids:
                    queue.append(child)

        # Phase 2: pass all visited nodes to _build_layer_graph for
        # 1-hop expansion (scaffold neighbours via LEFT_OPERAND etc.)
        graph = self._build_layer_graph(composes_reachable)

        # Phase 3: if tag is specified, filter entries to matching nodes
        # and their ancestors (preserving the tree structure)
        if tag:
            graph = _filter_graph_by_tag(graph, tag)

        return graph

    @staticmethod
    def _build_layer_graph(seeds: list[CodeGraphNode]) -> LayerGraph:
        """Build a LayerGraph from seed nodes plus 1-hop neighbors.

        Uses the active backend for all data access.

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
            for edge_info in get_backend().get_all_edges(node):
                if edge_info.relation_type == "HAS_IMPLEMENTATION":
                    continue
                target_uid = edge_info.target_uid
                target_type = edge_info.target_type
                if target_uid not in uid_to_key:
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = get_backend().get(
                                target_cls, **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = LayerGraph._node_key(neighbor)
                                nodes[neighbor_key] = neighbor
                                uid_to_key[target_uid] = neighbor_key

        # Phase 3: build CompositeEntry instances
        key_to_entry: dict[str, CompositeEntry] = {}
        for key, node in nodes.items():
            key_to_entry[key] = CompositeEntry(node=node)

        # Phase 4: build composition tree and collect references
        child_keys: set[str] = set()
        for key, node in nodes.items():
            entry = key_to_entry[key]

            # COMPOSES: use get_backend().get_composed_children(node)
            for child in get_backend().get_composed_children(node):
                child_key = LayerGraph._node_key(child)
                if child_key not in key_to_entry:
                    continue
                child_entry = key_to_entry[child_key]
                child_type = type(child).__name__
                entry.children.setdefault(child_type, {})[child_key] = child_entry
                child_keys.add(child_key)

            # Non-COMPOSES references: use get_backend().get_all_edges(node)
            for edge_info in get_backend().get_all_edges(node):
                relation_type = edge_info.relation_type
                if relation_type in ("COMPOSES", "HAS_IMPLEMENTATION"):
                    continue
                target_key = uid_to_key.get(edge_info.target_uid)
                if target_key and target_key in key_to_entry:
                    entry.references.append(
                        (relation_type, target_key, edge_info.target_type)
                    )

        # Phase 5: root entries = nodes not composed by another node
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        # Phase 6: derive tags from seeds
        all_tags: set[str] = set()
        for node in seeds:
            if "tags" in type(node).defined_properties():
                node_tags = getattr(node, "tags", None)
                if node_tags:
                    all_tags.update(node_tags)
        tags = frozenset(all_tags) if all_tags else frozenset({"design"})

        return LayerGraph(tags=tags, entries=root_entries)

    # ── Public: scope-based read methods ──────────────────────────────

    def get_by_tag(self, tag: Tag) -> LayerGraph:
        """Fetch all nodes with a given tag plus their 1-hop neighbors.

        Args:
            tag: The tag to query (``"design"``, ``"as-built"``, ``"dependency"``).

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = get_backend().find_all_by_tag(tag)
        return self._build_layer_graph(seeds)

    def get_by_source(self, source: str) -> LayerGraph:
        """Fetch all nodes from a given source project plus neighbors.

        Args:
            source: The source project name (e.g. "codegraph", "llvm").

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = get_backend().find_all_by_source(source)
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
        ns = get_backend().get(NamespaceNode, qualified_name=qualified_name)
        if ns is None:
            return LayerGraph(tags=frozenset({"design"}))
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
            return LayerGraph(tags=frozenset({"design"}))
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
            return LayerGraph(tags=frozenset({"design"}))
        return self._build_layer_graph([node])

    def get_by_kind(self, kind: str, tag: Tag | None = None) -> LayerGraph:
        """Fetch all nodes of a given kind, optionally filtered by tag.

        Args:
            kind: The node kind to filter by (e.g. "class", "method").
            tag: Optional tag to additionally filter by.

        Returns:
            A LayerGraph containing all matching nodes and neighbors.
        """
        seeds = get_backend().find_all_by_kind(kind, tag)
        return self._build_layer_graph(seeds)

    # ── Public: flat query methods (no graph expansion) ──────────────
    #
    # These are thin wrappers around backend queries.  Use them instead
    # of importing ``get_backend`` directly — they keep higher-level
    # modules decoupled from the storage layer.

    def find_by_tag(
        self, node_type: type["CodeGraphNode"], tag: str
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* whose tags contain *tag*.

        Thin wrapper around ``backend.find_by_tag()``.
        """
        from codegraph.backends import get_backend
        return get_backend().find_by_tag(node_type, tag)

    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Return all nodes across all types whose tags contain *tag*."""
        from codegraph.backends import get_backend
        return get_backend().find_all_by_tag(tag)

    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Return all nodes across all types matching *source*."""
        from codegraph.backends import get_backend
        return get_backend().find_all_by_source(source)

    def find_all_by_kind(
        self, kind: str, tag: str | None = None
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *kind* (and optionally *tag*)."""
        from codegraph.backends import get_backend
        return get_backend().find_all_by_kind(kind, tag)

    # ── Public: relationship traversal helpers ───────────────────────

    @staticmethod
    def composed_children(
        node: "CodeGraphNode",
        child_type: type["CodeGraphNode"],
    ) -> list["CodeGraphNode"]:
        """Return children of *node* reachable via outgoing COMPOSES
        that are instances of *child_type*.

        Replaces neomodel's ``node.relations.all()`` with a
        backend-agnostic query.  Example::

            methods = GraphRepository.composed_children(cls, MethodNode)
        """
        return [
            c for c in get_backend().get_composed_children(node)
            if isinstance(c, child_type)
        ]

    @staticmethod
    def incoming_composers(
        node: "CodeGraphNode",
        composer_type: type["CodeGraphNode"] | None = None,
    ) -> list["CodeGraphNode"]:
        """Return nodes that COMPOSE *node* (incoming COMPOSES edges).

        Replaces neomodel's ``.parent_namespace.all()`` and similar
        ``RelationshipFrom`` traversals.  Example::

            parents = GraphRepository.incoming_composers(method, ClassNode)
        """
        backend = get_backend()
        edges = backend.get_all_edges(node)
        composers: list["CodeGraphNode"] = []
        for e in edges:
            if e.relation_type != "COMPOSES" or e.is_outgoing:
                continue
            target_cls = CodeGraphNode._registry.get(e.target_type)
            if target_cls is None:
                continue
            if composer_type is not None and target_cls is not composer_type:
                continue
            composer = backend.get(target_cls, uid=e.target_uid)
            if composer is not None:
                composers.append(composer)
        return composers

    @staticmethod
    def outgoing_by_relation(
        node: "CodeGraphNode",
        relation_type: str,
        target_type: type["CodeGraphNode"] | None = None,
    ) -> list["CodeGraphNode"]:
        """Return nodes reachable via outgoing *relation_type* edges.

        Replaces neomodel's ``.depends_on.all()``, ``.invokes.all()``
        and other outgoing relationship traversals.  Example::

            deps = GraphRepository.outgoing_by_relation(cls, "DEPENDS_ON")
        """
        backend = get_backend()
        edges = backend.get_all_edges_outgoing(node)
        targets: list["CodeGraphNode"] = []
        for e in edges:
            if e.relation_type != relation_type:
                continue
            target_cls = CodeGraphNode._registry.get(e.target_type)
            if target_cls is None:
                continue
            if target_type is not None and target_cls is not target_type:
                continue
            target = backend.get(target_cls, uid=e.target_uid)
            if target is not None:
                targets.append(target)
        return targets

    # ── Public: write method ──────────────────────────────────────────

    @staticmethod
    def save_layer_graph(graph: LayerGraph) -> None:
        """Persist a LayerGraph.  Delegates to the active backend's
        ``bulk_save()``.

        Args:
            graph: The LayerGraph to persist.
        """
        get_backend().bulk_save(graph)


# ══════════════════════════════════════════════════════════════════════════
# Helper: filter LayerGraph entries by tag (preserving ancestry)
# ══════════════════════════════════════════════════════════════════════════


def _filter_graph_by_tag(graph: LayerGraph, tag: str) -> LayerGraph:
    """Filter a LayerGraph to only entries whose node carries *tag*,
    plus their ancestors (to preserve tree structure).

    Returns a new LayerGraph with the same tags and the pruned entries.
    """
    # ── Collect tagged keys (walk entire tree, not just roots) ──
    tagged_keys: set[str] = set()

    def _collect_tagged(entry) -> None:
        key = LayerGraph._node_key(entry.node)
        node_tags: list[str] = getattr(entry.node, "tags", None) or []
        if tag in node_tags:
            tagged_keys.add(key)
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                _collect_tagged(child_entry)

    for entry in graph.entries.values():
        _collect_tagged(entry)

    if not tagged_keys:
        # No matches — return empty graph
        return LayerGraph(tags=graph.tags)

    # Walk from each root entry; keep entries that are ancestors of a tagged
    # node or are themselves tagged
    keep_keys: set[str] = set()

    def _walk(entry, path: list[str]) -> bool:
        """Return True if this entry or any descendant has the tag."""
        key = LayerGraph._node_key(entry.node)
        has_tag = key in tagged_keys
        descendant_has = False
        for type_children in entry.children.values():
            for child_key, child_entry in type_children.items():
                if _walk(child_entry, path + [key]):
                    descendant_has = True
        if has_tag or descendant_has:
            keep_keys.add(key)
            keep_keys.update(path)
            return True
        return False

    for entry in graph.entries.values():
        _walk(entry, [])

    # Build filtered entries dict: prune children to only keep_keys
    filtered: dict = {}

    def _prune(entry):
        key = LayerGraph._node_key(entry.node)
        if key not in keep_keys:
            return None
        from codegraph.graph import CompositeEntry
        new_entry = CompositeEntry(node=entry.node)
        new_entry.references = list(entry.references)
        for child_type, type_children in entry.children.items():
            for child_key, child_entry in type_children.items():
                if child_key in keep_keys:
                    pruned = _prune(child_entry)
                    if pruned is not None:
                        new_entry.children.setdefault(child_type, {})[child_key] = pruned
        return new_entry

    for key, entry in graph.entries.items():
        if key in keep_keys:
            pruned = _prune(entry)
            if pruned is not None:
                filtered[key] = pruned

    return LayerGraph(tags=graph.tags, entries=filtered)


def _filter_graph_by_types(graph: LayerGraph, keep_types: frozenset[str]) -> LayerGraph:
    """Filter a LayerGraph to only entries whose node type name is in *keep_types*,
    plus their ancestors (to preserve tree structure).

    Returns a new LayerGraph with the same tags and the pruned entries.

    Example:
        ``keep_types=frozenset({"HLR", "LLR"})`` returns a requirements-only
        graph, stripping design classes, assertions, steps, and test nodes.
    """
    # Build a set of entry keys whose node type matches (walk entire tree)
    matching_keys: set[str] = set()

    def _collect_matching(entry) -> None:
        key = LayerGraph._node_key(entry.node)
        node_type_name = type(entry.node).__name__
        if node_type_name in keep_types:
            matching_keys.add(key)
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                _collect_matching(child_entry)

    for entry in graph.entries.values():
        _collect_matching(entry)

    if not matching_keys:
        return LayerGraph(tags=graph.tags)

    # Walk from each root entry; keep matching entries + ancestors
    keep_keys: set[str] = set()

    def _walk(entry, path: list[str]) -> bool:
        key = LayerGraph._node_key(entry.node)
        has_match = key in matching_keys
        descendant_has = False
        for type_children in entry.children.values():
            for child_key, child_entry in type_children.items():
                if _walk(child_entry, path + [key]):
                    descendant_has = True
        if has_match or descendant_has:
            keep_keys.add(key)
            keep_keys.update(path)
            return True
        return False

    for entry in graph.entries.values():
        _walk(entry, [])

    # Build filtered entries
    from codegraph.graph import CompositeEntry
    filtered: dict = {}

    def _prune(entry):
        key = LayerGraph._node_key(entry.node)
        if key not in keep_keys:
            return None
        new_entry = CompositeEntry(node=entry.node)
        new_entry.references = list(entry.references)
        for child_type, type_children in entry.children.items():
            for child_key, child_entry in type_children.items():
                if child_key in keep_keys:
                    pruned = _prune(child_entry)
                    if pruned is not None:
                        new_entry.children.setdefault(child_type, {})[child_key] = pruned
        return new_entry

    for key, entry in graph.entries.items():
        if key in keep_keys:
            pruned = _prune(entry)
            if pruned is not None:
                filtered[key] = pruned

    return LayerGraph(tags=graph.tags, entries=filtered)