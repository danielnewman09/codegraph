"""Compound node models — ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode.

Each compound kind gets its own neomodel class, Neo4j label, and
kind-specific fields. Common fields are shared via ``_CompoundMixin``.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import LlmSerializable


class _CompoundMixin(StructuredNode, LlmSerializable):
    """Common fields and serialization for all compound node types."""

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    source = StringProperty(default="")
    source_type = StringProperty(default="")

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "brief_description"}

    def serialize(self) -> dict:
        props = dict(self.__properties__)
        return {k: props[k] for k in self._llm_fields if k in props}

    @classmethod
    def deserialize(cls, data: dict) -> "_CompoundMixin":
        return cls(**{k: v for k, v in data.items()
                      if k in cls.defined_properties()})


class ClassNode(_CompoundMixin):
    """Class or struct — Neo4j label ``:Class``."""

    kind = StringProperty(default="class")
    module = StringProperty(default="")
    base_classes = ArrayProperty(StringProperty(), default=[])
    is_final = BooleanProperty(default=False)
    is_abstract = BooleanProperty(default=False)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "base_classes"}

    # Relationships
    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
    attributes = RelationshipTo('codegraph.models.member.AttributeNode', 'COMPOSES')
    base = RelationshipTo('ClassNode', 'GENERALIZES')
    derived = RelationshipFrom('ClassNode', 'GENERALIZES')


# --- Stubs for Tasks 3-5 (will be fleshed out with their own fields) ---

class InterfaceNode(_CompoundMixin):
    """Interface stub — full implementation in Task 3."""
    kind = StringProperty(default="interface")


class EnumNode(_CompoundMixin):
    """Enum stub — full implementation in Task 4."""
    kind = StringProperty(default="enum")


class UnionNode(_CompoundMixin):
    """Union stub — full implementation in Task 5."""
    kind = StringProperty(default="union")


class ModuleNode(_CompoundMixin):
    """Module stub — full implementation in Task 5."""
    kind = StringProperty(default="module")
