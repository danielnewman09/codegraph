"""Namespace node model (:Namespace label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo,
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
    #  • COMPOSES  — NamespaceNode → ClassNode
    #    The namespace owns/contains these compounds.  Uses ClassNode as the
    #    representative target type (applies to all compound kinds).
    # --------------------------------------------------------------------------

    compounds = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "description"}