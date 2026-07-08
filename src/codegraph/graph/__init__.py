"""LayerGraph — tag-aware graph container for codebase views.

A Python-only container that holds a nested composition structure for
all nodes in a design view. Root entries are keyed by a stable local
identifier.  COMPOSES relationships create nesting; other relationship
types are stored as references.  Supports deserialization from dicts,
persistence to Neo4j, and querying from Neo4j by tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from codegraph.constants import Tag, TAGS
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

    def serialize(self, fields: str = "llm") -> dict:
        """Recursively serialize this CompositeEntry and its composed children.

        Walks the pre-built ``children`` tree to produce nested output.
        Composed children appear under a ``composes`` key and COMPOSES
        edges are removed from the ``edges`` array.  The node's unique
        identifier property is included in the output when not already
        present, so that roundtrip deserialization can resolve edge
        targets correctly.

        Uses ``CodeGraphNode.serialize()`` for each node's properties
        and edges, then adds the ``composes`` nesting and uid supplement
        on top.

        Note: For direct nested serialization of a single persisted
        node, use ``node.serialize(nested=True)`` instead — it walks
        COMPOSES relationship managers directly.  This method exists
        because the ``children`` tree may contain only a scoped subset
        of the full composition hierarchy (e.g. only nodes in a
        particular tags), which ``walk_composes()`` would not respect.

        Args:
            fields: Which property fields to include when serializing
                each node.  ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every defined property.  Passed through to
                ``CodeGraphNode.serialize()``.

        Returns:
            A dict representing the entry with nested children.
        """
        # Start from the node's own flat serialization.
        # Remove COMPOSES edges — they are represented by nesting.
        serialized = self.node.serialize(fields=fields)
        edges = [
            e for e in serialized.get("edges", [])
            if e["relation_type"] != "COMPOSES"
        ]
        serialized["edges"] = edges

        # Ensure uid property is included for roundtrip target resolution.
        # With fields="llm" (default), FileNode's refid is omitted since
        # it's not in _llm_fields; with fields="all" it's already present.
        uid_prop = type(self.node)._uid_prop()
        if uid_prop and uid_prop not in serialized:
            uid_value = self.node._uid_value()
            if uid_value is not None:
                serialized[uid_prop] = uid_value

        # Inline composed children under "composes"
        if self.children:
            composes: list[dict] = []
            for type_children in self.children.values():
                for child_entry in type_children.values():
                    composes.append(child_entry.serialize(fields=fields))
            serialized["composes"] = composes

        return serialized


@dataclass
class LayerGraph:
    """A Python-only container for all nodes in a design view, filtered by tags.

    Nodes are organised into a nested composition structure via
    ``CompositeEntry`` instances.  Root entries are nodes not composed
    by any other node (files, namespaces, orphan compounds).  Children
    live inside their parent entry's ``children`` dict, keyed by
    target type then target key.

    Non-COMPOSES relationships are stored as references on each entry.

    Attributes:
        tags: The provenance tags this graph was constructed from
            (e.g. frozenset({"design"}), frozenset({"design", "as-built"})).
        entries: Dict mapping stable local keys to CompositeEntry instances
            for root-level nodes only.
    """

    tags: frozenset[str]  # e.g. frozenset({"design"}) or frozenset({"design", "as-built"})

    def __post_init__(self) -> None:
        """Validate that all tags are from the allowed vocabulary."""
        invalid = self.tags - set(TAGS)
        if invalid:
            raise ValueError(
                f"Invalid tags {invalid!r}; must be from {TAGS}"
            )

    entries: dict[str, CompositeEntry] = field(default_factory=dict)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _node_key(obj) -> str:
        """Derive a stable local key from a node instance or raw dict.

        For dicts (raw JSON data), resolves the ``uid`` field via the
        type registry.  Falls back to ``name`` only when the dict has
        no ``uid`` (e.g. ParameterNode before save).

        For CodeGraphNode instances, delegates to ``_uid_value()`` which
        returns the value of the node's ``uid`` UniqueIdProperty.

        Args:
            obj: A CodeGraphNode instance or a raw dict with ``type``
                and node property keys.

        Returns:
            The stable local key string for the node.
        """
        if isinstance(obj, dict):
            type_name = obj.get("type")
            if type_name and type_name in CodeGraphNode._registry:
                model_cls = CodeGraphNode._registry[type_name]
                uid_prop = model_cls._uid_prop()
                if uid_prop and uid_prop in obj:
                    return obj[uid_prop]
                # uid_prop exists but not in dict (e.g. LLM outputs
                # that lack a pre-computed "uid" hash).  Deserialize
                # the dict to compute the deterministic uid only when
                # the dict has the primary identity field — otherwise
                # deserialization produces a random auto-generated uid,
                # breaking the Phase 1 / Phase 2 key stability.
                if uid_prop:
                    identity_fields = getattr(model_cls, "_identity_fields", ())
                    if identity_fields and obj.get(identity_fields[0]):
                        try:
                            node = CodeGraphNode.deserialize(obj)
                            uid = node._uid_value()
                            if uid:
                                return uid
                        except Exception:
                            pass
            return obj.get("name", "")
        # CodeGraphNode instance — use the UniqueIdProperty value
        uid = obj._uid_value()
        if uid is not None:
            return uid
        # Fallback for types without UniqueIdProperty (e.g. ParameterNode)
        return obj.name

    def resolve_target_name(self, target_key: str) -> str:
        """Resolve a target key (uid hash) to a human-readable display name.

        Looks up *target_key* in the flat entry index and returns the
        node's ``qualified_name``, ``refid``, or ``name`` — whichever is
        most descriptive.  Falls back to *target_key* itself if the entry
        is not in the graph (e.g. a filtered-out neighbour).

        Args:
            target_key: The target node's key (typically a uid hash).

        Returns:
            A human-readable display name for the target node.
        """
        flat = self._flat_index()
        entry = flat.get(target_key)
        if entry is not None:
            node = entry.node
            return (
                getattr(node, "qualified_name", None)
                or getattr(node, "refid", None)
                or node.name
            )
        return target_key

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

    # ── Deserialization ──────────────────────────────────────────────

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
        node = CodeGraphNode.deserialize(data)
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
    def _deserialize_nested(cls, data: list[dict]) -> "LayerGraph":
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
        tags: frozenset[str] = frozenset()

        # Phase 1: create entries and build tree structure
        for entry_data in data:
            cls._parse_nested_entry(
                entry_data, key_to_entry, uid_to_key, child_keys
            )
            # Infer tags from node data (backward compat: "layer" field)
            if not tags:
                node_tags = entry_data.get("tags", [])
                if not node_tags and "layer" in entry_data:
                    node_tags = [entry_data["layer"]]
                if node_tags:
                    tags = frozenset(node_tags)

        # Phase 2: resolve references with complete uid mapping
        for entry_data in data:
            cls._resolve_nested_references(entry_data, key_to_entry, uid_to_key)

        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }
        return cls(tags=tags or frozenset({"design"}), entries=root_entries)

    @classmethod
    def _deserialize_flat(
        cls,
        data: list[dict],
        *,
        create_missing: bool = False,
    ) -> "LayerGraph":
        """Deserialize from the flat JSON format (edges with target_local_id).

        Args:
            data: A list of dicts in flat format, where COMPOSES edges
                create nesting and other edges become references.
            create_missing: When True, auto-create scaffold nodes (with
                ``tags=["scaffold"]``) for edge targets that don't
                resolve to any node in *data*.  This allows partial graphs
                that reference external nodes to be deserialized without
                manually pre-creating placeholder nodes.

        Returns:
            A LayerGraph with the nested composition structure.
        """
        key_to_entry: dict[str, CompositeEntry] = {}
        uid_to_key: dict[str, str] = {}
        # Secondary lookup: maps identity-field values (qualified_name,
        # refid, path) to keys, so LLM-produced edges whose target_uid
        # is a human-readable identifier (not a uid hash) can resolve.
        identity_to_key: dict[str, str] = {}
        tags: frozenset[str] = frozenset()

        # Phase 1: create all CompositeEntry instances (nodes only, no edges yet)
        for node_data in data:
            node = CodeGraphNode.deserialize(node_data)
            key = cls._node_key(node_data)
            key_to_entry[key] = CompositeEntry(node=node)

            # Build uid → key mapping for roundtrip format
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

            # Build identity_to_key from common identity fields
            for field in ("qualified_name", "refid", "path"):
                val = node_data.get(field) or getattr(node, field, None)
                if val:
                    identity_to_key[val] = key

            # Infer tags from node data (backward compat: "layer" field)
            if not tags:
                node_tags = node_data.get("tags", [])
                if not node_tags and "layer" in node_data:
                    node_tags = [node_data["layer"]]
                if node_tags:
                    tags = frozenset(node_tags)

        # Phase 2: walk edges and build nesting / references
        # Track which nodes are children (composed by another node)
        child_keys: set[str] = set()

        for node_data in data:
            source_key = cls._node_key(node_data)
            source_entry = key_to_entry[source_key]

            for edge in node_data.get("edges", []):
                # Resolve target key: try uid hash, then identity field
                target_key = edge.get("target_local_id")
                if target_key is None and "target_uid" in edge:
                    target_key = uid_to_key.get(edge["target_uid"])
                if target_key is None and "target_uid" in edge:
                    target_key = identity_to_key.get(edge["target_uid"])

                # Auto-create scaffold node for unresolved target
                if target_key is None and create_missing and "target_uid" in edge:
                    target_key = cls._create_missing_scaffold(
                        edge, key_to_entry, uid_to_key, identity_to_key
                    )

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

        return cls(tags=tags or frozenset({"design"}), entries=root_entries)

    @staticmethod
    def _classify_literal(value: str) -> str:
        """Classify a literal value string as int, float, boolean, or string."""
        value = value.strip()
        if value.lower() in ("true", "false"):
            return "boolean"
        try:
            int(value)
            return "int"
        except ValueError:
            pass
        try:
            float(value)
            return "float"
        except ValueError:
            pass
        return "string"

    @staticmethod
    def _create_missing_scaffold(
        edge: dict,
        key_to_entry: dict[str, CompositeEntry],
        uid_to_key: dict[str, str],
        identity_to_key: dict[str, str],
    ) -> str | None:
        """Create a scaffold node for an unresolved edge target.

        Builds a minimal node dict from the edge's ``target_type`` and
        ``target_uid``, deserializes it (which computes the deterministic
        ``uid``), and registers it in all lookup dicts.

        The scaffold gets ``tags=["scaffold"]`` so it can be identified
        and later reconciled with real design nodes.

        Args:
            edge: The unresolved edge dict with ``target_uid`` and
                ``target_type``.
            key_to_entry: Global index to add the scaffold to.
            uid_to_key: UID hash → key mapping to update.
            identity_to_key: Identity field → key mapping to update.

        Returns:
            The scaffold's key, or None if creation failed.
        """
        target_type = edge.get("target_type", "")
        target_uid = edge.get("target_uid", "")
        if not target_type or not target_uid:
            return None

        target_cls = CodeGraphNode._registry.get(target_type)
        if not target_cls:
            return None

        # Build minimal scaffold dict
        scaffold_data: dict = {"type": target_type, "tags": ["scaffold"]}

        # Set the first identity field to target_uid (e.g. qualified_name)
        identity_fields = getattr(target_cls, "_identity_fields", ())
        if identity_fields:
            scaffold_data[identity_fields[0]] = target_uid

        # Set name from last :: or . segment
        if "::" in target_uid:
            scaffold_data["name"] = target_uid.rsplit("::", 1)[-1]
        elif "." in target_uid and not target_uid.startswith("literal::"):
            scaffold_data["name"] = target_uid.rsplit(".", 1)[-1]
        else:
            scaffold_data["name"] = target_uid

        # Set kind defaults for compound/member types
        kind_defaults = {
            "ClassNode": "class",
            "CompoundNode": "class",
            "InterfaceNode": "interface",
            "EnumNode": "enum",
            "AttributeNode": "attribute",
            "MemberNode": "attribute",
            "MethodNode": "method",
            "FunctionNode": "function",
            "LiteralNode": "literal",
        }
        if target_type in kind_defaults and "kind" in target_cls.defined_properties():
            scaffold_data["kind"] = kind_defaults[target_type]

        # LiteralNode needs a value with basic type classification
        if target_type == "LiteralNode":
            # Strip "literal::" prefix if present for the raw value
            raw_value = (
                target_uid.split("::", 1)[1]
                if target_uid.startswith("literal::")
                else target_uid
            )
            scaffold_data["value"] = raw_value
            scaffold_data["value_type"] = LayerGraph._classify_literal(raw_value)

        # Deserialize (computes deterministic uid)
        scaffold_node = CodeGraphNode.deserialize(scaffold_data)
        # Use the node instance's key (uid hash), not the dict key (name),
        # so that _flat_index() can find the scaffold.
        scaffold_key = LayerGraph._node_key(scaffold_node)

        key_to_entry[scaffold_key] = CompositeEntry(node=scaffold_node)

        uid = scaffold_node._uid_value()
        if uid:
            uid_to_key[uid] = scaffold_key
        identity_to_key[target_uid] = scaffold_key

        # For member types with a "::" or "."-separated qualified_name, also
        # create a parent ClassNode scaffold (if not already present)
        # and nest the member under it via COMPOSES.  This follows the
        # codegraph convention that members belong to compounds.
        # Handles both "::" (C++ convention) and "." (notional convention)
        # separators — the decompose LLM sometimes uses "." even though
        # the prompt asks for "::".
        if target_type in (
            "AttributeNode", "MemberNode", "MethodNode", "FunctionNode",
        ):
            if "::" in target_uid:
                parent_name = target_uid.rsplit("::", 1)[0]
            elif "." in target_uid and not target_uid.startswith("literal::"):
                parent_name = target_uid.rsplit(".", 1)[0]
            else:
                parent_name = None
            if parent_name:
                # Find or create the parent ClassNode
                parent_key = identity_to_key.get(parent_name)
                if parent_key is None:
                    parent_edge = {
                        "target_uid": parent_name,
                        "target_type": "ClassNode",
                        "relation_type": "COMPOSES",
                    }
                    parent_key = LayerGraph._create_missing_scaffold(
                        parent_edge, key_to_entry, uid_to_key, identity_to_key
                    )
                if parent_key is not None:
                    # Nest the member under the parent ClassNode
                    parent_entry = key_to_entry[parent_key]
                    if target_type not in parent_entry.children:
                        parent_entry.children[target_type] = {}
                    parent_entry.children[target_type][scaffold_key] = (
                        key_to_entry[scaffold_key]
                    )

        return scaffold_key

    @classmethod
    def deserialize(
        cls,
        data: list[dict],
        *,
        create_missing: bool = False,
    ) -> "LayerGraph":
        """Deserialize from a list of dicts (as produced by ``serialize()``).

        Pure deserialization — no database interaction.  Infers tags from
        the first node that has a ``tags`` field (fallback: ``frozenset({"design"})``).
        Supports backward compatibility with legacy ``layer`` field data.

        Accepts two formats:
        - **Nested format**: entries with a ``composes`` key containing
          child nodes.  COMPOSES edges are represented by nesting, not
          in the ``edges`` array.
        - **Flat format**: all nodes as separate entries with ``edges``
          arrays containing COMPOSES and other relationship types.

        Args:
            data: A list of dicts, each a serialized node with ``type``,
                properties, and optionally ``edges`` and ``composes``.
            create_missing: When True, auto-create scaffold nodes for
                edge targets that don't resolve to any node in *data*.

        Returns:
            A LayerGraph containing the deserialized nodes in a nested
            composition structure.
        """
        # Detect format: nested if any entry has a "composes" key
        has_nested = any("composes" in entry for entry in data)

        if has_nested:
            return cls._deserialize_nested(data)

        return cls._deserialize_flat(data, create_missing=create_missing)

    # ── to_neo4j ───────────────────────────────────────────────────────

    def to_neo4j(self) -> None:
        """Persist all nodes and relationships to Neo4j.

        Walks the entry tree depth-first.  Saves every node, then
        connects COMPOSES children via the parent's relationship manager
        and connects reference edges via ``find_relationship_manager()``.
        """
        # Build flat indexes for resolving reference targets.
        # uid_index: keyed by node uid (from _node_key).
        # qname_index: keyed by qualified_name (for markdown-imported
        #   references that use qnames, not uids).
        flat = self._flat_index()
        qname_index: dict[str, CompositeEntry] = {}
        for entry in self._all_entries():
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                qname_index[qname] = entry

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
                target_entry = flat.get(target_key) or qname_index.get(target_key)
                if target_entry is not None:
                    try:
                        manager = CodeGraphNode.find_relationship_manager(
                            source_node, relation_type, target_entry.node
                        )
                        manager.connect(target_entry.node)
                    except ValueError:
                        # Fallback: raw Cypher for polymorphic relationships
                        # declared on a base class (e.g. INSTANCE_OF on
                        # CompoundNode) where the concrete target subclass
                        # (e.g. ClassNode) is not matched by
                        # find_relationship_manager's exact-name check.
                        # neomodel's inherited labels still make .all()
                        # work for querying; this fallback covers the write
                        # path.
                        from neomodel import db
                        db.cypher_query(
                            f"MATCH (s), (t) "
                            f"WHERE elementId(s) = $src "
                            f"AND elementId(t) = $tgt "
                            f"MERGE (s)-[:{relation_type}]->(t)",
                            {
                                "src": db.parse_element_id(
                                    source_node.element_id
                                ),
                                "tgt": db.parse_element_id(
                                    target_entry.node.element_id
                                ),
                            },
                        )
                else:
                    # Cross-document reference: target not in this graph.
                    # Look up the target in Neo4j by qualified_name or name
                    # (e.g. tests referencing design-layer LLRs/classes
                    # ingested from a separate markdown file).
                    # LLR/HLR/Component nodes use `name`; ClassNode/
                    # FunctionNode use `qualified_name`.
                    from neomodel import db
                    results, _ = db.cypher_query(
                        "MATCH (t) "
                        "WHERE t.qualified_name = $qname OR t.name = $qname "
                        "RETURN elementId(t) LIMIT 1",
                        {"qname": target_key},
                    )
                    if results:
                        db.cypher_query(
                            f"MATCH (s), (t) "
                            f"WHERE elementId(s) = $src "
                            f"AND elementId(t) = $tgt "
                            f"MERGE (s)-[:{relation_type}]->(t)",
                            {
                                "src": db.parse_element_id(
                                    source_node.element_id
                                ),
                                "tgt": db.parse_element_id(results[0][0]),
                            },
                        )

    # ── Serialization ──────────────────────────────────────────────────

    def serialize(self, fields: str = "llm") -> list[dict]:
        """Serialize the graph as a nested list of dicts.

        Root entries are serialized recursively.  Composed children
        appear under a ``composes`` key on their parent and do not
        appear as top-level entries.  COMPOSES edges are excluded
        from the ``edges`` array since the nesting represents them
        explicitly.

        For nodes that have not been persisted to Neo4j, the
        ``edges`` key will be an empty list.

        Args:
            fields: Which property fields to include when serializing
                each node.  ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every defined property.  Passed through to
                ``CodeGraphNode.serialize()``.

        Returns:
            A list of serialized node dicts with nested composition,
            suitable for passing to ``json.dumps()`` externally.
        """
        return [entry.serialize(fields=fields) for entry in self.entries.values()]

    # ── from_neo4j ─────────────────────────────────────────────────────

    @classmethod
    def from_neo4j(cls, tag: str) -> "LayerGraph":
        """Query Neo4j for all nodes where *tag* is in their tags, plus their
        first-level neighbors.  Collect into a nested LayerGraph.

        This includes both endpoints of any edge touching a tag-matched
        node, even if the neighbor's tags don't include *tag*.

        COMPOSES edges from compound nodes create nesting; all other
        edge types are stored as references.

        Args:
            tag: The tag to query for (``"design"``, ``"as-built"``,
                ``"dependency"``).

        Returns:
            A LayerGraph containing all matching nodes and their first-level
            neighbours in a nested composition structure.
        """
        # Fetch all tag-matched nodes
        matched_nodes = CodeGraphNode.fetch_all_by_tag(tag)

        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}
        seen_uids: set[str] = set()

        # Add all tag-matched nodes
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

        # Build composition tree and collect references
        child_keys: set[str] = set()
        for key, node in nodes.items():
            entry = key_to_entry[key]

            # COMPOSES: use walk_composes() for outgoing edges
            for child in node.walk_composes():
                child_key = cls._node_key(child)
                if child_key not in key_to_entry:
                    continue  # child not in our fetched set
                child_entry = key_to_entry[child_key]
                child_type = type(child).__name__
                entry.children.setdefault(child_type, {})[child_key] = child_entry
                child_keys.add(child_key)

            # Non-COMPOSES references: use walk_edges()
            for edge in node.walk_edges():
                relation_type = edge["relation_type"]
                # Skip COMPOSES (handled above) and lazy-loaded edges
                if relation_type in ("COMPOSES", "HAS_IMPLEMENTATION"):
                    continue
                target_key = uid_to_key.get(edge["target_uid"])
                if target_key and target_key in key_to_entry:
                    entry.references.append(
                        (relation_type, target_key, edge["target_type"])
                    )

        # Root entries = nodes not composed by another node
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        return cls(tags=frozenset({tag}), entries=root_entries)