"""Literal node model (:Literal label in Neo4j).

Represents primitive/builtin values (int, float, string, boolean) as
first-class graph nodes.  Used in verification conditions where the
expected value on the right-hand side of an assertion is a literal
rather than a reference to a design-graph node.

Example::

    Condition: Engine.result == 30

    (Condition) -[:LEFT_OPERAND]-> (AttributeNode "Engine::result")
    (Condition) -[:RIGHT_OPERAND]-> (LiteralNode value="30" value_type="int")

LiteralNodes are lightweight — they carry only ``value``, ``value_type``,
and the standard ``qualified_name``/``tags``/``kind`` fields.  They do
not participate in COMPOSES relationships (they are not owned by a
class or namespace).  During the scaffold phase they carry
``tags=["scaffold"]``; the design agent may later replace them with
proper typed constants or leave them as-is.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode,
    StringProperty,
    ArrayProperty,
    UniqueIdProperty,
)

from codegraph.models.tags import CodeGraphNode


class LiteralNode(StructuredNode, CodeGraphNode):
    """A primitive/builtin literal value — Neo4j label ``:Literal``.

    Attributes:
        qualified_name: Human-readable identifier, typically
            ``"literal::<value>"`` (e.g. ``"literal::30"``,
            ``"literal::true"``, ``"literal::0.0"``) — indexed, not unique.
        uid: Deterministic SHA-1 hash — the cross-codebase-stable unique key.
        kind: Defaults to ``"literal"``.
        value: The raw literal value as a string (e.g. ``"30"``, ``"true"``,
            ``"0.0"``, ``"hello"``).  Stored as a string for uniformity;
            ``value_type`` indicates how to interpret it.
        value_type: The primitive type — one of ``"int"``, ``"float"``,
            ``"string"``, ``"boolean"``.
        tags: Provenance tags (e.g. ``["scaffold"]``).
    """

    _markdown_keyword = "Literal"

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable identifier, typically 'literal::<value>'.",
    )
    kind = StringProperty(default="literal")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Literal value ---
    value = StringProperty(
        required=True,
        help_text="The raw literal value as a string (e.g. '30', 'true', '0.0').",
    )
    value_type = StringProperty(
        required=True,
        help_text="Primitive type: 'int', 'float', 'string', or 'boolean'.",
    )

    # --- Tags & provenance ---
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "value", "value_type", "tags",
    }