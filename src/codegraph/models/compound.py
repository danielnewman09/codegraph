"""Compound node model (:Compound label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)


class CompoundNode(StructuredNode):
    """A compound entity — class, struct, interface, enum, etc."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")
    base_classes = ArrayProperty(StringProperty(), default=[])
    file_path = StringProperty(default="")
    line_number = IntegerProperty()
    source = StringProperty(default="")
    is_final = BooleanProperty(default=False)
    is_abstract = BooleanProperty(default=False)

    # Relationships
    members = RelationshipTo('codegraph.models.member.MemberNode', 'COMPOSES')
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
    base = RelationshipTo('CompoundNode', 'GENERALIZES')
    derived = RelationshipFrom('CompoundNode', 'GENERALIZES')
