"""Namespace node model (:Namespace label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo,
)


class NamespaceNode(StructuredNode):
    """A namespace entity — namespace, package, or module."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="namespace")
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    description = StringProperty(default="")
    source = StringProperty(default="")

    # --- NamespaceNode relationships ----------------------------------------
    #
    #  • COMPOSES  — NamespaceNode → ClassNode
    #    The namespace owns/contains these compounds.  Uses ClassNode as the
    #    representative target type (applies to all compound kinds).
    # --------------------------------------------------------------------------

    compounds = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')
