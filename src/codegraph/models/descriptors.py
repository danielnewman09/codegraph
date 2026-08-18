"""Backend-agnostic property and relationship descriptors.

Replaces neomodel's ``StringProperty``,
``RelationshipTo``, ``RelationshipFrom``, and ``defined_properties()``
with pure-Python equivalents.  Storage backends (Neo4j, in-memory,
SQLite) use these descriptors for introspection; I/O stays in the
backend implementations.

Usage::

    from codegraph.models.descriptors import Property, Relationship

    class MyNode(CodeGraphNode):
        qualified_name = Property(str, index=True)
        methods = Relationship("COMPOSES", direction="OUTGOING",
                               target_class="MethodNode")

Design notes
~~~~~~~~~~~~

- ``Property`` is a standard Python data descriptor (``__get__`` /
  ``__set__`` / ``__delete__``) that stores values in the instance's
  ``_props`` dict.  This mirrors neomodel's instance-level storage
  without the metaclass magic.

- ``Relationship`` is a non-data descriptor (no ``__set__``).  Accessing
  it on an instance raises ``AttributeError`` with a helpful message —
  relationships are traversed through the backend, not through
  attribute access.  On the class, the descriptor itself is returned
  for introspection.

- ``PropertyRegistry`` replaces ``cls.defined_properties()``.  It walks
  the MRO and collects all ``Property`` and ``Relationship``
  descriptors, resolving ``__name__``-level overrides correctly (the
  first occurrence in MRO — the most-derived class — wins).
"""

from __future__ import annotations

import functools
from datetime import datetime
from typing import Any


# ══════════════════════════════════════════════════════════════════════════
# Property descriptor
# ══════════════════════════════════════════════════════════════════════════


class Property:
    """Backend-agnostic property descriptor.

    Stores values in the instance's ``_props`` dict.  No I/O
    is performed — read/write/delete is pure Python.

    Attributes:
        name: The attribute name this descriptor is assigned to
            (set via ``__set_name__``).
        python_type: The expected Python type (``str``, ``int``, ``float``,
            ``bool``, ``list``, ``datetime``).  Used by backends for
            validation and serialization.
        default: Default value when the property is not set on an
            instance.  ``None`` means no default.
        required: If ``True``, the backend should reject a node that is
            missing this property.
        index: If ``True``, the backend should create an index on this
            property.  Only meaningful for database backends.
        help_text: Human-readable description of the property.
    """

    def __init__(
        self,
        python_type: type = str,
        *,
        default: Any = None,
        required: bool = False,
        index: bool = False,
        help_text: str = "",
    ) -> None:
        self.name: str = ""
        self.python_type: type = python_type
        self.default: Any = default
        self.required: bool = required
        self.index: bool = index
        self.help_text: str = help_text

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        props = obj.__dict__.setdefault("_props", {})
        if self.name in props:
            return props[self.name]
        return self.default() if callable(self.default) else self.default

    def __set__(self, obj: Any, value: Any) -> None:
        obj.__dict__.setdefault("_props", {})[self.name] = value

    def __delete__(self, obj: Any) -> None:
        props = obj.__dict__.get("_props")
        if props is not None:
            props.pop(self.name, None)

    def __repr__(self) -> str:
        return (
            f"Property(name={self.name!r}, type={self.python_type.__name__}, "
            f"required={self.required}, index={self.index})"
        )


# ══════════════════════════════════════════════════════════════════════════
# Specialized property types
# ══════════════════════════════════════════════════════════════════════════


class DateTimeProperty(Property):
    """Property that holds a ``datetime`` value.

    The default is ``None`` (not set).  When serialized to a backend,
    the value should be converted to a Unix timestamp (float).  When
    deserialized from a backend, the value is stored as a ``datetime``.
    """

    def __init__(
        self,
        *,
        default: Any = None,
        required: bool = False,
        index: bool = False,
        help_text: str = "",
    ) -> None:
        super().__init__(
            datetime,
            default=default,
            required=required,
            index=index,
            help_text=help_text,
        )


# ══════════════════════════════════════════════════════════════════════════
# Relationship descriptor
# ══════════════════════════════════════════════════════════════════════════


class Relationship:
    """Backend-agnostic relationship descriptor.

    Declares that a node type can participate in a relationship of a
    given type and direction with nodes of a given target type.

    Attributes:
        name: The attribute name this descriptor is assigned to
            (set via ``__set_name__``).
        relation_type: The Neo4j relationship label / edge type
            (e.g. ``"COMPOSES"``, ``"INHERITS_FROM"``, ``"VERIFIES"``).
        direction: ``"OUTGOING"`` or ``"INCOMING"``.
        target_class: The class or fully-qualified class name of the
            target node type.  String values (e.g. ``"MethodNode"`` or
            ``"codegraph.models.member.MethodNode"``) are resolved
            lazily by the backend.
    """

    def __init__(
        self,
        relation_type: str,
        *,
        direction: str = "OUTGOING",
        target_class: str | type,
    ) -> None:
        if direction not in ("OUTGOING", "INCOMING"):
            raise ValueError(
                f"direction must be 'OUTGOING' or 'INCOMING', got {direction!r}"
            )
        self.name: str = ""
        self.relation_type: str = relation_type
        self.direction: str = direction
        self.target_class: str | type = target_class

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @property
    def definition(self) -> dict:
        """Neomodel-compatible ``definition`` dict.

        Legacy callers read ``descriptor.definition["relation_type"]``.
        Returns the same keys so those call sites (and tests) keep
        working unchanged.
        """
        return {
            "node_class": None,
            "relation_type": self.relation_type,
            "direction": self.direction,
            "model": (
                self.target_class
                if isinstance(self.target_class, str)
                else self.target_class.__name__
            ),
        }

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return RelationshipManager(obj, self)

    def __repr__(self) -> str:
        target = (
            self.target_class.__name__
            if isinstance(self.target_class, type)
            else self.target_class
        )
        return (
            f"Relationship(name={self.name!r}, "
            f"type={self.relation_type!r}, "
            f"direction={self.direction!r}, "
            f"target={target!r})"
        )


class RelationshipManager:
    """Backend-delegating relationship manager.

    Returned when a ``Relationship`` descriptor is accessed on an
    instance.  Provides the neomodel-compatible surface used across
    the codebase — ``.all()``, ``.get()``, ``.get_or_none()``,
    ``.single()``, ``.connect()``, ``.disconnect()`` — delegating all
    I/O to the active backend.  No storage logic lives here.
    """

    def __init__(self, source: Any, descriptor: "Relationship"):
        self._source = source
        self._rel = descriptor

    # ── Traversal ──────────────────────────────────────────────────

    def _resolved_target_class(self) -> type | None:
        """Resolve the declared ``target_class`` to a registered type."""
        tc = self._rel.target_class
        if isinstance(tc, type):
            return tc
        leaf = tc.rsplit(".", 1)[-1]
        from codegraph.models.tags import CodeGraphNode

        return CodeGraphNode._registry.get(leaf)

    def _target_matches(self, edge) -> bool:
        """True when the edge's connected node matches the declared target class.

        Restores neomodel's ``RelationshipTo(Class, rel_type)`` contract,
        which the pure-Python descriptor migration dropped: traversal must
        be filtered to the declared target type, otherwise e.g.
        ``NamespaceNode.classes`` (COMPOSES -> ClassNode) also returns
        interfaces, enums, functions, ... that share the edge type.
        """
        target_cls = self._resolved_target_class()
        if target_cls is None:
            return True  # unresolvable declaration — don't over-filter
        if edge.target_type == target_cls.__name__:
            return True
        from codegraph.models.tags import CodeGraphNode

        candidate = CodeGraphNode._registry.get(edge.target_type)
        return candidate is not None and issubclass(candidate, target_cls)

    def all(self) -> list[Any]:
        """Return all connected target nodes matching the declared class."""
        from codegraph.backends import get_backend

        backend = get_backend()
        edges = backend.get_all_edges(self._source)
        targets: list[Any] = []
        for edge in edges:
            if edge.relation_type != self._rel.relation_type:
                continue
            if self._rel.direction == "OUTGOING" and not edge.is_outgoing:
                continue
            if self._rel.direction == "INCOMING" and edge.is_outgoing:
                continue
            if not self._target_matches(edge):
                continue
            target = backend.graph.find_by_key(edge.target_key)
            if target is not None:
                targets.append(target)
        return targets

    def get(self, **filters) -> Any:
        """Return the single matching target; raise if none."""
        matches = self._filter_targets(filters)
        if not matches:
            raise ValueError(
                f"No '{self._rel.relation_type}' target of "
                f"{type(self._source).__name__} matching {filters}"
            )
        return matches[0]

    def get_or_none(self, **filters) -> Any | None:
        """Return the first matching target, or None."""
        matches = self._filter_targets(filters)
        return matches[0] if matches else None

    def single(self) -> Any | None:
        """Return the first target, or None."""
        targets = self.all()
        return targets[0] if targets else None

    # ── Mutation ───────────────────────────────────────────────────

    def connect(self, target: Any) -> None:
        """Create the relationship to *target*."""
        from codegraph.backends import get_backend

        get_backend().connect(self._source, self._rel.relation_type, target)

    def disconnect(self, target: Any) -> None:
        """Remove the relationship to *target*."""
        from codegraph.backends import get_backend

        get_backend().disconnect(self._source, self._rel.relation_type, target)

    # ── Protocol support ───────────────────────────────────────────

    def __iter__(self):
        return iter(self.all())

    def __len__(self) -> int:
        return len(self.all())

    def __repr__(self) -> str:
        return (
            f"<RelationshipManager {type(self._source).__name__}."
            f"{self._rel.name} -> {self._rel.relation_type}>"
        )

    def _filter_targets(self, filters: dict) -> list[Any]:
        targets = self.all()
        return [
            t for t in targets
            if all(getattr(t, key, None) == value for key, value in filters.items())
        ]


# ══════════════════════════════════════════════════════════════════════════
# Property registry — replaces cls.defined_properties()
# ══════════════════════════════════════════════════════════════════════════


class PropertyRegistry:
    """Collects ``Property`` and ``Relationship`` descriptors from a class MRO.

    Replaces neomodel's ``cls.defined_properties()`` and
    ``self.__properties__`` with a pure-Python implementation that walks
    the class hierarchy and collects descriptors.

    Usage::

        props = PropertyRegistry.properties_of(MyNode)      # → dict[str, Property]
        rels = PropertyRegistry.relationships_of(MyNode)    # → dict[str, Relationship]
        both = PropertyRegistry.of(MyNode)                  # → (props, rels)

        # Get current values from a live instance
        values = PropertyRegistry.values_of(node)           # → dict[str, Any]
    """

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def of(
        klass: type,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(properties, relationships)`` for a class.

        Walks the MRO in reverse (base classes first), collecting
        Property and Relationship descriptors.  The most-derived
        class's descriptor wins for a given name.

        Memoized (``lru_cache``): a class's descriptor set is static
        after module import, and this is called per-node on every
        save/serialize path — e.g. ``bulk_save`` calls it ~60k times
        for a 50k-node ingest.  The cached dicts are shared; callers
        must treat them as read-only (none currently mutate them).
        """
        props: dict[str, Any] = {}
        rels: dict[str, Any] = {}

        for base in reversed(klass.__mro__):
            for attr_name, value in vars(base).items():
                if isinstance(value, Property):
                    # Our Property / DateTimeProperty
                    props[attr_name] = value
                elif isinstance(value, Relationship):
                    # Our Relationship
                    rels[attr_name] = value

        return props, rels

    @classmethod
    def properties_of(cls, klass: type) -> dict[str, Property]:
        """Return only the Property descriptors for a class."""
        props, _ = cls.of(klass)
        return props

    @classmethod
    def relationships_of(cls, klass: type) -> dict[str, Relationship]:
        """Return only the Relationship descriptors for a class."""
        _, rels = cls.of(klass)
        return rels

    @classmethod
    def values_of(cls, obj: Any) -> dict[str, Any]:
        """Return the current property values from a live instance.

        Reads each declared Property via ``getattr(obj, name)``, which
        invokes the descriptor's ``__get__`` (our Property or neomodel's).
        Skips relationship descriptors.
        """
        props, _ = cls.of(type(obj))
        result: dict[str, Any] = {}
        for name in props:
            try:
                result[name] = getattr(obj, name)
            except Exception:
                result[name] = None
        return result

    @classmethod
    def is_required_string(cls, prop: Any) -> bool:
        """Check whether *prop* is a required string-typed property."""
        return isinstance(prop, Property) and prop.python_type is str and bool(
            prop.required
        )

    @classmethod
    def has_property(cls, klass: type, name: str) -> bool:
        """Check whether *klass* (or any of its bases) declares *name*."""
        return name in cls.properties_of(klass)



# ══════════════════════════════════════════════════════════════════════════
# Relationship introspection — replaces find_relationship_manager
# ══════════════════════════════════════════════════════════════════════════


def _relationship_matches(
    rel: Any,
    relation_type: str,
    target_type: type | str,
) -> bool:
    """Check whether a relationship descriptor matches type + target.

    Class targets match by equality or subclass — e.g. a descriptor
    targeting ``CompoundNode`` matches a ``ClassNode`` target.
    """
    target_name = (
        target_type if isinstance(target_type, str) else target_type.__name__
    )

    if not isinstance(rel, Relationship):
        return False

    if rel.relation_type != relation_type:
        return False
    tc = rel.target_class
    if isinstance(tc, str):
        if tc == target_name or tc.endswith(f".{target_name}"):
            return True
        # String class targets also match by subclass — e.g. a
        # descriptor targeting ``"CompoundNode"`` matches a
        # ``ClassNode`` target (ClassNode subclasses CompoundNode).
        # Match on the simple name against the target's MRO so no
        # import is needed to resolve the dotted string.
        if isinstance(target_type, type):
            short = tc.split(".")[-1]
            return any(base.__name__ == short for base in target_type.__mro__)
        return False
    if isinstance(tc, type) and isinstance(target_type, type):
        return (
            tc is target_type
            or issubclass(target_type, tc)
        )
    return tc is target_type


def find_relationship_descriptor(
    source_type: type,
    relation_type: str,
    target_type: type | str,
) -> Any | None:
    """Find a relationship descriptor matching the given parameters.

    Searches the source type's MRO for a descriptor with the given
    ``relation_type`` whose ``target_class`` matches the given target
    type (by class equality, name resolution, or subclass — e.g. a
    descriptor targeting ``CompoundNode`` matches a ``ClassNode``).

    Works with the new ``Relationship`` descriptors.

    Args:
        source_type: The node type that owns the relationship.
        relation_type: Relationship label (e.g. ``"COMPOSES"``).
        target_type: The target node type (class or class name string).

    Returns:
        The matching descriptor, or ``None`` if no match is found.
    """
    _, rels = PropertyRegistry.of(source_type)
    for rel in rels.values():
        if _relationship_matches(rel, relation_type, target_type):
            return rel
    return None


def find_relationship_attr(
    source_type: type,
    relation_type: str,
    target_type: type | str,
) -> str | None:
    """Return the attribute name of the matching relationship descriptor.

    Like :func:`find_relationship_descriptor` but returns the attribute
    name (e.g. ``"methods"``) instead of the descriptor instance.
    Returns ``None`` if no descriptor matches.
    """
    _, rels = PropertyRegistry.of(source_type)
    for name, rel in rels.items():
        if _relationship_matches(rel, relation_type, target_type):
            return name
    return None


# ══════════════════════════════════════════════════════════════════════════
# Relationship introspection — replaces find_relationship_manager
# ══════════════════════════════════════════════════════════════════════════


def _relationship_matches(
    rel: Any,
    relation_type: str,
    target_type: type | str,
) -> bool:
    """Check whether a relationship descriptor matches type + target.

    Class targets match by equality or subclass — e.g. a descriptor
    targeting ``CompoundNode`` matches a ``ClassNode`` target.
    """
    target_name = (
        target_type if isinstance(target_type, str) else target_type.__name__
    )

    if not isinstance(rel, Relationship):
        return False

    if rel.relation_type != relation_type:
        return False
    tc = rel.target_class
    if isinstance(tc, str):
        if tc == target_name or tc.endswith(f".{target_name}"):
            return True
        # String class targets also match by subclass — e.g. a
        # descriptor targeting ``"CompoundNode"`` matches a
        # ``ClassNode`` target (ClassNode subclasses CompoundNode).
        # Match on the simple name against the target's MRO so no
        # import is needed to resolve the dotted string.
        if isinstance(target_type, type):
            short = tc.split(".")[-1]
            return any(base.__name__ == short for base in target_type.__mro__)
        return False
    if isinstance(tc, type) and isinstance(target_type, type):
        return (
            tc is target_type
            or issubclass(target_type, tc)
        )
    return tc is target_type


def find_relationship_descriptor(
    source_type: type,
    relation_type: str,
    target_type: type | str,
) -> Any | None:
    """Find a relationship descriptor matching the given parameters.

    Searches the source type's MRO for a descriptor with the given
    ``relation_type`` whose ``target_class`` matches the given target
    type (by class equality, name resolution, or subclass — e.g. a
    descriptor targeting ``CompoundNode`` matches a ``ClassNode``).

    Works with the new ``Relationship`` descriptors.

    Args:
        source_type: The node type that owns the relationship.
        relation_type: Relationship label (e.g. ``"COMPOSES"``).
        target_type: The target node type (class or class name string).

    Returns:
        The matching descriptor, or ``None`` if no match is found.
    """
    _, rels = PropertyRegistry.of(source_type)
    for rel in rels.values():
        if _relationship_matches(rel, relation_type, target_type):
            return rel
    return None


def find_relationship_attr(
    source_type: type,
    relation_type: str,
    target_type: type | str,
) -> str | None:
    """Return the attribute name of the matching relationship descriptor.

    Like :func:`find_relationship_descriptor` but returns the attribute
    name (e.g. ``"methods"``) instead of the descriptor instance.
    Returns ``None`` if no descriptor matches.
    """
    _, rels = PropertyRegistry.of(source_type)
    for name, rel in rels.items():
        if _relationship_matches(rel, relation_type, target_type):
            return name
    return None


# ══════════════════════════════════════════════════════════════════════════
# UniqueId property name helper
# ══════════════════════════════════════════════════════════════════════════


def uid_prop_name(klass: type) -> str | None:
    """Return the name of the ``UniqueId`` property on *klass*."""
    return PropertyRegistry.unique_id_name(klass)
