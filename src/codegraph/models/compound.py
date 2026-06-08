"""Compound node models — ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode.

Each compound kind gets its own neomodel class, Neo4j label, and
kind-specific fields. Common fields are shared via ``CompoundNode``.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class CompoundNode(StructuredNode, CodeGraphNode):
    """Common fields and serialization for all compound node types.

    Attributes:
        qualified_name: Unique identifier for the compound.
        kind: Node kind (e.g. "class", "struct", "interface", "concept").
        layer: Origin layer ("design", "as-built", "dependency").
        component_id: Component identifier for grouping.
        source_type: Source system type (e.g. "Doxygen").
        visibility: Access level (e.g. "public", "private").
        brief_description: Short human-readable description.
        detailed_description: Full human-readable description.
        file_path: Source file path where declared.
        line_number: Source line number where declared.
        definition: Source code definition text (class/struct declaration).
        doc_embedding: Vector embedding of documentation text.
    """

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    source_type = StringProperty(default="")

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

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[],
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

    implementation_ref = RelationshipTo('codegraph.models.implementation.ImplementationNode', 'HAS_IMPLEMENTATION')

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
    defined_in = RelationshipTo('codegraph.models.file.FileNode', 'DEFINED_IN')

    # Template machinery (shared by ClassNode, InterfaceNode, ConceptNode, etc.)
    template_params = RelationshipTo('ClassNode', 'TEMPLATE_PARAM')
    specializes = RelationshipTo('ClassNode', 'SPECIALIZES')
    enforces_concept = RelationshipTo('ConceptNode', 'ENFORCES_CONCEPT')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "brief_description", "visibility"}


class ClassNode(CompoundNode):
    """Class or struct — Neo4j label ``:Class``.

    Attributes:
        kind: Defaults to "class".
        module: Module/namespace the class belongs to.
        base_classes: List of base class qualified names.
        is_final: Whether the class is marked final.
        is_abstract: Whether the class is abstract.
    """

    kind = StringProperty(default="class")
    module = StringProperty(default="")
    base_classes = ArrayProperty(StringProperty(), default=[])
    is_final = BooleanProperty(default=False)
    is_abstract = BooleanProperty(default=False)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "base_classes", "visibility"}

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
    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
    attributes = RelationshipTo('codegraph.models.member.AttributeNode', 'COMPOSES')

    # Inheritance (outgoing + incoming)
    base = RelationshipTo('ClassNode', 'INHERITS_FROM')
    derived = RelationshipFrom('ClassNode', 'INHERITS_FROM')

    # Dependency (outgoing + incoming)
    depends_on = RelationshipTo('ClassNode', 'DEPENDS_ON')
    depended_on_by = RelationshipFrom('ClassNode', 'DEPENDS_ON')

    # Reference (outgoing + incoming)
    references = RelationshipTo('ClassNode', 'REFERENCES')
    referred_by = RelationshipFrom('ClassNode', 'REFERENCES')

    # Interface realization (outgoing)
    realizes = RelationshipTo('InterfaceNode', 'REALIZES')

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')


# --- Stubs for Tasks 3-5 (will be fleshed out with their own fields) ---

class InterfaceNode(CompoundNode):
    """Interface or abstract base — Neo4j label ``:Interface``.

    Attributes:
        kind: Defaults to "interface".
        module: Module/namespace the interface belongs to.
        is_abstract: Whether the interface is abstract (defaults to True).
    """

    kind = StringProperty(default="interface")
    module = StringProperty(default="")
    is_abstract = BooleanProperty(default=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

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

    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
    inherits_from = RelationshipTo('InterfaceNode', 'INHERITS_FROM')
    dependencies = RelationshipTo('ClassNode', 'DEPENDS_ON')

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')


class EnumNode(CompoundNode):
    """Enum type — Neo4j label ``:Enum``.

    Attributes:
        kind: Defaults to "enum".
        module: Module/namespace the enum belongs to.
    """

    kind = StringProperty(default="enum")
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

    # --- EnumNode relationships ----------------------------------------------
    #
    #  • COMPOSES  — EnumNode → EnumValueNode
    #    The enum owns these constant values.  Enums have no methods, attributes,
    #    or inheritance.
    # --------------------------------------------------------------------------

    values = RelationshipTo('codegraph.models.member.EnumValueNode', 'COMPOSES')

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')


class UnionNode(CompoundNode):
    """C/C++ union type — Neo4j label ``:Union``.

    Attributes:
        kind: Defaults to "union".
        module: Module/namespace the union belongs to.
    """

    kind = StringProperty(default="union")
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')


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

    kind = StringProperty(default="concept")
    module = StringProperty(default="")
    initializer = StringProperty(
        default="",
        help_text="The full concept definition expression as written in source.",
    )

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')


class ModuleNode(CompoundNode):
    """Module or logical namespace — Neo4j label ``:Module``.

    Module names are derived from compound qualified names during
    ``LayerGraph`` construction.

    Attributes:
        kind: Defaults to "module".
    """

    kind = StringProperty(default="module")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "visibility"}

    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')

