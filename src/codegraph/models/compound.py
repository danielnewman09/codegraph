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

    # --- File relationship ---
    defined_in = RelationshipTo('codegraph.models.file.FileNode', 'DEFINED_IN')

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
    depends_on = RelationshipTo('ClassNode', 'DEPENDS_ON')
    references = RelationshipTo('ClassNode', 'REFERENCES')
    realizes = RelationshipTo('InterfaceNode', 'REALIZES')
    template_params = RelationshipTo('ClassNode', 'TEMPLATE_PARAM')
    depended_on_by = RelationshipFrom('ClassNode', 'DEPENDS_ON')
    referred_by = RelationshipFrom('ClassNode', 'REFERENCES')


# --- Stubs for Tasks 3-5 (will be fleshed out with their own fields) ---

class InterfaceNode(_CompoundMixin):
    """Interface or abstract base — Neo4j label ``:Interface``."""

    kind = StringProperty(default="interface")
    module = StringProperty(default="")
    is_abstract = BooleanProperty(default=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships — methods only, no attributes
    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
    generalizes = RelationshipTo('InterfaceNode', 'GENERALIZES')
    dependencies = RelationshipTo('ClassNode', 'DEPENDS_ON')


class EnumNode(_CompoundMixin):
    """Enum type — Neo4j label ``:Enum``."""

    kind = StringProperty(default="enum")
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships
    values = RelationshipTo('codegraph.models.member.EnumValueNode', 'COMPOSES')


class UnionNode(_CompoundMixin):
    """C/C++ union type — Neo4j label ``:Union``."""

    kind = StringProperty(default="union")
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}


class ModuleNode(_CompoundMixin):
    """Module or logical namespace — Neo4j label ``:Module``.

    Not a direct member of ClassDiagram; module names are derived
    from compound qualified names during ``from_layer()``.
    """

    kind = StringProperty(default="module")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}


# ---------------------------------------------------------------------------
# Old-label compatibility — write to :Compound/:Member/:Namespace labels
# until schema migration renames them to the atomized labels.
# Remove these overrides after the Neo4j schema migration.
# ---------------------------------------------------------------------------
ClassNode.__label__ = "Compound"
InterfaceNode.__label__ = "Compound"
EnumNode.__label__ = "Compound"
UnionNode.__label__ = "Compound"
ModuleNode.__label__ = "Compound"
