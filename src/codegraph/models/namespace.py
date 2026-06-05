"""Namespace node model (:Namespace label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class NamespaceNode(StructuredNode, CodeGraphNode):
    """A namespace entity — namespace, package, or module.

    Attributes:
        qualified_name: Unique identifier for the namespace.
        kind: Namespace kind (defaults to "namespace").
        layer: Origin layer (defaults to "design").
        component_id: Component identifier for grouping.
        description: Human-readable description of the namespace.
    """

    qualified_name = UniqueIdProperty()
    kind = StringProperty(default="namespace")
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    description = StringProperty(default="")

    # --- NamespaceNode relationships ----------------------------------------
    #
    #  • COMPOSES (outgoing)  — NamespaceNode → ClassNode | InterfaceNode |
    #    EnumNode | UnionNode | ModuleNode | FunctionNode | NamespaceNode
    #    The namespace owns/contains these entities.  Each target type gets
    #    its own descriptor so neomodel can dispatch correctly.
    #
    #  • COMPOSES (incoming)  — NamespaceNode ← NamespaceNode
    #    The parent namespace owns/contains this namespace.
    #    Traversed via ``parent_namespace``.
    #
    #  Self-referential COMPOSES (namespaces → namespaces) supports
    #  nested namespaces (e.g. outer::inner).
    # --------------------------------------------------------------------------

    classes     = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')
    interfaces  = RelationshipTo('codegraph.models.compound.InterfaceNode', 'COMPOSES')
    enums       = RelationshipTo('codegraph.models.compound.EnumNode', 'COMPOSES')
    unions      = RelationshipTo('codegraph.models.compound.UnionNode', 'COMPOSES')
    modules     = RelationshipTo('codegraph.models.compound.ModuleNode', 'COMPOSES')
    functions   = RelationshipTo('codegraph.models.member.FunctionNode', 'COMPOSES')
    namespaces  = RelationshipTo('NamespaceNode', 'COMPOSES')

    # Incoming composition (parent namespace for nesting)
    parent_namespace = RelationshipFrom('NamespaceNode', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "description"}