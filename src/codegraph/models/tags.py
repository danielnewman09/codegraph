"""CodeGraphNode — base class for all codegraph neomodel nodes.

Provides shared fields (``source``), serialization (``serialize()``,
``deserialize()``, ``from_json()``), relationship introspection, and a
registry for type-dispatched deserialization.

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

    Attributes:
        name: Short name of the node (e.g. 'Widget', 'draw', 'widget.h').
        refid: External reference ID from the source system (e.g. Doxygen refid).
            FileNode overrides this as UniqueIdProperty.
        source: Name of the project this node belongs to (e.g. 'codegraph', 'llvm').

    Subclasses must:
    - Declare ``_llm_fields`` as a class-level ``set[str]`` of field names
    """

    _llm_fields: set[str] = set()

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

    # ── Layer-aware queries ───────────────────────────────────────────────

    @classmethod
    def fetch_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
        """Fetch all persisted instances of this type matching *layer*.

        Uses neomodel's ``.nodes.filter(layer=layer)``. Returns an empty
        list for types that don't have a ``layer`` property
        (e.g. FileNode, ParameterNode).

        Args:
            layer: The layer to filter by (e.g. "design", "as-built",
                "dependency").

        Returns:
            A list of CodeGraphNode instances matching the given layer.
        """
        if "layer" not in cls.defined_properties():
            return []
        return list(cls.nodes.filter(layer=layer))

    @classmethod
    def fetch_all_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *layer*.

        Iterates ``_registry``, calling ``fetch_by_layer`` on each
        concrete subclass. Returns a flat list.

        Args:
            layer: The layer to filter by (e.g. "design", "as-built",
                "dependency").

        Returns:
            A flat list of CodeGraphNode instances across all registered
            types matching the given layer.
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            result.extend(node_cls.fetch_by_layer(layer))
        return result

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
    def fetch_all_by_kind(cls, kind: str, layer: str | None = None) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *kind*.

        Optionally filter by *layer* as well. Only types that have a ``kind``
        property are queried. Returns a flat list.

        Args:
            kind: The node kind to filter by (e.g. "class", "method").
            layer: Optional layer to additionally filter by. When provided,
                only nodes with both matching kind and layer are returned.

        Returns:
            A flat list of CodeGraphNode instances matching the given kind
            (and optionally layer).
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            props = node_cls.defined_properties()
            if "kind" not in props:
                continue
            if layer is not None and "layer" not in props:
                continue
            filters: dict = {"kind": kind}
            if layer is not None and "layer" in props:
                filters["layer"] = layer
            result.extend(node_cls.nodes.filter(**filters))
        return result

    # ── Registry ──────────────────────────────────────────────────────────
    # Every concrete CodeGraphNode subclass registers itself here so that
    # ``from_json()`` can look up the right class by the ``type`` discriminator.
    _registry: dict[str, type["CodeGraphNode"]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Only register concrete classes that have their own ``_llm_fields``.
        # Mixins like _CompoundMixin / _MemberMixin set _llm_fields but are
        # still abstract (they inherit from StructuredNode directly). We skip
        # any class whose name starts with an underscore by convention.
        if not cls.__name__.startswith("_") and cls._llm_fields:
            CodeGraphNode._registry[cls.__name__] = cls

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self, fields: str = "all") -> dict:
        """Return a dict representation of this node.

        Produces a full-fidelity or LLM-trimmed dict suitable for
        round-tripping through :meth:`from_dict` or for transport to
        external services.

        Args:
            fields: "all" to include every defined property, "llm" to
                include only the properties listed in ``_llm_fields``.

        Returns:
            A dict with ``type`` discriminator, the node's unique
            identifier property value (if it has one), and the selected
            property fields.  Does NOT include ``edges`` — that is
            the domain of :class:`CompositeEntry` and
            :class:`~codegraph.graph.LayerGraph`.
        """
        props = dict(self.__properties__)
        if fields == "llm":
            result = {k: props[k] for k in self._llm_fields if k in props}
        else:  # fields == "all"
            result = dict(props)

        # Always include the type discriminator
        result["type"] = type(self).__name__

        # Always include uid_prop for round-trip resolution, even in llm mode.
        # FileNode uses refid (not in _llm_fields), so to_dict(fields="llm")
        # would omit it without this explicit inclusion.
        uid_prop = type(self)._uid_prop()
        if uid_prop and uid_prop not in result:
            uid_value = getattr(self, uid_prop, None)
            if uid_value is not None:
                result[uid_prop] = uid_value

        return result

    def serialize(self) -> dict:
        """Return the full LLM-facing representation of this node.

        Includes a ``type`` discriminator, property fields (filtered by
        ``_llm_fields``), and, if the node has been saved to Neo4j, a list
        of relationship edges from ``serialize_edges()``.

        For unsaved nodes the ``edges`` key is an empty list.

        Returns:
            A dict with ``type``, property fields, and ``edges`` keys.
        """
        props = dict(self.__properties__)
        result = {k: props[k] for k in self._llm_fields if k in props}
        result["type"] = type(self).__name__
        if hasattr(self, "element_id_property"):
            result["edges"] = self.serialize_edges()
        else:
            result["edges"] = []
        return result

    @classmethod
    def deserialize(cls, data: dict) -> "CodeGraphNode":
        """Instantiate a node of *this* class from LLM-provided dict data.

        Ignores the ``edges`` and ``type`` keys — edges are resolved
        separately via Neo4j after nodes are saved.

        Args:
            data: A dict of property names to values, as produced by an LLM
            or deserialized from JSON. Keys ``edges`` and ``type`` are ignored.

        Returns:
            A new instance of this CodeGraphNode subclass.
        """
        skip = {"edges", "type"}
        filtered = {k: v for k, v in data.items()
                    if k not in skip and k in cls.defined_properties()}
        return cls(**filtered)

    @classmethod
    def from_dict(cls, data: dict) -> "CodeGraphNode":
        """Instantiate the correct subclass from a dict.

        Reads the ``type`` key to dispatch to the registered subclass,
        then calls ``deserialize()`` on that class.

        Args:
            data: A dict with a ``type`` discriminator key and property
                fields as produced by :meth:`to_dict`.

        Returns:
            A new instance of the appropriate CodeGraphNode subclass.

        Raises:
            ValueError: If the ``type`` key is missing from data.
            KeyError: If the ``type`` is not in the registry.
        """
        type_name = data.get("type")
        if type_name is None:
            raise ValueError("Dict data is missing the 'type' discriminator")
        if type_name not in cls._registry:
            raise KeyError(
                f"Unknown node type '{type_name}'. "
                f"Registered types: {sorted(cls._registry.keys())}"
            )
        return cls._registry[type_name].deserialize(data)

    @classmethod
    def from_json(cls, data: dict) -> "CodeGraphNode":
        """Instantiate the correct subclass from a serialized dict.

        Alias for :meth:`from_dict`. Reads the ``type`` key to dispatch
        to the registered subclass.

        Args:
            data: A serialized dict with a ``type`` discriminator key.

        Returns:
            A new instance of the appropriate CodeGraphNode subclass.

        Raises:
            ValueError: If the ``type`` key is missing from data.
            KeyError: If the ``type`` is not in the registry.
        """
        return cls.from_dict(data)

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