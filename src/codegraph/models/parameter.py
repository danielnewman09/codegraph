"""Parameter node model (:Parameter label in Neo4j)."""

from neomodel import StructuredNode, StringProperty, IntegerProperty


class ParameterNode(StructuredNode):
    """A function/method parameter."""

    # No UniqueIdProperty — parameters don't have a natural single key.
    # Use a composite lookup (position + member_refid) in the repository.
    position = IntegerProperty(required=True)
    name = StringProperty(required=True)
    type = StringProperty(default="")
    default_value = StringProperty(default="")
    member_refid = StringProperty(default="")
