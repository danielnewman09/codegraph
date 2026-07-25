"""Member node models — MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode.

Each member kind gets its own neomodel class and Neo4j label. Common fields
are shared via a ``MemberNode`` abstract base.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom,
)


from codegraph.models.tags import CodeGraphNode


class MemberNode(StructuredNode, CodeGraphNode):
    """Common fields and serialization for all member node types.

    Attributes:
        qualified_name: Human-readable fully-qualified name (indexed, not
            unique).  Used as an identity-field input to ``uid``.
        uid: Deterministic SHA-1 hash — the cross-codebase-stable unique
            key, computed automatically on save.
        kind: Node kind (e.g. "method", "attribute", "function").
        tags: Provenance tags (e.g. ["design"], ["design", "as-built"],
            ["dependency"]). Multiple tags allowed — a node can belong to
            several views simultaneously.
        component_id: Component identifier for grouping.
        compound_refid: Reference ID of the parent compound.
        visibility: Access level (e.g. "public", "private").
        brief_description: Short human-readable description.
        detailed_description: Full human-readable description.
        file_path: Source file path where declared.
        line_number: Source line number where declared.
        body_start: Start line of implementation body (from Doxygen bodystart).
        body_end: End line of implementation body (from Doxygen bodyend).
        definition: Source code definition text (signature only).
        doc_embedding: Vector embedding of documentation text.
    """

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable fully-qualified name. Indexed for lookup; "
                  "the unique key is `uid`.",
    )
    kind = StringProperty(required=True)

    # --- Identity fields for uid computation ---
    # Subclasses that have signatures (MethodNode, FunctionNode) override
    # this to include `argsstring` so overloads get distinct uids.
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Tags & provenance ---
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency'. "
                  "Multiple tags allowed — a node can belong to several views.")
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
    body_start = IntegerProperty(
        default=0,
        help_text="Start line of the implementation body (from Doxygen bodystart). "
                  "0 or negative means no implementation body available.",
    )
    body_end = IntegerProperty(
        default=0,
        help_text="End line of the implementation body (from Doxygen bodyend). "
                  "0 or negative means no implementation body available.",
    )

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of brief_description + detailed_description.")

    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this member → ImplementationNode
    #    The full source code body and its vector embedding.  Kept on a
    #    separate node so that lightweight queries (listing, counting,
    #    serializing) do not pull potentially large implementation text or
    #    embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``method.implementation_ref.all()`` when source code is needed.
    # --------------------------------------------------------------------------

    implementation_ref = RelationshipTo('codegraph.models.implementation.ImplementationNode', 'HAS_IMPLEMENTATION')

    # --- Relationships -------------------------------------------------------
    #
    # Relationship glossary (all member types inherit this):
    #
    #  • DEFINED_IN  — this member → FileNode
    #    The source file where this member is declared/defined.
    # --------------------------------------------------------------------------

    # File location
    defined_in = RelationshipTo('codegraph.models.file.FileNode', 'DEFINED_IN')

    # Type dependencies — this member's type signature references these types.
    # Targets can be CompoundNode (classes, structs) or MemberNode (typedefs).
    # Two separate relationships because neomodel can't target abstract bases.
    depends_on_compound = RelationshipTo('codegraph.models.compound.ClassNode', 'DEPENDS_ON')
    depends_on_member = RelationshipTo('codegraph.models.member.AttributeNode', 'DEPENDS_ON')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "visibility",
    }


class MethodNode(MemberNode):
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

    # Include argsstring in uid so overloads get distinct identities
    _identity_fields = ("qualified_name", "argsstring")

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "argsstring", "visibility",
    }

    # --- MethodNode relationships -------------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming)  — ClassNode | InterfaceNode → this MethodNode
    #    The parent compound or interface owns this method.
    #    Traversed via ``parent_compound`` / ``parent_interface``.
    #
    #  ── Call-callee ──
    #  • INVOKES  — MethodNode/FunctionNode(caller) → MethodNode/FunctionNode(callee)
    #    Call-callee relationship.  Methods and free functions can invoke
    #    each other.
    #
    #  ── Type relationships ──
    #  • HAS_ARGUMENT  — MethodNode → ClassNode
    #    The method accepts a parameter whose type is the target class.
    #    Example: ``void draw(Canvas c)``  →  ``draw -[:HAS_ARGUMENT]-> Canvas``.
    #
    #  • RETURNS  — MethodNode → ClassNode
    #    The method's return type is the target class.
    #    Example: ``Canvas create()``  →  ``create -[:RETURNS]-> Canvas``.
    # --------------------------------------------------------------------------

    # Incoming composition
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')
    parent_interface = RelationshipFrom('codegraph.models.compound.InterfaceNode', 'COMPOSES')

    # Call-callee
    invokes = RelationshipTo('MethodNode', 'INVOKES')
    invokes_function = RelationshipTo('FunctionNode', 'INVOKES')
    invoked_by_function = RelationshipFrom('FunctionNode', 'INVOKES')

    # Type relationships
    has_argument = RelationshipTo('codegraph.models.compound.ClassNode', 'HAS_ARGUMENT')
    returns = RelationshipTo('codegraph.models.compound.ClassNode', 'RETURNS')


class AttributeNode(MemberNode):
    """Member variable / data attribute — Neo4j label ``:Attribute``.

    Attributes:
        kind: Defaults to "attribute".
        type_signature: Type string (e.g. "int", "std::string").
        is_static: Whether the attribute is static.
        is_const: Whether the attribute is const.
    """

    _markdown_keyword = "Attribute"

    kind = StringProperty(default="attribute")
    type_signature = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "visibility",
    }

    # --- AttributeNode relationships ----------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming)  — ClassNode → this AttributeNode
    #    The parent class owns this attribute.
    #    Traversed via ``parent_compound``.
    # --------------------------------------------------------------------------

    # Incoming composition
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')


class EnumValueNode(MemberNode):
    """Enum constant value — Neo4j label ``:EnumValue``.

    Attributes:
        kind: Defaults to "enumvalue".
    """

    kind = StringProperty(default="enumvalue")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # --- EnumValueNode relationships ----------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming)  — EnumNode → this EnumValueNode
    #    The parent enum owns this constant value.
    #    Traversed via ``parent_enum``.
    # --------------------------------------------------------------------------

    # Incoming composition
    parent_enum = RelationshipFrom('codegraph.models.compound.EnumNode', 'COMPOSES')


class FunctionNode(MemberNode):
    """Free function (not a method) — Neo4j label ``:Function``.

    Attributes:
        kind: Defaults to "function".
        type_signature: Return type string.
        argsstring: Full argument signature string.
    """

    kind = StringProperty(default="function")
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")

    # Include argsstring in uid so overloads get distinct identities
    _identity_fields = ("qualified_name", "argsstring")

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "argsstring", "visibility",
    }

    # --- FunctionNode relationships ------------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming)  — NamespaceNode → this FunctionNode
    #    The parent namespace owns this function.
    #    Traversed via ``parent_namespace``.
    #
    #  ── Call-callee ──
    #  • INVOKES  — FunctionNode/MethodNode(caller) → FunctionNode/MethodNode(callee)
    #    Call-callee relationship.  Free functions and methods can invoke
    #    each other.
    # --------------------------------------------------------------------------

    # Incoming composition
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')

    # Call-callee
    invokes_method = RelationshipTo('MethodNode', 'INVOKES')
    invokes_function = RelationshipTo('FunctionNode', 'INVOKES')
    invoked_by_method = RelationshipFrom('MethodNode', 'INVOKES')
    invoked_by_function = RelationshipFrom('FunctionNode', 'INVOKES')


class DefineNode(MemberNode):
    """Preprocessor macro / define — Neo4j label ``:Define``.

    Attributes:
        kind: Defaults to "define".
    """

    kind = StringProperty(default="define")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

