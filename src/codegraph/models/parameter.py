"""Parameter node model (:Parameter label in Neo4j).

Parameters have no outgoing relationships of their own.
They are identified by a composite of (position, member_refid) rather than
a single unique property."""

from neomodel import StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty

from codegraph.models.tags import CodeGraphNode


class ParameterNode(StructuredNode, CodeGraphNode):
    """A function/method parameter.

    Parameters have no outgoing relationships of their own.
    They are identified by a composite of (position, member_refid) which
    is hashed into ``uid``.

    Attributes:
        uid: Deterministic SHA-1 hash of ``member_refid`` + ``position``.
        position: Zero-based position in the parameter list.
        type: Type string for the parameter (e.g. "int", "const std::string&").
        default_value: Default value expression, if any.
        member_refid: Reference ID of the parent method/function.
    """

    # --- Identity ---
    uid = UniqueIdProperty()

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("member_refid", "position")

    qualified_name = StringProperty(
        default="", index=True,
        help_text="Qualified name for display/serialization.",
    )
    position = IntegerProperty(required=True)
    type = StringProperty(default="")
    default_value = StringProperty(default="")
    member_refid = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "type"}