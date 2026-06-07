"""LayerGraph — layer-aware graph container for codebase views.

A Python-only container that holds a nested composition structure for
all nodes in a design view. Root entries are keyed by a stable local
identifier.  COMPOSES relationships create nesting; other relationship
types are stored as references.  Supports deserialization from JSON,
persistence to Neo4j, and querying from Neo4j by layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from codegraph.constants import Layer, LAYERS
from codegraph.models.tags import CodeGraphNode


@dataclass
class CompositeEntry:
    """A node and its composition hierarchy.

    Bundles a ``CodeGraphNode`` with its composed children (COMPOSES
    edges) and non-composition references (all other edge types).

    Attributes:
        node: The CodeGraphNode instance.
        children: Composed children keyed by target type, then by
            target key.  Only COMPOSES edges create entries here.
        references: Non-composition edges from this node.  Each tuple
            is ``(relation_type, target_key, target_type)``.
    """

    node: CodeGraphNode
    children: dict[str, dict[str, "CompositeEntry"]] = field(default_factory=dict)
    references: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class LayerGraph:
    """A Python-only container for all nodes in a design view, filtered by layer.

    Nodes are organised into a nested composition structure via
    ``CompositeEntry`` instances.  Root entries are nodes not composed
    by any other node (files, namespaces, orphan compounds).  Children
    live inside their parent entry's ``children`` dict, keyed by
    target type then target key.

    Non-COMPOSES relationships are stored as references on each entry.

    Attributes:
        layer: The design view layer ("design", "as-built", or "dependency").
        entries: Dict mapping stable local keys to CompositeEntry instances
            for root-level nodes only.
    """

    layer: Layer  # "design" | "as-built" | "dependency"

    def __post_init__(self) -> None:
        """Validate that *layer* is one of the allowed values."""
        if self.layer not in LAYERS:
            raise ValueError(
                f"Invalid layer {self.layer!r}; must be one of {LAYERS}"
            )

    entries: dict[str, CompositeEntry] = field(default_factory=dict)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _node_key(obj) -> str:
        """Derive a stable local key from a node instance or raw dict.

        Uses the node's UniqueIdProperty value (``qualified_name`` for
        compounds/members/namespaces, ``refid`` for FileNode) as the key,
        falling back to ``name`` for node types that lack a UniqueIdProperty
        (e.g. ParameterNode) or for dicts that omit the uid field.

        For dicts (raw JSON data), the uid property name is resolved via
        the type registry so that the correct field is consulted regardless
        of node type.

        For CodeGraphNode instances, delegates to ``_uid_value()`` which
        returns the value of the node's UniqueIdProperty.

        Args:
            obj: A CodeGraphNode instance or a raw dict with ``type``
                and node property keys.

        Returns:
            The stable local key string for the node.
        """
        if isinstance(obj, dict):
            type_name = obj.get("type")
            if type_name and type_name in CodeGraphNode._registry:
                uid_prop = CodeGraphNode._registry[type_name]._uid_prop()
                if uid_prop and uid_prop in obj:
                    return obj[uid_prop]
            return obj.get("name", "")
        # CodeGraphNode instance — use the UniqueIdProperty value
        uid = obj._uid_value()
        if uid is not None:
            return uid
        # Fallback for types without UniqueIdProperty (e.g. ParameterNode)
        return obj.name

    @staticmethod
    def _walk_entries(entry: CompositeEntry) -> Iterator[CompositeEntry]:
        """Yield all CompositeEntry instances depth-first from *entry*.

        Args:
            entry: The root CompositeEntry to walk.

        Yields:
            Each CompositeEntry in the subtree, depth-first.
        """
        yield entry
        for type_children in entry.children.values():
            for child in type_children.values():
                yield from LayerGraph._walk_entries(child)

    def _all_entries(self) -> Iterator[CompositeEntry]:
        """Yield every CompositeEntry across all root entries, depth-first.

        Yields:
            Each CompositeEntry in the graph.
        """
        for entry in self.entries.values():
            yield from self._walk_entries(entry)

    def _flat_index(self) -> dict[str, CompositeEntry]:
        """Build a flat key → CompositeEntry lookup across the entire tree.

        Returns:
            A dict mapping every node key to its CompositeEntry.
        """
        return {LayerGraph._node_key(e.node): e for e in self._all_entries()}

    # ── from_json ──────────────────────────────────────────────────────

    @classmethod
    def _parse_nested_entry(
        cls,
        data: dict,
        key_to_entry: dict[str, CompositeEntry],
        uid_to_key: dict[str, str],
        child_keys: set[str],
    ) -> CompositeEntry:
        """Phase 1: Create entries, register uids, and build the tree.

        Does not resolve references — that requires a complete uid
        mapping, which is only available after all entries have been
        created.  Use ``_resolve_nested_references`` for Phase 2.

        Args:
            data: A dict representing one node with optional ``composes``
                children.
            key_to_entry: Global index mapping node keys to entries.
            uid_to_key: Mapping from unique ids to local keys.
            child_keys: Set of keys that appear as composed children
                (used to determine root entries).

        Returns:
            The CompositeEntry for this node (with children attached,
            references pending).
        """
        node = CodeGraphNode.from_json(data)
        entry = CompositeEntry(node=node)

        # Build uid → key mapping
        key = cls._node_key(data)
        uid = node._uid_value()
        if uid:
            uid_to_key[uid] = key

        # Register in the global index
        key_to_entry[key] = entry

        # Process composes children recursively
        for child_data in data.get("composes", []):
            child_entry = cls._parse_nested_entry(
                child_data, key_to_entry, uid_to_key, child_keys
            )
            child_key = cls._node_key(child_data)
            child_type = child_data["type"]
            if child_type not in entry.children:
                entry.children[child_type] = {}
            entry.children[child_type][child_key] = child_entry
            child_keys.add(child_key)

        return entry

    @classmethod
    def _resolve_nested_references(
        cls,
        data: dict,
        key_to_entry: dict[str, CompositeEntry],
        uid_to_key: dict[str, str],
    ) -> None:
        """Phase 2: Resolve non-COMPOSES references for all entries.

        Walks the nested data recursively and populates the
        ``references`` list on each CompositeEntry using the complete
        uid-to-key mapping.

        Args:
            data: A dict representing one node with optional ``composes``
                children and ``edges``.
            key_to_entry: Global index mapping node keys to entries.
            uid_to_key: Complete mapping from unique ids to local keys.
        """
        source_key = cls._node_key(data)
        source_entry = key_to_entry[source_key]

        for edge in data.get("edges", []):
            target_key = edge.get("target_local_id")
            if target_key is None and "target_uid" in edge:
                target_key = uid_to_key.get(edge["target_uid"])
            if target_key is None:
                continue
            source_entry.references.append(
                (edge["relation_type"], target_key, edge["target_type"])
            )

        for child_data in data.get("composes", []):
            cls._resolve_nested_references(child_data, key_to_entry, uid_to_key)

    @classmethod
    def _from_json_nested(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from the nested JSON format (entries with composes key).

        Two-phase approach:
        1. Create all CompositeEntry instances and build uid mapping.
        2. Resolve references using the complete mapping.

        Args:
            data: A list of dicts in nested format, where each entry may
                have a ``composes`` key containing child nodes.

        Returns:
            A LayerGraph with the nested composition structure.
        """
        key_to_entry: dict[str, CompositeEntry] = {}
        uid_to_key: dict[str, str] = {}
        child_keys: set[str] = set()
        layer: Layer = "design"

        # Phase 1: create entries and build tree structure
        for entry_data in data:
            cls._parse_nested_entry(
                entry_data, key_to_entry, uid_to_key, child_keys
            )
            if layer == "design" and "layer" in entry_data:
                layer = entry_data["layer"]  # type: ignore[assignment]

        # Phase 2: resolve references with complete uid mapping
        for entry_data in data:
            cls._resolve_nested_references(entry_data, key_to_entry, uid_to_key)

        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }
        return cls(layer=layer, entries=root_entries)

    @classmethod
    def _from_json_flat(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from the flat JSON format (edges with target_local_id).

        Args:
            data: A list of dicts in flat format, where COMPOSES edges
                create nesting and other edges become references.

        Returns:
            A LayerGraph with the nested composition structure.
        """
        key_to_entry: dict[str, CompositeEntry] = {}
        uid_to_key: dict[str, str] = {}
        layer: Layer = "design"

        # Phase 1: create all CompositeEntry instances (nodes only, no edges yet)
        for node_data in data:
            node = CodeGraphNode.from_json(node_data)
            key = cls._node_key(node_data)
            key_to_entry[key] = CompositeEntry(node=node)

            # Build uid → key mapping for roundtrip format
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

            # Infer layer from node data
            if layer == "design" and "layer" in node_data:
                layer = node_data["layer"]  # type: ignore[assignment]

        # Phase 2: walk edges and build nesting / references
        # Track which nodes are children (composed by another node)
        child_keys: set[str] = set()

        for node_data in data:
            source_key = cls._node_key(node_data)
            source_entry = key_to_entry[source_key]

            for edge in node_data.get("edges", []):
                # Resolve target key
                target_key = edge.get("target_local_id")
                if target_key is None and "target_uid" in edge:
                    target_key = uid_to_key.get(edge["target_uid"])

                if target_key is None:
                    continue

                relation_type = edge["relation_type"]
                target_type = edge["target_type"]

                if relation_type == "COMPOSES":
                    # Nest target as a child under the source entry
                    target_entry = key_to_entry.get(target_key)
                    if target_entry is not None:
                        if target_type not in source_entry.children:
                            source_entry.children[target_type] = {}
                        source_entry.children[target_type][target_key] = target_entry
                        child_keys.add(target_key)
                else:
                    # Store as a reference
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )

        # Phase 3: root entries = nodes that were never a COMPOSES target
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        return cls(layer=layer, entries=root_entries)

    @classmethod
    def from_json(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from a JSON array (as produced by ``to_json()``).

        Pure deserialization — no database interaction.  Infers layer from
        the first node that has a ``layer`` field (fallback: ``"design"``).

        Accepts two formats:
        - **Nested format**: entries with a ``composes`` key containing
          child nodes.  COMPOSES edges are represented by nesting, not
          in the ``edges`` array.
        - **Flat format**: all nodes as separate entries with ``edges``
          arrays containing COMPOSES and other relationship types.

        Args:
            data: A list of dicts, each a serialized node with ``type``,
                properties, and optionally ``edges`` and ``composes``.

        Returns:
            A LayerGraph containing the deserialized nodes in a nested
            composition structure.
        """
        # Detect format: nested if any entry has a "composes" key
        has_nested = any("composes" in entry for entry in data)

        if has_nested:
            return cls._from_json_nested(data)

        return cls._from_json_flat(data)

    # ── to_neo4j ───────────────────────────────────────────────────────

    def to_neo4j(self) -> None:
        """Persist all nodes and relationships to Neo4j.

        Walks the entry tree depth-first.  Saves every node, then
        connects COMPOSES children via the parent's relationship manager
        and connects reference edges via ``find_relationship_manager()``.
        """
        # Build a flat index for resolving reference targets
        flat = self._flat_index()

        # Phase 1: save all nodes
        for entry in self._all_entries():
            entry.node.save()

        # Phase 2: connect relationships
        for entry in self._all_entries():
            source_node = entry.node
            source_key = self._node_key(source_node)

            # Connect COMPOSES children
            for target_type, type_children in entry.children.items():
                for child_key, child_entry in type_children.items():
                    manager = CodeGraphNode.find_relationship_manager(
                        source_node, "COMPOSES", child_entry.node
                    )
                    manager.connect(child_entry.node)

            # Connect references
            for relation_type, target_key, target_type in entry.references:
                target_entry = flat.get(target_key)
                if target_entry is not None:
                    manager = CodeGraphNode.find_relationship_manager(
                        source_node, relation_type, target_entry.node
                    )
                    manager.connect(target_entry.node)

    # ── to_json ────────────────────────────────────────────────────────

    def _serialize_entry(self, entry: CompositeEntry) -> dict:
        """Recursively serialize a CompositeEntry and its composed children.

        Produces a nested dict where composed children appear under a
        ``composes`` key and COMPOSES edges are removed from the
        ``edges`` array.  Includes the node's unique identifier
        property in the output if it is not already present, so that
        roundtrip deserialization can resolve edge targets correctly.

        Args:
            entry: The CompositeEntry to serialize.

        Returns:
            A dict representing the entry with nested children.
        """
        serialized = entry.node.serialize()

        # Ensure uid property is included for roundtrip target resolution.
        # FileNode uses refid (not in _llm_fields), so serialize() omits it.
        # Without it, from_json cannot resolve target_uid in edges.
        uid_prop = type(entry.node)._uid_prop()
        if uid_prop and uid_prop not in serialized:
            uid_value = entry.node._uid_value()
            if uid_value is not None:
                serialized[uid_prop] = uid_value

        # Remove COMPOSES edges — they are represented by nesting
        edges = [
            e for e in serialized.get("edges", [])
            if e["relation_type"] != "COMPOSES"
        ]
        serialized["edges"] = edges

        # Inline composed children under "composes"
        if entry.children:
            composes: list[dict] = []
            for type_children in entry.children.values():
                for child_entry in type_children.values():
                    composes.append(self._serialize_entry(child_entry))
            serialized["composes"] = composes

        return serialized

    def to_json(self) -> list[dict]:
        """Serialize the graph as a nested JSON-compatible list of dicts.

        Root entries are serialized recursively.  Composed children
        appear under a ``composes`` key on their parent and do not
        appear as top-level entries.  COMPOSES edges are excluded
        from the ``edges`` array since the nesting represents them
        explicitly.

        For nodes that have not been persisted to Neo4j, the
        ``edges`` key will be an empty list.

        Returns:
            A list of serialized node dicts with nested composition,
            suitable for JSON output.
        """
        return [self._serialize_entry(entry) for entry in self.entries.values()]

    # ── from_neo4j ─────────────────────────────────────────────────────

    @classmethod
    def from_neo4j(cls, layer: Layer) -> "LayerGraph":
        """Query Neo4j for all nodes where ``.layer == layer``, plus their
        first-level neighbors.  Collect into a nested LayerGraph.

        This includes both endpoints of any edge touching a layer-matched
        node, even if the neighbor's layer is different.

        COMPOSES edges from compound nodes create nesting; all other
        edge types are stored as references.

        Args:
            layer: The layer to query for (``"design"``, ``"as-built"``,
                ``"dependency"``).

        Returns:
            A LayerGraph containing all matching nodes and their first-level
            neighbours in a nested composition structure.
        """
        # Fetch all layer-matched nodes
        matched_nodes = CodeGraphNode.fetch_all_by_layer(layer)

        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}
        seen_uids: set[str] = set()

        # Add all layer-matched nodes
        for node in matched_nodes:
            key = cls._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key
                seen_uids.add(uid)

        # Expand to first-level neighbors
        for node in matched_nodes:
            for edge in node.walk_edges():
                # Skip lazy-loaded relationships — fetched on demand
                if edge["relation_type"] == "HAS_IMPLEMENTATION":
                    continue
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
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
                                uid_to_key[target_uid] = neighbor_key

        # Build CompositeEntry instances
        key_to_entry: dict[str, CompositeEntry] = {}
        for key, node in nodes.items():
            key_to_entry[key] = CompositeEntry(node=node)

        # Walk edges and build nesting / references
        child_keys: set[str] = set()
        for node in list(nodes.values()):
            source_key = cls._node_key(node)
            source_entry = key_to_entry[source_key]

            for edge in node.walk_edges():
                relation_type = edge["relation_type"]
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                is_outgoing = edge["is_outgoing"]
                # Skip lazy-loaded relationships
                if relation_type == "HAS_IMPLEMENTATION":
                    continue
                target_key = uid_to_key.get(target_uid)

                if target_key is None:
                    continue

                if relation_type == "COMPOSES":
                    target_entry = key_to_entry.get(target_key)
                    if target_entry is not None:
                        if is_outgoing:
                            # Parent -> child: nest target under source
                            source_entry.children.setdefault(target_type, {})[target_key] = target_entry
                            child_keys.add(target_key)
                        else:
                            # Child -> parent: nest source under target
                            source_type = type(node).__name__
                            target_entry.children.setdefault(source_type, {})[source_key] = source_entry
                            child_keys.add(source_key)
                else:
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )

        # Root entries = nodes not composed by another node
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        return cls(layer=layer, entries=root_entries)