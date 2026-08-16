"""Compound node models — ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode.

Each compound kind gets its own node class and Neo4j label.
Kind-specific fields are shared via ``CompoundNode``.
"""

from __future__ import annotations

from codegraph.models.descriptors import (
    Property,
    Relationship,
    UniqueId,
)

from codegraph.models.tags import CodeGraphNode


class CompoundNode(CodeGraphNode):
    """Common fields and serialization for all compound node types.

    Attributes:
        qualified_name: Human-readable fully-qualified name (indexed, not
            unique).  Used as an identity-field input to ``uid``.
        uid: Deterministic SHA-1 hash — the cross-codebase-stable unique
            key, computed automatically on save.
        kind: Node kind (e.g. "class", "struct", "interface", "concept").
        tags: Provenance tags (e.g. ["design"], ["design", "as-built"],
            ["dependency"]). Multiple tags allowed — a node can belong to
            several views simultaneously. Tags can be added/removed
            independently as the code evolves.
        component_id: Component identifier for grouping.
        source_type: Source system type (e.g. "Doxygen").
        visibility: Access level (e.g. "public", "private").
        brief_description: Short human-readable description.
        detailed_description: Full human-readable description.
        file_path: Source file path where declared.
        line_number: Source line number where declared.
        definition: Source code definition text (class/struct declaration).
        template_declarations: Ordered source declarations for template
            parameters (for example ``"ValidTransferObject T"``).
        source_documentation: Original documentation block immediately
            preceding the compound declaration, retained for lossless
            as-built generation.
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
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Tags & provenance ---
    tags = Property(list, default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency'. "
                  "Multiple tags allowed — a node can belong to several views.")
    component_id = Property(int)
    source_type = Property(str, default="")

    # --- Visibility ---
    visibility = Property(str, default="")

    # --- Documentation ---
    brief_description = Property(str, default="")
    detailed_description = Property(str, default="")

    # --- Location ---
    file_path = Property(str, default="")
    line_number = Property(int)

    # --- Definition ---
    definition = Property(str, default="")
    template_declarations = Property(list, default=[])
    source_documentation = Property(str, default="")

    # --- Vector embeddings ---
    doc_embedding = Property(list, default=[],
        help_text="Vector embedding of brief_description + detailed_description.")

    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this compound → ImplementationNode
    #    The full source code body and its vector embedding.  Kept on a
    #    separate node so that lightweight queries (listing, counting,
    #    serializing) do not pull potentially large implementation text or
    #    embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``node.implementation_ref.all()`` when source code is needed.
    # --------------------------------------------------------------------------

    implementation_ref = Relationship('HAS_IMPLEMENTATION', direction='OUTGOING',
                                      target_class='codegraph.models.implementation.ImplementationNode')

    # --- Relationships -------------------------------------------------------
    #
    # Relationship glossary (all compound types inherit these):
    #
    #  • DEFINED_IN   — this compound → FileNode
    #    The source file where this compound is declared/defined.
    #
    #  • TEMPLATE_PARAM  — this template → ClassNode (parameter slot)
    #    Declares a template type parameter slot. The target ClassNode represents
    #    the parameter itself (kind='type_parameter'). The edge carries metadata:
    #    position, declname, defname, defval.
    #
    #  • SPECIALIZES  — this specialization → ClassNode (primary template)
    #    Records that this compound is a template specialization of another.
    #    Example: ``std::vector<int> -[:SPECIALIZES]-> std::vector<T>``.
    #
    #  • ENFORCES_CONCEPT  — this type-parameter ClassNode → ConceptNode
    #    Records that a template parameter is constrained by a C++20 concept.
    #    The source is a ClassNode(kind='type_parameter'), and the target
    #    is the ConceptNode that defines the constraint.
    #    Example: ``T -[:ENFORCES_CONCEPT]-> ValidTransferObject``.
    # --------------------------------------------------------------------------

    # File location
    defined_in = Relationship('DEFINED_IN', direction='OUTGOING',
                              target_class='codegraph.models.file.FileNode')

    # Template machinery (shared by ClassNode, InterfaceNode, ConceptNode, etc.)
    template_params = Relationship('TEMPLATE_PARAM', direction='OUTGOING', target_class='ClassNode')
    specializes = Relationship('SPECIALIZES', direction='OUTGOING', target_class='ClassNode')
    enforces_concept = Relationship('ENFORCES_CONCEPT', direction='OUTGOING', target_class='ConceptNode')
    constrained_by = Relationship('CONSTRAINS', direction='INCOMING',
                                  target_class='codegraph.models.compound.ConceptNode')
    # Any compound can be the *source* of a CONSTRAINS edge (e.g.
    # BaseTransferObject → CONSTRAINS → TransferObject).
    constrains = Relationship('CONSTRAINS', direction='OUTGOING',
                              target_class='codegraph.models.compound.CompoundNode')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}


class ClassNode(CompoundNode):
    """Class or struct — Neo4j label ``:Class``.

    Attributes:
        kind: Defaults to "class".
        module: Module/namespace the class belongs to.
        base_classes: List of base class qualified names.
        is_final: Whether the class is marked final.
        is_abstract: Whether the class is abstract.
    """

    kind = Property(str, default="class")
    module = Property(str, default="")
    base_classes = Property(list, default=[])
    is_final = Property(bool, default=False)
    is_abstract = Property(bool, default=False)

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "base_classes", "visibility"}

    _markdown_keyword = "Class"

    # --- ClassNode relationships ---------------------------------------------
    #
    # Each relationship is documented as:  descriptor → target  (predicate)
    # Semantics, direction, and concrete examples are included.
    #
    #  ── Composition ──
    #  • COMPOSES  — ClassNode → MethodNode | AttributeNode
    #    Strong ownership. The class owns its methods and attributes.
    #    Destroying the class destroys these members.
    #
    #  ── Inheritance ──
    #  • INHERITS_FROM  — ClassNode(derived) → ClassNode(base)
    #    Inheritance / "is-a". The source (derived class) inherits from the
    #    target (base class).  Example:  ``Dog -[:INHERITS_FROM]-> Animal``.
    #
    #  ── Dependency ──
    #  • DEPENDS_ON  — ClassNode(dependent) → ClassNode(dependency)
    #    The source depends on the target (e.g., includes its header, calls its
    #    methods).  Loose coupling — the target is not owned.
    #
    #  ── Reference ──
    #  • REFERENCES  — ClassNode(referrer) → ClassNode(referent)
    #    The source holds a pointer, reference, or smart-pointer to the target.
    #    Use the ``mechanism`` property (on the edge) to specify how:
    #    raw_pointer, std::unique_ptr, std::shared_ptr, reference, etc.
    #
    #  ── Interface realization ──
    #  • REALIZES  — ClassNode → InterfaceNode
    #    The class implements (realizes) the interface contract.
    #    Example:  ``Printer -[:REALIZES]-> IPrintable``.
    # --------------------------------------------------------------------------

    # Composition (outgoing)
    methods = Relationship('COMPOSES', direction='OUTGOING',
                           target_class='codegraph.models.member.MethodNode')
    attributes = Relationship('COMPOSES', direction='OUTGOING',
                              target_class='codegraph.models.member.AttributeNode')

    # Inheritance (outgoing + incoming)
    base = Relationship('INHERITS_FROM', direction='OUTGOING', target_class='ClassNode')
    derived = Relationship('INHERITS_FROM', direction='INCOMING', target_class='ClassNode')

    # Dependency (outgoing + incoming)
    depends_on = Relationship('DEPENDS_ON', direction='OUTGOING', target_class='ClassNode')
    depended_on_by = Relationship('DEPENDS_ON', direction='INCOMING', target_class='ClassNode')

    # Reference (outgoing + incoming)
    references = Relationship('REFERENCES', direction='OUTGOING', target_class='ClassNode')
    referred_by = Relationship('REFERENCES', direction='INCOMING', target_class='ClassNode')

    # Interface realization (outgoing)
    realizes = Relationship('REALIZES', direction='OUTGOING', target_class='InterfaceNode')

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')


# --- Stubs for Tasks 3-5 (will be fleshed out with their own fields) ---

class InterfaceNode(CompoundNode):
    """Interface or abstract base — Neo4j label ``:Interface``.

    Attributes:
        kind: Defaults to "interface".
        module: Module/namespace the interface belongs to.
        is_abstract: Whether the interface is abstract (defaults to True).
    """

    kind = Property(str, default="interface")
    module = Property(str, default="")
    is_abstract = Property(bool, default=True)

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # --- InterfaceNode relationships -----------------------------------------
    #
    #  • COMPOSES  — InterfaceNode → MethodNode
    #    The interface declares these methods.  Interfaces have no attributes.
    #
    #  • INHERITS_FROM  — InterfaceNode(derived) → InterfaceNode(base)
    #    Interface inheritance.  The source extends the target interface.
    #    Example:  ``ISerializable -[:INHERITS_FROM]-> IPrintable``.
    #
    #  • DEPENDS_ON  — InterfaceNode → ClassNode
    #    The interface depends on a concrete class (rare; usually the reverse).
    # --------------------------------------------------------------------------

    methods = Relationship('COMPOSES', direction='OUTGOING',
                           target_class='codegraph.models.member.MethodNode')
    inherits_from = Relationship('INHERITS_FROM', direction='OUTGOING', target_class='InterfaceNode')
    dependencies = Relationship('DEPENDS_ON', direction='OUTGOING', target_class='ClassNode')

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')


class EnumNode(CompoundNode):
    """Enum type — Neo4j label ``:Enum``.

    Attributes:
        kind: Defaults to "enum".
        module: Module/namespace the enum belongs to.
    """

    kind = Property(str, default="enum")
    module = Property(str, default="")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    def markdown_body_type(self) -> str | None:
        """Enum has a **Values:** section instead of methods/attributes."""
        return "enum"

    # --- EnumNode relationships ----------------------------------------------
    #
    #  • COMPOSES  — EnumNode → EnumValueNode
    #    The enum owns these constant values.  Enums have no methods, attributes,
    #    or inheritance.
    # --------------------------------------------------------------------------

    values = Relationship('COMPOSES', direction='OUTGOING',
                          target_class='codegraph.models.member.EnumValueNode')

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')


class UnionNode(CompoundNode):
    """C/C++ union type — Neo4j label ``:Union``.

    Attributes:
        kind: Defaults to "union".
        module: Module/namespace the union belongs to.
    """

    kind = Property(str, default="union")
    module = Property(str, default="")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')


class ConceptNode(CompoundNode):
    """C++20 concept (type constraint) — Neo4j label ``:Concept``.

    Concepts define constraints on template parameters. They are
    parsed from Doxygen ``kind=\"concept\"`` compound elements.

    Attributes:
        kind: Defaults to "concept".
        module: Module/namespace the concept belongs to.
        initializer: The concept definition expression (e.g.
            ``template<typename T>\nconcept ValidTransferObject = TransferObject<T>``).
    """

    kind = Property(str, default="concept")
    module = Property(str, default="")
    initializer = Property(
        str, default="",
        help_text="The full concept definition expression as written in source.",
    )

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')

    # CONSTRAINS — this concept constrains a type/concept
    # (e.g. TransferObject CONSTRAINS BaseTransferObject)
    constrains = Relationship('CONSTRAINS', direction='OUTGOING',
                              target_class='codegraph.models.compound.CompoundNode')


class ModuleNode(CompoundNode):
    """Module or logical namespace — Neo4j label ``:Module``.

    Module names are derived from compound qualified names during
    ``LayerGraph`` construction.

    Attributes:
        kind: Defaults to "module".
    """

    kind = Property(str, default="module")

    _llm_fields = {"qualified_name", "name", "kind", "tags", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = Relationship('COMPOSES', direction='INCOMING',
                                    target_class='codegraph.models.namespace.NamespaceNode')
