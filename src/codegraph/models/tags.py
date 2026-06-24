"""CodeGraphNode — base class for all codegraph neomodel nodes.

Provides shared fields (``source``), serialization (``serialize()``,
``deserialize()``), relationship introspection, and a registry for
type-dispatched deserialization.

Uses a combined metaclass (ABCMeta + NodeMeta) so that subclasses can
inherit from both StructuredNode and CodeGraphNode without metaclass
conflicts.
"""

from __future__ import annotations

from abc import ABCMeta

from neomodel import StringProperty
from neomodel.sync_.node import NodeMeta


class _CodeGraphNodeMeta(NodeMeta, ABCMeta):
    """Combined metaclass: NodeMeta for neomodel properties, ABCMeta for
    any abstract methods that may be added.

    NodeMeta.__new__ is only invoked for subclasses that inherit from
    ``StructuredNode``. For plain ABC subclasses (including CodeGraphNode
    itself), the pure ABCMeta path is used.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        from neomodel import StructuredNode

        is_neomodel = any(
            issubclass(b, StructuredNode)
            for b in bases
            if isinstance(b, type) and b is not object
        )
        if not is_neomodel:
            # Pure ABC path — skip NodeMeta initialization
            return ABCMeta.__new__(mcs, name, bases, namespace, **kwargs)

        # NodeMeta.__new__ calls type.__new__ directly, bypassing ABCMeta.
        # Re-compute __abstractmethods__ so @abstractmethod works if added.
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        abstracts: set[str] = set()
        for base in bases:
            for attr in getattr(base, "__abstractmethods__", ()):
                value = namespace.get(attr, getattr(base, attr, None))
                if getattr(value, "__isabstractmethod__", False):
                    abstracts.add(attr)
        for attr, value in namespace.items():
            if getattr(value, "__isabstractmethod__", False):
                abstracts.add(attr)
        if abstracts:
            cls.__abstractmethods__ = frozenset(abstracts)
        return cls


class CodeGraphNode(metaclass=_CodeGraphNodeMeta):
    """Base class for all codegraph neomodel nodes.

    Provides shared fields, serialization, relationship introspection,
    and a registry for type-dispatched deserialization.

    Identity model:
        Every node has a ``uid`` ``UniqueIdProperty`` that serves as the
        cross-codebase-stable primary key.  ``uid`` is computed
        *automatically* in the :meth:`save` hook from the node's
        ``_identity_fields`` (e.g. ``qualified_name`` + ``argsstring``
        for functions/methods), so callers never need to pass it.

        The human-readable ``qualified_name`` / ``refid`` fields remain
        as regular indexed properties for queryability — they are no longer
        the uniqueness constraint.

    Attributes:
        name: Short name of the node (e.g. 'Widget', 'draw', 'widget.h').
        refid: External reference ID from the source system (e.g. Doxygen
            refid).  Regular indexed StringProperty (FileNode).
        source: Name of the project this node belongs to.
        uid: Deterministic SHA-1 hash of the node's identity fields — the
            cross-codebase-stable unique key used for edge resolution.

    Subclasses must:
    - Declare ``_llm_fields`` as a class-level ``set[str]`` of field names
    - Declare ``_identity_fields`` as a class-level ``tuple[str, ...]`` of
      field names to hash into ``uid``
    """

    _llm_fields: set[str] = set()

    # Fields whose values are hashed (in order) to produce ``uid``.
    # Subclasses override this.  For functions/methods it includes
    # ``argsstring`` so that overloads get distinct uids.
    _identity_fields: tuple[str, ...] = ()

    # ── Identity ────────────────────────────────────────────────────────────
    name = StringProperty(
        default="",
        help_text="Short name of the node (e.g. 'Widget', 'draw', 'widget.h').",
    )
    refid = StringProperty(
        default="",
        help_text="External reference ID from the source system "
        "(e.g. Doxygen refid). FileNode overrides this as UniqueIdProperty.",
    )

    # ── Provenance ──────────────────────────────────────────────────────────
    source = StringProperty(
        default="",
        help_text="Name of the project this node belongs to (e.g. 'codegraph', 'llvm').",
    )

    # ── Relationship introspection ────────────────────────────────────────

    @classmethod
    def find_relationship_manager(cls, source, relation_type: str, target):
        """Find the relationship manager on *source* matching both
        *relation_type* and the class of *target*.

        Needed because some relation types (e.g. COMPOSES) have multiple
        managers on the same source class pointing at different target types.

        Args:
            source: The neomodel node instance to search on.
            relation_type: Neo4j relationship label (e.g. "COMPOSES",
                "DEFINED_IN").
            target: The target node instance whose class determines which
                manager to return.

        Returns:
            The relationship manager attribute (e.g. ``source.methods``).

        Raises:
            ValueError: If no matching manager is found.
        """
        from neomodel import RelationshipTo, RelationshipFrom

        target_cls = type(target)
        for klass in type(source).__mro__:
            for name, val in vars(klass).items():
                if isinstance(val, (RelationshipTo, RelationshipFrom)):
                    if val.definition["relation_type"] != relation_type:
                        continue
                    rel_target = val.definition.get("model") or val._raw_class
                    if rel_target == target_cls:
                        return getattr(source, name)
                    if isinstance(rel_target, str) and (
                        rel_target == target_cls.__name__
                        or rel_target.endswith(f".{target_cls.__name__}")
                    ):
                        return getattr(source, name)
        raise ValueError(
            f"No '{relation_type}' relationship from "
            f"{type(source).__name__} to {target_cls.__name__}"
        )

    # ── Tag-aware queries ───────────────────────────────────────────────

    @classmethod
    def fetch_by_tag(cls, tag: str) -> list["CodeGraphNode"]:
        """Fetch all persisted instances of this type matching *tag*.

        Uses a Cypher ``WHERE $tag IN n.tags`` query for array membership.
        Returns an empty list for types that don't have a ``tags``
        property (e.g. FileNode, ParameterNode).

        Args:
            tag: The tag to filter by (e.g. "design", "as-built",
                "dependency").

        Returns:
            A list of CodeGraphNode instances matching the given tag.
        """
        if "tags" not in cls.defined_properties():
            return []
        from neomodel import db
        label = cls.__label__
        query = f"MATCH (n:`{label}`) WHERE $tag IN n.tags RETURN n"
        results, _ = db.cypher_query(query, {"tag": tag})
        return [cls.inflate(row[0]) for row in results]

    @classmethod
    def fetch_all_by_tag(cls, tag: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *tag*.

        Iterates ``_registry``, calling ``fetch_by_tag`` on each
        concrete subclass. Returns a flat list.

        Args:
            tag: The tag to filter by (e.g. "design", "as-built",
                "dependency").

        Returns:
            A flat list of CodeGraphNode instances across all registered
            types matching the given tag.
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            result.extend(node_cls.fetch_by_tag(tag))
        return result

    # ── Tag mutation helpers ─────────────────────────────────────────────

    def add_tag(self, tag: str) -> "CodeGraphNode":
        """Add *tag* to this node's tags list. Persists the change to Neo4j.

        Does nothing if the tag is already present. Does nothing for
        node types that don't have a ``tags`` property.

        Args:
            tag: The tag to add (e.g. "design", "as-built", "dependency").

        Returns:
            This node instance (after saving), for chaining.
        """
        if "tags" not in type(self).defined_properties():
            return self
        current = list(self.tags) if self.tags else []
        if tag not in current:
            current.append(tag)
            self.tags = current
            self.save()
        return self

    def remove_tag(self, tag: str) -> "CodeGraphNode":
        """Remove *tag* from this node's tags list. Persists the change.

        Does nothing if the tag is not present. Does nothing for
        node types that don't have a ``tags`` property.

        Args:
            tag: The tag to remove.

        Returns:
            This node instance (after saving), for chaining.
        """
        if "tags" not in type(self).defined_properties():
            return self
        current = list(self.tags) if self.tags else []
        if tag in current:
            current.remove(tag)
            self.tags = current
            self.save()
        return self

    def has_tag(self, tag: str) -> bool:
        """Check whether this node has *tag* in its tags list.

        Returns False for node types that don't have a ``tags`` property.

        Args:
            tag: The tag to check for.

        Returns:
            True if the tag is present, False otherwise.
        """
        if "tags" not in type(self).defined_properties():
            return False
        return tag in (self.tags or [])

    @classmethod
    def fetch_all_by_source(cls, source: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *source*.

        Iterates ``_registry``, calling ``.nodes.filter(source=source)`` on
        each type that has a ``source`` property. Returns a flat list.

        Args:
            source: The source project name to filter by (e.g. "codegraph",
                "llvm").

        Returns:
            A flat list of CodeGraphNode instances matching the given source.
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            if "source" in node_cls.defined_properties():
                result.extend(node_cls.nodes.filter(source=source))
        return result

    @classmethod
    def fetch_all_by_kind(cls, kind: str, tag: str | None = None) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *kind*.

        Optionally filter by *tag* as well. Only types that have a ``kind``
        property are queried. Returns a flat list.

        Args:
            kind: The node kind to filter by (e.g. "class", "method").
            tag: Optional tag to additionally filter by. When provided,
                only nodes with both matching kind and tag are returned.

        Returns:
            A flat list of CodeGraphNode instances matching the given kind
            (and optionally tag).
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            props = node_cls.defined_properties()
            if "kind" not in props:
                continue
            if tag is not None and "tags" not in props:
                continue
            filters: dict = {"kind": kind}
            nodes = list(node_cls.nodes.filter(**filters))
            if tag is not None and "tags" in props:
                nodes = [n for n in nodes if tag in (n.tags or [])]
            result.extend(nodes)
        return result

    # ── Registry ──────────────────────────────────────────────────────────
    # Every concrete CodeGraphNode subclass registers itself here so that
    # ``deserialize()`` can look up the right class by the ``type`` discriminator.
    _registry: dict[str, type["CodeGraphNode"]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Only register concrete classes that have their own ``_llm_fields``.
        # Mixins like CompoundNode / MemberNode set _llm_fields but are
        # still abstract (they inherit from StructuredNode directly). We skip
        # any class whose name starts with an underscore by convention.
        if not cls.__name__.startswith("_") and cls._llm_fields:
            CodeGraphNode._registry[cls.__name__] = cls

            # Override neomodel's delete() on each concrete class.
            # Without this injection, MRO resolution finds
            # StructuredNode.delete() first (StructuredNode precedes
            # CodeGraphNode in the MRO of every concrete subclass),
            # so our enhanced version on CodeGraphNode would be shadowed.
            # Putting delete directly in the concrete class's __dict__
            # makes it the first entry found during method resolution.
            #
            # create() is NOT injected because neomodel's
            # StructuredNode.create() is called internally by save(),
            # and overriding it on concrete classes breaks the internal
            # creation path.  Instead, save_new() (below) provides
            # the single-node creation API.
            # Inject save() — same MRO-shadowing rationale as delete()
            # above: StructuredNode precedes CodeGraphNode in the MRO of
            # every concrete subclass, so a save() defined on CodeGraphNode
            # would be shadowed.  Putting it in the concrete class's
            # __dict__ makes it the first entry found.
            if "save" not in cls.__dict__:
                cls.save = CodeGraphNode._save

            if "delete" not in cls.__dict__:
                cls.delete = CodeGraphNode._delete

            # Inject save_new() as a convenience classmethod on each
            # concrete class::
            #
            #     ClassNode.save_new(name="Widget", kind="class",
            #                       qualified_name="ns::Widget")
            #
            # Validates properties, constructs, saves, and returns the
            # instance in one call.
            if "save_new" not in cls.__dict__:
                def _make_save_new(klass):
                    def save_new(kls, **kwargs):
                        return CodeGraphNode._save_new(klass, **kwargs)
                    return classmethod(save_new)
                cls.save_new = _make_save_new(cls)

    # ── Create / Delete ──────────────────────────────────────────────────

    @staticmethod
    def _save_new(cls, **kwargs) -> "CodeGraphNode":
        """Create and persist a single node instance.

        Validates that all keyword arguments correspond to declared
        neomodel properties, constructs a node instance, saves it to
        Neo4j, and returns the saved instance.

        Called by the ``save_new()`` classmethod injected on each
        concrete subclass via ``__init_subclass__``.

        Args:
            cls: The concrete CodeGraphNode subclass to instantiate.
            **kwargs: Property names and their initial values.
                Each key must correspond to a declared neomodel property
                on ``cls``.

        Returns:
            The saved node instance.

        Raises:
            ValueError: If any key is not a declared property on ``cls``.
        """
        props = cls.defined_properties()
        invalid = set(kwargs) - set(props)
        if invalid:
            raise ValueError(
                f"Unknown property(ies) on {cls.__name__}: "
                f"{sorted(invalid)}. "
                f"Valid properties: {sorted(props)}"
            )
        node = cls(**kwargs)
        return node.save()

    # ── UID computation ────────────────────────────────────────────────

    def _compute_uid(self) -> str:
        """Compute deterministic uid from identity fields without saving.

        Derives a SHA-1 hash from the node's ``_identity_fields``
        (e.g. ``qualified_name`` + normalised ``argsstring`` for
        functions/methods).  Returns an empty string if the primary
        identity field is empty, signalling the caller to leave the
        ``UniqueIdProperty`` auto-generated value untouched.

        Returns:
            The 40-character hex hash string, or ``""`` if identity
            fields are empty.
        """
        from codegraph.uid import compute_uid, normalize_argsstring

        identity_fields = getattr(type(self), "_identity_fields", ())
        parts: list[str] = []
        for field in identity_fields:
            val = getattr(self, field, None)
            if val is None:
                val = ""
            val = str(val)
            if field == "argsstring":
                val = normalize_argsstring(val)
            parts.append(val)
        return compute_uid(*parts)

    # ── Save (uid computation hook) ────────────────────────────────────

    def _save(self) -> "CodeGraphNode":
        """Save this node to Neo4j, computing ``uid`` from identity fields.

        Before delegating to neomodel's ``StructuredNode.save()``, derives
        a deterministic SHA-1 hash from the node's ``_identity_fields``
        and assigns it to ``uid``.  This makes the same logical symbol in
        different codebases produce the same ``uid``, enabling
        cross-codebase edge resolution.

        If all identity-field values are empty (e.g. a node constructed
        without a ``qualified_name``), the ``UniqueIdProperty``
        auto-generated random value is left untouched.

        Returns:
            This node instance (after saving).
        """
        from neomodel.sync_.node import StructuredNode

        computed = self._compute_uid()
        if computed:
            self.uid = computed

        return StructuredNode.save(self)

    def _delete(self) -> "CodeGraphNode":
        """Delete this node from Neo4j, cascading to composed children first.

        Any node reachable via an outgoing COMPOSES relationship is
        considered an owned child and is deleted recursively (depth-
        first, leaves first) before this node is removed.  This mirrors
        the containment semantics of the code graph: deleting a
        namespace deletes its classes, which delete their methods, and
        so on.

        After cascading, all remaining relationships on this node
        (both outgoing and incoming) are explicitly disconnected to
        clear the in-memory caches of related nodes — neomodel's
        default ``DETACH DELETE`` removes relationships at the database
        level but does not update other nodes' relationship manager
        caches.

        Must be called on a saved node (one with an
        ``element_id_property``).  After deletion the node is marked
        as deleted and should not be reused.

        Returns:
            This node instance (marked as deleted, no longer persisted).

        Raises:
            ValueError: If the node has not been saved to Neo4j yet
                (no ``element_id_property``).

        Example:
            >>> ns = NamespaceNode.save_new(name="my_ns", kind="namespace",
            ...                              qualified_name="my_ns")
            >>> cls = ClassNode.save_new(name="Widget", kind="class",
            ...                         qualified_name="my_ns::Widget")
            >>> ns.classes.connect(cls)
            >>> ns.delete()  # deletes cls first (composed child), then ns
        """
        from neomodel import RelationshipTo, RelationshipFrom
        from neomodel.sync_.node import StructuredNode

        if not hasattr(self, "element_id_property"):
            raise ValueError(
                f"Cannot delete unsaved {type(self).__name__} instance. "
                "Save the node first before calling delete()."
            )

        # Cascade: delete all composed children (depth-first, leaves
        # first) before deleting this node.  COMPOSES represents
        # ownership containment, so children should not outlive their
        # parent.
        for child in self.walk_composes():
            if hasattr(child, "element_id_property") and not getattr(child, "deleted", False):
                child.delete()

        # Disconnect all remaining relationships to clear caches of
        # related nodes.  neomodel's DETACH DELETE removes relationships
        # at the Cypher level but does not update other nodes'
        # Python-side relationship caches.
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                manager = getattr(self, name)
                try:
                    for connected in manager.all():
                        try:
                            manager.disconnect(connected)
                        except Exception:
                            pass  # best-effort disconnect
                except Exception:
                    pass  # unsaved or unavailable relationship manager

        # Delegate to neomodel's DETACH DELETE
        StructuredNode.delete(self)
        return self

    # ── Serialization ─────────────────────────────────────────────────────

    def walk_composes(self) -> list["CodeGraphNode"]:
        """Return all nodes that this node composes via outgoing COMPOSES edges.

        Walks all ``RelationshipTo`` managers with
        ``relation_type="COMPOSES"`` and returns the connected target
        nodes.

        Requires the node to be saved in Neo4j (the relationship managers
        query the database).  Returns an empty list for unsaved nodes.

        Returns:
            A list of CodeGraphNode instances that this node composes.
        """
        from neomodel import RelationshipTo

        # Unsaved nodes have no database relationships to walk
        if not hasattr(self, "element_id_property"):
            return []

        children: list[CodeGraphNode] = []
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, RelationshipTo):
                    continue
                if val.definition["relation_type"] != "COMPOSES":
                    continue
                if name in seen:
                    continue
                seen.add(name)
                children.extend(getattr(self, name).all())
        return children

    def serialize(
        self,
        fields: str = "llm",
        nested: bool = False,
        _seen: set | None = None,
    ) -> dict:
        """Return a serialized representation of this node.

        By default (``fields="llm"``, ``nested=False``), only includes
        property fields listed in the node's ``_llm_fields`` set — the
        minimal subset relevant for LLM consumption.  Pass
        ``fields="all"`` to include every neomodel-defined property.

        When ``nested=True``, walks outgoing COMPOSES relationship
        managers and inlines composed children under a ``composes``
        key.  COMPOSES edges are removed from the ``edges`` array since
        the nesting represents them explicitly.  The node's unique
        identifier property is always included for roundtrip target
        resolution.  Cycle detection via ``_seen`` prevents infinite
        recursion.

        Regardless of *fields* and *nested*, the result always includes
        a ``type`` discriminator and, if the node has been saved to
        Neo4j, a list of relationship edges from
        ``serialize_edges()``.  For unsaved nodes the ``edges`` key is
        an empty list.

        Args:
            fields: Which property fields to include.
                ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every defined property.
            nested: If True, inline composed children under a
                ``composes`` key.  Requires the node to be persisted in
                Neo4j.
            _seen: Internal — set of uid values for cycle detection.
                Not part of the public API.

        Returns:
            A dict with ``type``, property fields, ``edges``, and
            optionally ``composes`` keys.
        """
        props = dict(self.__properties__)
        if fields == "all":
            result = dict(sorted(props.items()))
        else:
            result = {k: props[k] for k in sorted(self._llm_fields) if k in props}
        result["type"] = type(self).__name__

        # Always include the uid property (e.g. ``uid``) so that
        # roundtrip deserialization and edge target resolution work
        # regardless of the *fields* selection.  ``uid`` is a deterministic
        # hash — it is included for resolution, not for LLM readability.
        uid_prop = type(self)._uid_prop()
        uid_value = self._uid_value()
        if uid_prop and uid_value and uid_prop not in result:
            result[uid_prop] = uid_value

        if hasattr(self, "element_id_property"):
            all_edges = self.serialize_edges()
            if nested:
                # Remove COMPOSES edges — they are represented by nesting
                result["edges"] = [
                    e for e in all_edges
                    if e["relation_type"] != "COMPOSES"
                ]
            else:
                result["edges"] = all_edges
        else:
            result["edges"] = []

        if nested:
            # Cycle detection
            if _seen is None:
                _seen = set()
            if uid_value:
                _seen.add(uid_value)

            # Walk COMPOSES relationships and serialize children recursively
            composes = self._serialize_composes(fields=fields, _seen=_seen)
            if composes:
                result["composes"] = composes

        return result

    def _serialize_composes(
        self,
        fields: str = "llm",
        _seen: set | None = None,
    ) -> list[dict]:
        """Serialize all COMPOSES children of this node recursively.

        Walks outgoing COMPOSES relationship managers, filters out
        already-seen nodes (cycle prevention), and recursively serializes
        each child with ``nested=True``.

        Args:
            fields: Which property fields to include for each child.
            _seen: Set of uid values for cycle detection.

        Returns:
            A list of serialized child dicts, or an empty list if this
            node has no composed children.
        """
        children = self.walk_composes()
        composes: list[dict] = []
        for child in children:
            child_uid = child._uid_value()
            # Skip already-visited nodes (cycle prevention)
            if _seen is not None and child_uid and child_uid in _seen:
                continue
            composes.append(
                child.serialize(fields=fields, nested=True, _seen=_seen)
            )
        return composes

    @classmethod
    def deserialize(cls, data: dict) -> "CodeGraphNode":
        """Instantiate the correct subclass from a serialized dict.

        Reads the ``type`` key to dispatch to the registered subclass,
        then constructs an instance from the remaining properties.
        Keys ``edges`` and ``type`` are ignored — edges are resolved
        separately via Neo4j after nodes are saved.

        The ``type`` key is required when called on the base
        ``CodeGraphNode`` class.  When called directly on a concrete
        subclass, ``type`` is optional (defaults to that subclass).

        Args:
            data: A serialized dict, typically with a ``type`` discriminator.

        Returns:
            A new instance of the appropriate CodeGraphNode subclass.

        Raises:
            ValueError: If the ``type`` key is missing and *cls* is the
                abstract ``CodeGraphNode`` base.
            KeyError: If the ``type`` value is not in the registry.
        """
        type_name = data.get("type")
        if type_name is not None:
            if type_name not in cls._registry:
                raise KeyError(
                    f"Unknown node type '{type_name}'. "
                    f"Registered types: {sorted(cls._registry.keys())}"
                )
            target_cls = cls._registry[type_name]
        elif cls is CodeGraphNode or not cls._llm_fields:
            raise ValueError(
                "Serialized data is missing the 'type' discriminator"
            )
        else:
            target_cls = cls

        skip = {"edges", "type"}
        # Backward compatibility: convert legacy "layer" field to "tags".
        # If data has "layer" but no "tags", promote the single layer value
        # into a tags list.
        compat_data = dict(data)
        if "layer" in compat_data and "tags" not in compat_data:
            compat_data["tags"] = [compat_data.pop("layer")]
        filtered = {k: v for k, v in compat_data.items()
                    if k not in skip and k in target_cls.defined_properties()}
        node = target_cls(**filtered)

        # Compute deterministic uid from identity fields when not
        # explicitly provided in the input data.  This allows
        # LayerGraph.deserialize() to resolve edge targets by uid
        # without requiring the caller to pre-compute hashes.
        uid_prop = target_cls._uid_prop()
        if uid_prop and uid_prop not in data:
            computed = node._compute_uid()
            if computed:
                setattr(node, uid_prop, computed)

        return node

    @classmethod
    def serialize_relationships(cls) -> list[dict]:
        """Return relationship descriptors for this node type.

        Inspects ``RelationshipTo`` / ``RelationshipFrom`` descriptors
        statically — no database call needed.

        Returns:
            A list of dicts, each with keys: ``attr`` (Python attribute name),
            ``relation_type`` (Neo4j relationship label), ``direction``
            ("OUTGOING" or "INCOMING"), and ``target`` (dotted class path of
            the target node).
        """
        from neomodel import RelationshipTo, RelationshipFrom

        rels: list[dict] = []
        for klass in cls.__mro__:
            for name, val in vars(klass).items():
                if isinstance(val, RelationshipTo):
                    d = val.definition
                    rels.append({
                        "attr": name,
                        "relation_type": d["relation_type"],
                        "direction": d["direction"].name,
                        "target": d.get("model") or val._raw_class,
                    })
                elif isinstance(val, RelationshipFrom):
                    d = val.definition
                    rels.append({
                        "attr": name,
                        "relation_type": d["relation_type"],
                        "direction": "INCOMING",
                        "target": d.get("model") or val._raw_class,
                    })
        return rels

    @classmethod
    def _uid_prop(cls) -> str | None:
        """Return the name of this node type's UniqueIdProperty, or None.

        Returns:
            The property name string if a UniqueIdProperty exists, otherwise
            None.
        """
        from neomodel import UniqueIdProperty

        for name, prop in cls.defined_properties().items():
            if isinstance(prop, UniqueIdProperty):
                return name
        return None

    def _uid_value(self) -> str | None:
        """Return the value of this instance's unique identifier, or None.

        Returns:
            The unique identifier value string if a UniqueIdProperty exists,
            otherwise None.
        """
        uid = type(self)._uid_prop()
        if uid is None:
            return None
        return getattr(self, uid, None)

    def serialize_edges(self) -> list[dict]:
        """Return all edges from this node as a flat list of relationship dicts.

        Walks every ``RelationshipTo`` / ``RelationshipFrom`` descriptor
        on this *instance*, calls ``.all()`` on each manager, and emits
        one dict per connected node with the relationship type and the
        connected node's unique identifier.

        Requires the node to be saved in Neo4j (the relationship managers
        query the database).

        Returns:
            A list of dicts, each with keys: ``relation_type`` (Neo4j
            relationship label), ``target_uid`` (the connected node's
            unique id value), and ``target_type`` (the connected node's
            class name).
        """
        from neomodel import RelationshipTo, RelationshipFrom

        edges: list[dict] = []
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if isinstance(val, (RelationshipTo, RelationshipFrom)):
                    if name not in seen:
                        seen.add(name)
                        manager = getattr(self, name)
                        connected = manager.all()
                        for node in connected:
                            edges.append({
                                "relation_type": val.definition["relation_type"],
                                "target_uid": node._uid_value(),
                                "target_type": type(node).__name__,
                            })
        return edges

    def update(self, **kwargs) -> "CodeGraphNode":
        """Update one or more property fields and persist the changes to Neo4j.

        Sets each keyword argument as an attribute on this node instance,
        then calls ``save()`` to write the changes to the database.

        Only neomodel-defined properties are accepted — passing a key
        that is not a declared property raises ``ValueError``.

        Args:
            **kwargs: Property names and their new values.
                Each key must correspond to a declared neomodel property
                on this node type (e.g. ``name``, ``source``, ``kind``,
                ``brief_description``, etc.).

        Returns:
            This node instance (after saving), for chaining.

        Raises:
            ValueError: If any key is not a declared property on this
                node type.
            ValueError: If the node has not been saved to Neo4j yet
                (no ``element_id_property``).

        Example:
            >>> node = ClassNode.nodes.get(qualified_name="MyClass")
            >>> node.update(brief_description="Updated", tags=["design", "as-built"])
            ClassNode(name='MyClass', ...)
        """
        if not hasattr(self, "element_id_property"):
            raise ValueError(
                f"Cannot update unsaved {type(self).__name__} instance. "
                "Save the node first before calling update()."
            )

        props = type(self).defined_properties()
        invalid = set(kwargs) - set(props)
        if invalid:
            raise ValueError(
                f"Unknown property(ies) on {type(self).__name__}: "
                f"{sorted(invalid)}. "
                f"Valid properties: {sorted(props)}"
            )

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.save()
        return self

    def walk_edges(self) -> list[dict]:
        """Walk relationship descriptors, classifying each edge by direction.

        Unlike :meth:`serialize_edges`, this method distinguishes outgoing
        (``RelationshipTo``) from incoming (``RelationshipFrom``) edges so
        that callers can handle COMPOSES nesting direction correctly.
        Direction is derived from the descriptor type — no extra field is
        added to :meth:`serialize_edges` output.

        Requires the node to be saved in Neo4j (the relationship managers
        query the database).

        Returns:
            A list of dicts, each with keys:

            - ``relation_type`` — Neo4j relationship label
            - ``target_uid`` — connected node's unique id value
            - ``target_type`` — connected node's class name
            - ``is_outgoing`` — ``True`` for ``RelationshipTo``,
              ``False`` for ``RelationshipFrom``
        """
        from neomodel import RelationshipTo, RelationshipFrom

        edges: list[dict] = []
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)

                is_outgoing = isinstance(val, RelationshipTo)
                manager = getattr(self, name)

                for target in manager.all():
                    edges.append({
                        "relation_type": val.definition["relation_type"],
                        "target_uid": target._uid_value(),
                        "target_type": type(target).__name__,
                        "is_outgoing": is_outgoing,
                    })

        return edges

    # ── Markdown rendering ──────────────────────────────────────────────

    _markdown_keyword: str = ""
    """Capitalized heading keyword for Markdown export.

    Subclasses MUST set this.  Examples: ``"Namespace"``, ``"Class"``,
    ``"Interface"``, ``"Enum"``, ``"Function"``.
    """

    def markdown_is_heading(self) -> bool:
        """Whether this node produces a Markdown heading during export.

        Returns ``True`` for all node types except :class:`FileNode`,
        which renders as a note in the ``## File Notes`` section.
        """
        return True

    def markdown_body_type(self) -> str | None:
        """What kind of body section to render after the heading.

        Returns:
            ``"compound"`` — ``**Public methods:**`` / ``**Public attributes:**``
            ``"enum"`` — ``**Values:**`` section
            ``None`` — no body section (namespaces, file nodes)
        """
        return "compound"

    def to_markdown(self, depth: int) -> list[str]:
        """Return Markdown heading and description lines for this node.

        Called by :class:`~codegraph.markdown.MarkdownExporter` during
        export.  The exporter handles child recursion, member lists,
        and relationship rendering separately.

        Args:
            depth: Heading level (2 = ``##``, 3 = ``###``, etc.).

        Returns:
            A list of Markdown lines (heading + description).
        """
        keyword = self._markdown_keyword or _default_markdown_keyword(
            type(self).__name__
        )
        qname = getattr(self, "qualified_name", None) or self.name
        lines = [f"{'#' * depth} {keyword}: `{qname}`"]

        # Walk common description sources: brief_description on compounds,
        # description on namespaces.  FileNode has neither and returns empty.
        desc = (
            getattr(self, "brief_description", "")
            or getattr(self, "description", "")
        )
        if desc:
            lines.append(desc)

        return lines


def _default_markdown_keyword(node_type_name: str) -> str:
    """Fallback when a node type hasn't set ``_markdown_keyword``."""
    defaults: dict[str, str] = {
        "NamespaceNode": "Namespace",
        "ModuleNode": "Namespace",
        "ClassNode": "Class",
        "InterfaceNode": "Interface",
        "EnumNode": "Enum",
        "UnionNode": "Class",
        "ConceptNode": "Class",
        "FunctionNode": "Function",
        "DefineNode": "Function",
        "MethodNode": "Method",
        "AttributeNode": "Attribute",
        "EnumValueNode": "EnumValue",
        "FileNode": "Note",
        "TestNode": "Test",
        "AssertionNode": "Assertion",
        "TestStepNode": "TestStep",
        "TestFixtureNode": "TestFixture",
    }
    return defaults.get(node_type_name, "Class")