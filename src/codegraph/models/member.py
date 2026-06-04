"""Member node models — MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode.

Each member kind gets its own neomodel class and Neo4j label. Common fields
are shared via a ``_MemberMixin`` abstract base.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipTo,
)

from codegraph.models.tags import CodeGraphNode


class _MemberMixin(StructuredNode, CodeGraphNode):
    """Common fields and serialization for all member node types.

    Attributes:
        qualified_name: Unique identifier for the member.
        kind: Node kind (e.g. "method", "attribute", "function").
        layer: Origin layer ("design", "as-built", "dependency").
        component_id: Component identifier for grouping.
        compound_refid: Reference ID of the parent compound.
        visibility: Access level (e.g. "public", "private").
        brief_description: Short human-readable description.
        detailed_description: Full human-readable description.
        file_path: Source file path where declared.
        line_number: Source line number where declared.
        definition: Source code definition text.
    """

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    compound_refid = StringProperty(default="")

    # --- Visibility ---
    visibility = StringProperty(default="")

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Relationships -------------------------------------------------------
    #
    # Relationship glossary (all member types inherit this):
    #
    #  • DEFINED_IN  — this member → FileNode
    #    The source file where this member is declared/defined.
    # --------------------------------------------------------------------------

    # File location
    defined_in = RelationshipTo('codegraph.models.file.FileNode', 'DEFINED_IN')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "visibility",
    }


class MethodNode(_MemberMixin):
    """Function or method — Neo4j label ``:Method``.

    Attributes:
        kind: Defaults to "method".
        type_signature: Return type string (e.g. "void", "CalculatorResult").
        argsstring: Full argument signature string.
        is_static: Whether the method is static.
        is_const: Whether the method is const.
        is_constexpr: Whether the method is constexpr.
        is_virtual: Whether the method is virtual.
        is_inline: Whether the method is inline.
        is_explicit: Whether the method is explicit.
    """

    kind = StringProperty(default="method")
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)
    is_constexpr = BooleanProperty(default=False)
    is_virtual = BooleanProperty(default=False)
    is_inline = BooleanProperty(default=False)
    is_explicit = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility",
    }

    # --- MethodNode relationships -------------------------------------------
    #
    #  • INVOKES  — MethodNode(caller) → MethodNode(callee)
    #    Call-callee relationship.  The source method invokes the target method.
    #
    #  • HAS_ARGUMENT  — MethodNode → ClassNode
    #    The method accepts a parameter whose type is the target class.
    #    Example: ``void draw(Canvas c)``  →  ``draw -[:HAS_ARGUMENT]-> Canvas``.
    #
    #  • RETURNS  — MethodNode → ClassNode
    #    The method's return type is the target class.
    #    Example: ``Canvas create()``  →  ``create -[:RETURNS]-> Canvas``.
    #
    #  Note: COMPOSES is declared only on parent compound nodes (ClassNode,
    #  InterfaceNode) as an outgoing relationship. Use ``compound_refid``
    #  (inherited from ``_MemberMixin``) to look up the parent compound.
    # --------------------------------------------------------------------------

    # Call-callee
    invokes = RelationshipTo('MethodNode', 'INVOKES')

    # Type relationships
    has_argument = RelationshipTo('codegraph.models.compound.ClassNode', 'HAS_ARGUMENT')
    returns = RelationshipTo('codegraph.models.compound.ClassNode', 'RETURNS')


class AttributeNode(_MemberMixin):
    """Member variable / data attribute — Neo4j label ``:Attribute``.

    Attributes:
        kind: Defaults to "attribute".
        type_signature: Type string (e.g. "int", "std::string").
        is_static: Whether the attribute is static.
        is_const: Whether the attribute is const.
    """

    kind = StringProperty(default="attribute")
    type_signature = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "visibility",
    }

    # --- AttributeNode relationships ----------------------------------------
    #
    #  Note: COMPOSES is declared only on parent ClassNode as an outgoing
    #  relationship. Use ``compound_refid`` (inherited from ``_MemberMixin``)
    #  to look up the parent compound.
    # --------------------------------------------------------------------------


class EnumValueNode(_MemberMixin):
    """Enum constant value — Neo4j label ``:EnumValue``.

    Attributes:
        kind: Defaults to "enumvalue".
    """

    kind = StringProperty(default="enumvalue")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

    # --- EnumValueNode relationships ----------------------------------------
    #
    #  Note: COMPOSES is declared only on parent EnumNode as an outgoing
    #  relationship. Use ``compound_refid`` (inherited from ``_MemberMixin``)
    #  to look up the parent compound.
    # --------------------------------------------------------------------------


class FunctionNode(_MemberMixin):
    """Free function (not a method) — Neo4j label ``:Function``.

    Attributes:
        kind: Defaults to "function".
        type_signature: Return type string.
        argsstring: Full argument signature string.
    """

    kind = StringProperty(default="function")
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility",
    }


class DefineNode(_MemberMixin):
    """Preprocessor macro / define — Neo4j label ``:Define``.

    Attributes:
        kind: Defaults to "define".
    """

    kind = StringProperty(default="define")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

