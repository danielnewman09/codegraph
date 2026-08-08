"""CodeGraphNode — base class for all codegraph node types.

Provides shared fields (``source``), serialization (``serialize()``,
``deserialize()``), relationship introspection, and a registry for
type-dispatched deserialization.

Pure-Python node model: no neomodel dependency.  All storage I/O is
delegated to the active backend via ``get_backend()``.
"""

from __future__ import annotations

import logging
from abc import ABCMeta
from typing import Any

from codegraph.backends import get_backend
from codegraph.models.descriptors import (
    Property,
    PropertyRegistry,
    Relationship as CGRelationship,
)


class CodeGraphNode(metaclass=ABCMeta):
    """Base class for all codegraph node types.

    Provides shared fields, serialization, relationship introspection,
    and a registry for type-dispatched deserialization.

    Identity model:
        Every node has a ``uid`` ``UniqueId`` descriptor that serves as the
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

    class DoesNotExist(Exception):
        """Raised when a node query matches no nodes."""

    @property
    def element_id(self) -> Any | None:
        """Backend element id of the persisted node, or None if unsaved.

        Mirrors neomodel's ``StructuredNode.element_id`` so that the
        model layer exposes the same attribute regardless of backend.
        """
        return getattr(self, "element_id_property", None)

    @property
    def __properties__(self) -> dict[str, Any]:
        """Read-only dict view of declared property values.

        Legacy consumers (e.g. the doxygen-index batch writer) read
        ``node.__properties__.items()``; the view is computed on demand
        from the ``_props`` store.  Mutation through this view is not
        supported — writes go through the ``Property`` descriptors.
        """
        props, _ = PropertyRegistry.of(type(self))
        store = self.__dict__.setdefault("_props", {})
        return {name: store[name] for name in props if name in store}

    @classmethod
    def inherited_labels(cls) -> list[str]:
        """Return the Neo4j label chain for this node type.

        Mirrors neomodel's ``StructuredNode.inherited_labels()`` for
        pure-Python classes: the class's own name plus every
        intermediate ``CodeGraphNode`` subclass (e.g.
        ``ClassNode`` → ``["ClassNode", "CompoundNode"]``).  Keeping
        the intermediate labels matches what neomodel wrote before
        migration, so raw Cypher queries matching ``:CompoundNode`` /
        ``:MemberNode`` continue to work.
        """
        labels: list[str] = []
        for base in cls.__mro__:
            if base is CodeGraphNode:
                break
            if base is not cls and not issubclass(base, CodeGraphNode):
                continue
            if base.__name__ not in labels:
                labels.append(base.__name__)
        return labels

    def __eq__(self, other: Any) -> bool:
        """Compare by backend element id when both nodes are saved.

        Mirrors neomodel's ``StructuredNode.__eq__`` identity semantics.
        """
        if not isinstance(other, CodeGraphNode):
            return NotImplemented
        self_eid = getattr(self, "element_id_property", None)
        other_eid = getattr(other, "element_id_property", None)
        if self_eid is not None and other_eid is not None:
            return self_eid == other_eid
        return self is other

    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        eid = getattr(self, "element_id_property", None)
        if eid is not None:
            return hash(eid)
        return hash(id(self))

    # Fields whose values are hashed (in order) to produce ``uid``.
    # Subclasses override this.  For functions/methods it includes
    # ``argsstring`` so that overloads get distinct uids.
    _identity_fields: tuple[str, ...] = ()

    def __init__(self, **kwargs: Any) -> None:
        """Initialise a node with the given property values.

        Sets each keyword argument via ``setattr``, which invokes our
        ``Property.__set__`` and lazily creates ``_props``.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    # ── Identity ────────────────────────────────────────────────────────────
    name = Property(
        str,
        default="",
        help_text="Short name of the node (e.g. 'Widget', 'draw', 'widget.h').",
    )
    refid = Property(
        str,
        default="",
        help_text="External reference ID from the source system "
        "(e.g. Doxygen refid). FileNode overrides this as UniqueId.",
    )

    # ── Provenance ──────────────────────────────────────────────────────────
    source = Property(
        str,
        default="",
        help_text="Name of the project this node belongs to (e.g. 'codegraph', 'llvm').",
    )

    # ── Relationship introspection ────────────────────────────────────────

    @classmethod
    def find_relationship_manager(cls, source, relation_type: str, target):
        """Find the relationship descriptor on *source* matching both
        *relation_type* and the class of *target*.

        Needed because some relation types (e.g. COMPOSES) have multiple
        managers on the same source class pointing at different target types.

        Args:
            source: The node instance to search on.
            relation_type: Neo4j relationship label (e.g. "COMPOSES",
                "DEFINED_IN").
            target: The target node instance whose class determines which
                manager to return.

        Returns:
            The matching relationship descriptor (``Relationship``).

        Raises:
            ValueError: If no matching manager is found.
        """
        from codegraph.models.descriptors import find_relationship_descriptor

        target_cls = type(target)
        source_type = type(source)

        descriptor = find_relationship_descriptor(
            source_type, relation_type, target_cls
        )
        if descriptor is None:
            raise ValueError(
                f"No '{relation_type}' relationship from "
                f"{source_type.__name__} to {target_cls.__name__}"
            )
        return descriptor

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
        if not PropertyRegistry.has_property(cls, "tags"):
            return []
        from codegraph.backends import get_backend
        label = _class_label(cls)
        query = f"MATCH (n:`{label}`) WHERE $tag IN n.tags RETURN n"
        results, _ = get_backend().execute_raw(query, {"tag": tag})
        return [get_backend().inflate(row[0], cls) for row in results]

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
        for node_cls in list(cls._registry.values()):
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
        if not PropertyRegistry.has_property(type(self), "tags"):
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
        if not PropertyRegistry.has_property(type(self), "tags"):
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
        if not PropertyRegistry.has_property(type(self), "tags"):
            return False
        return tag in (self.tags or [])



    # ── Registry ──────────────────────────────────────────────────────────
    # Every concrete CodeGraphNode subclass registers itself here so that
    # ``deserialize()`` can look up the right class by the ``type`` discriminator.
    _registry: dict[str, type["CodeGraphNode"]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Register every concrete subclass with ABCMeta to prevent
        # negative-cache poisoning of issubclass() checks.  The ABCMeta
        # negative cache can cause issubclass(ClassNode, CodeGraphNode)
        # to return False after unrelated test code triggers a failed
        # subclass check.
        CodeGraphNode.register(cls)
        # Only register concrete classes that have their own ``_llm_fields``.
        # Mixins like CompoundNode / MemberNode set _llm_fields but are
        # abstract. We skip any class whose name starts with an underscore
        # by convention.
        if not cls.__name__.startswith("_") and cls._llm_fields:
            CodeGraphNode._registry[cls.__name__] = cls

            # Inject save() / delete() / save_new() so they are first in
            # method resolution for every concrete subclass.
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

            # Inject a ``.nodes`` query shim that delegates to the
            # active backend.  No storage logic lives in the model layer.
            if "nodes" not in cls.__dict__:
                cls.nodes = _BackendNodeSet(cls)

    # ── Create / Delete ──────────────────────────────────────────────────

    @staticmethod
    def _save_new(cls, **kwargs) -> "CodeGraphNode":
        """Create and persist a single node instance.

        Validates that all keyword arguments correspond to declared
        properties, constructs a node instance, saves it to the
        backend, and returns the saved instance.

        Called by the ``save_new()`` classmethod injected on each
        concrete subclass via ``__init_subclass__``.

        Args:
            cls: The concrete CodeGraphNode subclass to instantiate.
            **kwargs: Property names and their initial values.
                Each key must correspond to a declared property
                on ``cls``.

        Returns:
            The saved node instance.

        Raises:
            ValueError: If any key is not a declared property on ``cls``.
        """
        valid = PropertyRegistry.properties_of(cls)
        invalid = set(kwargs) - set(valid)
        if invalid:
            raise ValueError(
                f"Unknown property(ies) on {cls.__name__}: "
                f"{sorted(invalid)}. "
                f"Valid properties: {sorted(valid)}"
            )
        node = cls(**kwargs)
        return node.save()

    # ── UID computation ────────────────────────────────────────────────

    def _compute_qualified_name(self) -> str:
        """Compute the qualified name from the node's own data.

        Subclasses override this to derive ``qualified_name`` from
        relationships or other fields.  The base implementation returns
        ``self.name`` — suitable for top-level nodes (Component, etc.)
        where the qualified name is just the name.

        Called by :meth:`_save` when ``qualified_name`` is empty and
        the node type has a ``qualified_name`` property.

        Returns:
            The computed qualified name string.
        """
        return self.name or ""

    def _compute_uid(self) -> str:
        """Compute deterministic uid from identity fields without saving.

        Derives a SHA-1 hash from the node's ``source`` + ``_identity_fields``
        (e.g. ``source`` + ``qualified_name`` + normalised ``argsstring`` for
        functions/methods).  Source is the first identity part so that the
        same symbol in different projects gets different uids.

        Raises:
            ValueError: If ``source`` is empty (``source`` is a required
                field on all nodes) or if the primary identity field is
                empty, meaning a deterministic uid cannot be derived.

        Returns:
            The 40-character hex hash string.
        """
        from codegraph.uid import compute_uid, normalize_argsstring

        source = str(getattr(self, "source", "") or "")
        if not source:
            raise ValueError(
                f"Cannot compute uid for {type(self).__name__}: "
                f"'source' is empty (a required field)."
            )
        identity_fields = getattr(type(self), "_identity_fields", ())
        parts: list[str] = [source]
        for field in identity_fields:
            val = getattr(self, field, None)
            if val is None:
                val = ""
            val = str(val)
            if field == "argsstring":
                val = normalize_argsstring(val)
            parts.append(val)
        uid = compute_uid(*parts)
        if not uid:
            raise ValueError(
                f"Cannot compute uid for {type(self).__name__}: "
                f"primary identity field {identity_fields[0]!r} is empty."
            )
        return uid

    # ── Save (uid computation hook) ────────────────────────────────────

    def _save(self) -> "CodeGraphNode":
        """Save this node via the active backend.

        Delegates to ``get_backend().save(self)``, which handles uid
        computation, MERGE semantics, and property deflation.

        Returns:
            This node instance (after saving).

        Raises:
            ValueError: If ``source`` or identity fields are empty
                (a deterministic uid cannot be derived).
        """
        return get_backend().save(self)

    def _delete(self) -> "CodeGraphNode":
        """Delete this node via the active backend.

        Delegates to ``get_backend().delete(self)``, which handles
        recursive cascade (depth-first, leaves first), relationship
        cache cleanup, and final node removal.

        Must be called on a saved node (one with an
        ``element_id_property``).  After deletion the node is marked
        as deleted and should not be reused.

        Returns:
            This node instance (marked as deleted, no longer persisted).

        Raises:
            ValueError: If the node has not been saved yet
                (no ``element_id_property``).
        """
        if not hasattr(self, "element_id_property"):
            raise ValueError(
                f"Cannot delete unsaved {type(self).__name__} instance. "
                "Save the node first before calling delete()."
            )
        get_backend().delete(self)
        return self

    # ── Serialization ─────────────────────────────────────────────────────


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
        ``fields="all"`` to include every declared property.

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
        all_props = PropertyRegistry.values_of(self)
        if fields == "all":
            result = dict(sorted(all_props.items()))
        else:
            result = {k: all_props[k] for k in sorted(self._llm_fields) if k in all_props}
        # The node-kind discriminator normally lives under ``"type"`` — but
        # ParameterNode (and any future node) declares a real ``type``
        # property (the C++ type string).  Writing the discriminator over
        # it destroyed the value (and deserialize() skipped it).  When the
        # class declares its own ``type`` property, the discriminator is
        # emitted under ``"node_type"`` instead so the property survives
        # the round-trip.
        declared = PropertyRegistry.properties_of(type(self))
        discriminator = "node_type" if "type" in declared else "type"
        result[discriminator] = type(self).__name__

        # Always include the uid property (e.g. ``uid``) so that
        # roundtrip deserialization and edge target resolution work
        # regardless of the *fields* selection.  ``uid`` is a deterministic
        # hash — it is included for resolution, not for LLM readability.
        uid_prop = type(self)._uid_prop()
        uid_value = self._uid_value()
        if uid_prop and uid_value and uid_prop not in result:
            result[uid_prop] = uid_value

        if hasattr(self, "element_id_property"):
            all_edges = [
                {
                    "relation_type": e.relation_type,
                    "target_uid": e.target_uid,
                    "target_type": e.target_type,
                }
                for e in get_backend().get_all_edges_outgoing(self)
            ]
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
        children = get_backend().get_composed_children(self)
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
        type_name = _type_discriminator(data)
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

        declared = PropertyRegistry.properties_of(target_cls)
        # Skip the discriminator key(s) — but only the ones the target
        # class does NOT declare as a real property.  ParameterNode
        # declares ``type`` (the C++ type string), so for it the
        # discriminator is ``node_type`` and ``type`` must be kept.
        skip: set[str] = {"edges"}
        for key in ("type", "node_type"):
            if key not in declared:
                skip.add(key)
        # Backward compatibility: convert legacy "layer" field to "tags".
        # If data has "layer" but no "tags", promote the single layer value
        # into a tags list.
        compat_data = dict(data)
        if "layer" in compat_data and "tags" not in compat_data:
            compat_data["tags"] = [compat_data.pop("layer")]
        filtered = {k: v for k, v in compat_data.items()
                    if k not in skip and k in declared}
        node = target_cls(**filtered)

        # Compute deterministic uid from identity fields when not
        # explicitly provided in the input data.  This allows
        # LayerGraph.deserialize() to resolve edge targets by uid
        # without requiring the caller to pre-compute hashes.
        uid_prop = target_cls._uid_prop()
        if uid_prop and uid_prop not in data:
            try:
                computed = node._compute_uid()
                if computed:
                    setattr(node, uid_prop, computed)
            except ValueError:
                # source or identity fields are empty — leave the
                # UniqueIdProperty auto-generated value untouched.
                logging.warning(
                    "Cannot compute deterministic uid for %s: missing source "
                    "or identity fields. Falling back to auto-generated uid.",
                    target_cls.__name__,
                )

        return node

    @classmethod
    def serialize_relationships(cls) -> list[dict]:
        """Return relationship descriptors for this node type.

        Inspects ``Relationship`` descriptors statically — no database
        call needed.

        Returns:
            A list of dicts, each with keys: ``attr`` (Python attribute name),
            ``relation_type`` (Neo4j relationship label), ``direction``
            ("OUTGOING" or "INCOMING"), and ``target`` (dotted class path of
            the target node).
        """
        _, declared = PropertyRegistry.of(cls)
        rels: list[dict] = []
        for name, val in declared.items():
            if isinstance(val, CGRelationship):
                target = (
                    val.target_class
                    if isinstance(val.target_class, str)
                    else val.target_class.__name__
                )
                rels.append({
                    "attr": name,
                    "relation_type": val.relation_type,
                    "direction": val.direction,
                    "target": target,
                })
            else:
                # Neomodel RelationshipTo / RelationshipFrom
                d = val.definition
                direction = d.get("direction")
                dir_name = (
                    direction.name
                    if direction is not None and hasattr(direction, "name")
                    else "OUTGOING"
                )
                rels.append({
                    "attr": name,
                    "relation_type": d["relation_type"],
                    "direction": dir_name,
                    "target": d.get("model") or val._raw_class,
                })
        return rels

    @classmethod
    def _uid_prop(cls) -> str | None:
        """Return the name of this node type's unique identifier property, or None.

        Uses ``PropertyRegistry.unique_id_name()``.

        Returns:
            The property name string if a unique identifier exists, otherwise
            None.
        """
        return PropertyRegistry.unique_id_name(cls)

    def _uid_value(self) -> str | None:
        """Return the value of this instance's unique identifier, or None.

        Returns:
            The unique identifier value string if a UniqueId exists,
            otherwise None.
        """
        uid = type(self)._uid_prop()
        if uid is None:
            return None
        return getattr(self, uid, None)


    def update(self, **kwargs) -> "CodeGraphNode":
        """Update one or more property fields and persist the changes to Neo4j.

        Sets each keyword argument as an attribute on this node instance,
        then calls ``save()`` to write the changes to the database.

        Only declared properties are accepted — passing a key
        that is not a declared property raises ``ValueError``.

        Args:
            **kwargs: Property names and their new values.
                Each key must correspond to a declared property
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

        valid = PropertyRegistry.properties_of(type(self))
        invalid = set(kwargs) - set(valid)
        if invalid:
            raise ValueError(
                f"Unknown property(ies) on {type(self).__name__}: "
                f"{sorted(invalid)}. "
                f"Valid properties: {sorted(valid)}"
            )

        # Reject updates to identity fields (source, uid, and
        # _identity_fields like qualified_name / argsstring).  Changing
        # these would alter the deterministic uid, breaking idempotent
        # MERGE behaviour and orphaning existing relationships.
        uid_prop = type(self)._uid_prop()
        identity_fields = set(getattr(type(self), "_identity_fields", ()))
        immutable = {"source", *(identity_fields)}
        if uid_prop:
            immutable.add(uid_prop)
        changed_identity = set(kwargs) & immutable
        if changed_identity:
            raise ValueError(
                f"Cannot update identity field(s) on {type(self).__name__}: "
                f"{sorted(changed_identity)}. These fields determine the "
                f"node's uid and must not change after creation. "
                f"Create a new node instead."
            )

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.save()
        return self


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
        qname = self.qualified_name
        if not qname:
            # No qualified name available — use the
            # description to generate a stable fallback so the markdown
            # round-trips.
            desc = (
                getattr(self, "brief_description", "")
                or getattr(self, "description", "")
            )
            if desc:
                # Use first 40 chars of description as a stable slug
                import hashlib
                slug = hashlib.sha1(desc.encode()).hexdigest()[:8]
                qname = f"{keyword.lower()}_{slug}"
            else:
                qname = f"{keyword.lower()}_unnamed"
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


def _class_label(cls: type) -> str:
    """Return the primary Neo4j label for a node type (the class name)."""
    return cls.__name__


def _type_discriminator(data: dict) -> str | None:
    """Return the node-type discriminator from a serialized dict.

    Prefers ``node_type`` and falls back to the legacy ``type`` key.
    ``node_type`` is used by node classes that declare their own
    ``type`` property (currently only ``ParameterNode`` — the C++ type
    string), so the discriminator doesn't clobber the property.
    """
    value = data.get("node_type")
    if value is None:
        value = data.get("type")
    return value


class _BackendNodeSet:
    """Backend-delegating ``.nodes`` query shim for node types.

    Injected as ``cls.nodes`` on every concrete ``CodeGraphNode``
    subclass.  Provides the query surface used across the codebase —
    ``get``, ``get_or_none``, ``filter``, ``all`` — delegating to the
    active backend.  No storage-specific logic lives here.
    """

    def __init__(self, node_cls: type):
        self._cls = node_cls

    def get(self, **filters) -> "CodeGraphNode":
        """Get exactly one node matching *filters*.

        Raises ``self._cls.DoesNotExist`` if no node matches.
        """
        node = get_backend().get(self._cls, **filters)
        if node is None:
            raise self._cls.DoesNotExist(
                f"{self._cls.__name__} matching {filters} does not exist"
            )
        return node

    def get_or_none(self, **filters) -> "CodeGraphNode | None":
        """Get one node matching *filters*, or None."""
        return get_backend().get(self._cls, **filters)

    def filter(self, **filters) -> list["CodeGraphNode"]:
        """Return all nodes of this type matching *filters*."""
        return get_backend().find_all(self._cls, **filters)

    def all(self) -> list["CodeGraphNode"]:
        """Return all nodes of this type."""
        return get_backend().find_all(self._cls)

    def __repr__(self) -> str:
        return f"<_BackendNodeSet for {self._cls.__name__}>"


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
        "Component": "Component",
        "HLR": "HLR",
        "LLR": "LLR",
    }
    return defaults.get(node_type_name, "Class")
