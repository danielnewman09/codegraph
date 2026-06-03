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

    Provides:
    - ``source`` — project provenance field (inherited by every node)
    - ``serialize()`` – property fields, type, and edges as a single dict
    - ``deserialize()`` – instantiate from dict (ignores ``edges`` and ``type``)
    - ``from_json()`` – factory: looks up the correct subclass by ``type``
    - ``find_relationship_manager()`` – find the neomodel relationship manager
      matching a relation type and target class
    - ``fetch_by_layer()`` / ``fetch_all_by_layer()`` – layer-aware Neo4j queries
    - ``serialize_relationships()`` – static schema of relationship descriptors
    - ``serialize_edges()`` – live edges from Neo4j
    - ``_uid_prop()`` / ``_uid_value()`` – unique identifier accessors

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

        Returns the relationship manager attribute (e.g. ``source.methods``).
        Raises ``ValueError`` if no matching manager is found.
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
        """
        if "layer" not in cls.defined_properties():
            return []
        return list(cls.nodes.filter(layer=layer))

    @classmethod
    def fetch_all_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
        """Fetch all nodes across all registered types matching *layer*.

        Iterates :pyattr:`_registry`, calling :pyfunc:`fetch_by_layer` on each
        concrete subclass. Returns a flat list.
        """
        result: list[CodeGraphNode] = []
        for node_cls in cls._registry.values():
            result.extend(node_cls.fetch_by_layer(layer))
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

    def serialize(self) -> dict:
        """Return the full LLM-facing representation of this node.

        Includes a ``type`` discriminator, property fields (filtered by
        ``_llm_fields``), and, if the node has been saved to Neo4j, a list
        of relationship edges from ``serialize_edges()``.

        For unsaved nodes the ``edges`` key is an empty list.
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
        """
        skip = {"edges", "type"}
        filtered = {k: v for k, v in data.items()
                    if k not in skip and k in cls.defined_properties()}
        return cls(**filtered)

    @classmethod
    def from_json(cls, data: dict) -> "CodeGraphNode":
        """Instantiate the correct subclass from a serialized dict.

        Reads the ``type`` key to dispatch to the registered subclass,
        then calls ``deserialize()`` on that class.

        Raises ``KeyError`` if the ``type`` is not in the registry.
        """
        type_name = data.get("type")
        if type_name is None:
            raise ValueError("Serialized data is missing the 'type' discriminator")
        if type_name not in cls._registry:
            raise KeyError(
                f"Unknown node type '{type_name}'. "
                f"Registered types: {sorted(cls._registry.keys())}"
            )
        return cls._registry[type_name].deserialize(data)

    @classmethod
    def serialize_relationships(cls) -> list[dict]:
        """Return relationship descriptors for this node type.

        Inspects ``RelationshipTo`` / ``RelationshipFrom`` descriptors
        statically — no database call needed.

        Returns a list of dicts, each with keys:
            attr           – Python attribute name on the node class
            relation_type  – Neo4j relationship label (e.g. "DEFINED_IN")
            direction      – "OUTGOING" or "INCOMING"
            target         – Dotted class path of the target node
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
        """Return the name of this node type's UniqueIdProperty, or None."""
        from neomodel import UniqueIdProperty

        for name, prop in cls.defined_properties().items():
            if isinstance(prop, UniqueIdProperty):
                return name
        return None

    def _uid_value(self) -> str | None:
        """Return the value of this instance's unique identifier, or None."""
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

        Returns a list of dicts, each with keys:
            relation_type  – Neo4j relationship label (e.g. "DEFINED_IN")
            target_uid     – the connected node's unique id value
            target_type    – the connected node's class name
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