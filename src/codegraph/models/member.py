"""Member node models — MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode.

Each member kind gets its own node class and Neo4j label. Common fields
are shared via a ``MemberNode`` abstract base.
"""

from __future__ import annotations

from codegraph.models.descriptors import (
    Property,
    Relationship,
    UniqueId,
)

from codegraph.models.tags import CodeGraphNode


class MemberNode(CodeGraphNode):
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
        start_line: First line of the inclusive owned source span (doc comment
            through declaration), 1-based.
        end_line: Last line of the inclusive owned source span (declaration end,
            or body end when the body is in the same file), 1-based.
        definition: Source code definition text (signature only).
        doc_embedding: Vector embedding of documentation text.
    """

    # --- Identity ---
    uid = UniqueId()
    qualified_name = Property(
        str, default="", index=True,
        help_text="Human-readable fully-qualified name. Indexed for lookup; "
                  "the unique key is `uid`.",
    )
    kind = Property(str, required=True)

    # --- Identity fields for uid computation ---
    # Subclasses that have signatures (MethodNode, FunctionNode) override
    # this to include `argsstring` so overloads get distinct uids.
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Tags & provenance ---
    tags = Property(list, default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency'. "
                  "Multiple tags allowed — a node can belong to several views.")

    # ── File provenance ──────────────────────────────────────────
    defined_in = Relationship('DEFINED_IN', direction='OUTGOING',
                              target_class='codegraph.models.file.FileNode')
    component_id = Property(int)
    compound_refid = Property(str, default="")

    # --- Visibility ---
    visibility = Property(str, default="")

    # --- Documentation ---
    brief_description = Property(str, default="")
    detailed_description = Property(str, default="")
    source_documentation = Property(str, default="")

    # --- Location ---
    file_path = Property(str, default="")
    line_number = Property(int)
    body_start = Property(
        int, default=0,
        help_text="Start line of the implementation body (from Doxygen bodystart). "
                  "0 or negative means no implementation body available.",
    )
    body_end = Property(
        int, default=0,
        help_text="End line of the implementation body (from Doxygen bodyend). "
                  "0 or negative means no implementation body available.",
    )
    start_line = Property(
        int, default=0,
        help_text="First line of the inclusive source span this member owns "
                  "(doc comment through declaration), 1-based. 0 when unknown.",
    )
    end_line = Property(
        int, default=0,
        help_text="Last line of the inclusive source span this member owns "
                  "(declaration end, or body end when the body is in the same "
                  "file), 1-based. 0 when unknown.",
    )

    # --- Definition ---
    definition = Property(str, default="")

    # --- Vector embeddings ---
    doc_embedding = Property(list, default=[],
        help_text="Vector embedding of brief_description + detailed_description.")

    # --- Lazy-loaded implementation ----------------------------------------
    implementation_ref = Relationship('HAS_IMPLEMENTATION', direction='OUTGOING',
                                      target_class='codegraph.models.implementation.ImplementationNode')

    # --- File provenance ───────────────────────────────────────────────────
    defined_in = Relationship('DEFINED_IN', direction='OUTGOING',
                              target_class='codegraph.models.file.FileNode')

    # --- Type dependencies ─────────────────────────────────────────────────
    depends_on_compound = Relationship('DEPENDS_ON', direction='OUTGOING',
                                       target_class='codegraph.models.compound.ClassNode')
    depends_on_member = Relationship('DEPENDS_ON', direction='OUTGOING',
                                     target_class='codegraph.models.member.AttributeNode')

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

    kind = Property(str, default="method")
    type_signature = Property(str, default="")
    argsstring = Property(str, default="")
    is_static = Property(bool, default=False)
    is_const = Property(bool, default=False)
    is_constexpr = Property(bool, default=False)
    is_virtual = Property(bool, default=False)
    is_inline = Property(bool, default=False)
    is_explicit = Property(bool, default=False)

    #: Implementation body text, captured at parse time from the source
    #: file (Doxygen's ``bodyfile``/``bodystart``/``bodyend`` line range —
    #: includes the signature line for out-of-line definitions).  The
    #: structured implementation detail codegen needs to regenerate
    #: out-of-line and inline definitions.  Deliberately NOT in
    #: ``_llm_fields`` and stripped by ``serialize()`` unless
    #: ``export_implementation=True`` — implementation data is opt-in.
    body = Property(str, default="")

    #: The file the implementation body lives in (``bodyfile``) — the
    #: planner uses it to route out-of-line definitions to their .cpp.
    body_file = Property(str, default="")

    # Include argsstring in uid so overloads get distinct identities
    _identity_fields = ("qualified_name", "argsstring")

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "argsstring", "visibility",
    }

    # Incoming composition
    parent_compound = Relationship('COMPOSES', direction='INCOMING',
                                   target_class='codegraph.models.compound.ClassNode')
    parent_interface = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.compound.InterfaceNode')

    # ── Call-callee ──────────────────────────────────────────────
    invokes = Relationship('INVOKES', direction='OUTGOING', target_class='MethodNode')
    invokes_function = Relationship('INVOKES', direction='OUTGOING', target_class='FunctionNode')
    invoked_by_function = Relationship('INVOKES', direction='INCOMING', target_class='FunctionNode')

    # ── Type relationships ───────────────────────────────────────
    has_argument = Relationship('HAS_ARGUMENT', direction='OUTGOING',
                                target_class='codegraph.models.compound.ClassNode')
    returns = Relationship('RETURNS', direction='OUTGOING',
                           target_class='codegraph.models.compound.ClassNode')

    # ── Parameters ────────────────────────────────────────────────
    # Ordered by ParameterNode.position (0-based).  Populated from the
    # doxygen-index ``HAS_PARAMETER`` edges (member → parameter).
    has_parameters = Relationship('HAS_PARAMETER', direction='OUTGOING',
                                  target_class='codegraph.models.parameter.ParameterNode')


class AttributeNode(MemberNode):
    """Member variable / data attribute — Neo4j label ``:Attribute``.

    Attributes:
        kind: Defaults to "attribute".
        type_signature: Type string (e.g. "int", "std::string").
        is_static: Whether the attribute is static.
        is_const: Whether the attribute is const.
    """

    _markdown_keyword = "Attribute"

    kind = Property(str, default="attribute")
    type_signature = Property(str, default="")
    initializer = Property(
        str, default="",
        help_text="Explicit source initializer for this attribute, including its leading =.",
    )
    is_static = Property(bool, default=False)
    is_const = Property(bool, default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "visibility",
    }

    # Incoming composition
    parent_compound = Relationship('COMPOSES', direction='INCOMING',
                                   target_class='codegraph.models.compound.ClassNode')
    composes_attribute = Relationship('COMPOSES', direction='INCOMING',
                                      target_class='codegraph.models.member.AttributeNode')


class EnumValueNode(MemberNode):
    """Enum constant value — Neo4j label ``:EnumValue``.

    Attributes:
        kind: Defaults to "enumvalue".
        initializer: The explicit value expression, if any (e.g. ``1``,
            ``1 << 3``, ``"a"``).  Captured from the Doxygen
            ``<initializer>`` element; empty when the enumerator relies
            on implicit sequential values.
    """

    kind = Property(str, default="enumvalue")
    initializer = Property(
        str, default="",
        help_text="Explicit value expression for this enumerator (from Doxygen "
                  "<initializer>). Empty means implicit sequential value.",
    )

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # Incoming composition
    parent_enum = Relationship('COMPOSES', direction='INCOMING',
                               target_class='codegraph.models.compound.EnumNode')


class FunctionNode(MemberNode):
    """Free function (not a method) — Neo4j label ``:Function``.

    Attributes:
        kind: Defaults to "function".
        type_signature: Return type string.
        argsstring: Full argument signature string.
    """

    kind = Property(str, default="function")
    type_signature = Property(str, default="")
    argsstring = Property(str, default="")

    # Include argsstring in uid so overloads get distinct identities
    _identity_fields = ("qualified_name", "argsstring")

    _llm_fields = {
        "qualified_name", "name", "kind", "tags", "brief_description",
        "type_signature", "argsstring", "visibility",
    }

    # Incoming composition
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')

    # ── Call-callee ──────────────────────────────────────────────
    invokes_method = Relationship('INVOKES', direction='OUTGOING', target_class='MethodNode')
    invokes_function = Relationship('INVOKES', direction='OUTGOING', target_class='FunctionNode')
    invoked_by_method = Relationship('INVOKES', direction='INCOMING', target_class='MethodNode')
    invoked_by_function = Relationship('INVOKES', direction='INCOMING', target_class='FunctionNode')

    # ── Parameters ────────────────────────────────────────────────
    # Ordered by ParameterNode.position (0-based).  Populated from the
    # doxygen-index ``HAS_PARAMETER`` edges (member → parameter).
    has_parameters = Relationship('HAS_PARAMETER', direction='OUTGOING',
                                  target_class='codegraph.models.parameter.ParameterNode')


class DefineNode(MemberNode):
    """Preprocessor macro / define — Neo4j label ``:Define``.

    Attributes:
        kind: Defaults to "define".
    """

    kind = Property(str, default="define")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}
