"""Member node models — MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode.

Each member kind gets its own neomodel class and Neo4j label. Common fields
are shared via a ``_MemberMixin`` abstract base.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipFrom,
)

from codegraph.models.tags import LlmSerializable


class _MemberMixin(StructuredNode, LlmSerializable):
    """Common fields and serialization for all member node types."""

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    compound_refid = StringProperty(default="")
    source = StringProperty(default="")

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Serialization ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature",
    }

    def serialize(self) -> dict:
        props = dict(self.__properties__)
        return {k: props[k] for k in self._llm_fields if k in props}

    @classmethod
    def deserialize(cls, data: dict) -> "_MemberMixin":
        return cls(**{k: v for k, v in data.items()
                      if k in cls.defined_properties()})


class MethodNode(_MemberMixin):
    """Function or method — Neo4j label ``:Method``."""

    kind = StringProperty(default="method")
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)
    is_constexpr = BooleanProperty(default=False)
    is_virtual = BooleanProperty(default=False)
    is_inline = BooleanProperty(default=False)
    is_explicit = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring",
    }

    # Relationships — a method can be composed from a ClassNode or InterfaceNode
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')
    parent_interface = RelationshipFrom('codegraph.models.compound.InterfaceNode', 'COMPOSES')


class AttributeNode(_MemberMixin):
    """Member variable / data attribute — Neo4j label ``:Attribute``."""

    kind = StringProperty(default="attribute")
    type_signature = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature",
    }

    # Relationships — an attribute is owned by a ClassNode
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')


class EnumValueNode(_MemberMixin):
    """Enum constant value — Neo4j label ``:EnumValue``."""

    kind = StringProperty(default="enumvalue")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships
    parent_enum = RelationshipFrom('codegraph.models.compound.EnumNode', 'COMPOSES')


class FunctionNode(_MemberMixin):
    """Free function (not a method) — Neo4j label ``:Function``."""

    kind = StringProperty(default="function")
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring",
    }


class DefineNode(_MemberMixin):
    """Preprocessor macro / define — Neo4j label ``:Define``."""

    kind = StringProperty(default="define")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}
