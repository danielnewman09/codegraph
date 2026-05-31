"""Member node model (:Member label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipFrom,
)


class MemberNode(StructuredNode):
    """A member entity — method, variable, define, enumvalue, function."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    compound_refid = StringProperty(default="")
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")
    type_signature = StringProperty(default="")
    definition = StringProperty(default="")
    argsstring = StringProperty(default="")
    file_path = StringProperty(default="")
    line_number = IntegerProperty()
    source = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)
    is_constexpr = BooleanProperty(default=False)
    is_virtual = BooleanProperty(default=False)
    is_inline = BooleanProperty(default=False)
    is_explicit = BooleanProperty(default=False)

    # Relationships
    parent_compound = RelationshipFrom('codegraph.models.compound.CompoundNode', 'COMPOSES')
