"""Test definition node models — :Test / :Assertion / :TestStep labels in Neo4j.

These models migrate the verification functionality from the ticketing
system's ``backend_migrated.models.verification`` into codegraph as
first-class node types.  They capture **test definitions** — e.g.
pytest functions with their assertions and relationships to the tested
code.

Graph structure::

    NamespaceNode -[:COMPOSES]-> TestNode
    TestNode -[:COMPOSES]-> AssertionNode   (pre/post conditions)
    TestNode -[:COMPOSES]-> TestStepNode     (stimulus / actions)
    TestNode -[:VERIFIES]-> MethodNode | FunctionNode | ClassNode | ...

    AssertionNode -[:LEFT_OPERAND]->  AttributeNode | MethodNode | LiteralNode | ...
    AssertionNode -[:RIGHT_OPERAND]-> AttributeNode | MethodNode | LiteralNode | ...
    TestStepNode  -[:CALLEE]->        MethodNode | FunctionNode | ClassNode | ...
    TestStepNode  -[:CALLER]->        MethodNode | FunctionNode | ClassNode | ...

Design notes
~~~~~~~~~~~~
The ticketing system's ``VerificationMethod`` / ``Condition`` / ``Action``
used a single ``layer`` field for provenance and ``refid`` as
``UniqueIdProperty``.  These codegraph-native models follow the current
codegraph conventions:

- ``uid`` ``UniqueIdProperty`` with deterministic SHA-1 hashing from
  ``_identity_fields`` (same as CompoundNode, MemberNode, etc.).
- ``tags`` ``ArrayProperty`` replacing the legacy ``layer`` field.
- Multiple ``RelationshipTo`` descriptors per edge type (e.g.
  ``left_operand_compound``, ``left_operand_member``,
  ``left_operand_literal``) so that ``LayerGraph.to_neo4j()`` and
  ``find_relationship_manager()`` can dispatch correctly to the right
  target class — the same pattern used by ``ClassNode.methods`` /
  ``ClassNode.attributes`` (both ``COMPOSES`` with different targets).

The ticketing system used raw Cypher for cross-type edges because
neomodel's relationship managers filter by ``__label__``.  The
codegraph approach of declaring separate managers per target type
avoids that problem entirely: each manager only matches its own target
class, and ``serialize_edges()`` / ``walk_edges()`` walk all of them.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode,
    StringProperty,
    IntegerProperty,
    ArrayProperty,
    FloatProperty,
    UniqueIdProperty,
    RelationshipTo,
    RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


# ══════════════════════════════════════════════════════════════════════════
# TestNode — a test definition (e.g. a pytest function)
# ══════════════════════════════════════════════════════════════════════════


class TestNode(StructuredNode, CodeGraphNode):
    """A test definition — Neo4j label ``:Test``.

    Represents a single test case (e.g. a pytest ``test_*`` function or
    a ``Test*`` class method).  TestNodes are composed by their parent
    namespace (or file) via ``COMPOSES``, and in turn compose their
    :class:`AssertionNode` children (pre/post-conditions / assertions)
    and :class:`TestStepNode` children (stimulus actions).

    A ``VERIFIES`` relationship connects the test to the design/as-built
    code nodes (methods, functions, classes) that it exercises.

    Attributes:
        qualified_name: Fully-qualified test identifier
            (e.g. ``"tests::test_member::TestUpdate::test_single_field"``).
        uid: Deterministic SHA-1 hash of ``qualified_name``.
        kind: Always ``"test"``.
        test_name: The test function name (e.g. ``"test_single_field"``).
        test_module: Dotted module path (e.g. ``"tests.test_member"``).
        method: Verification method type — ``"automated"``, ``"review"``,
            ``"inspection"``, etc.
        description: Human-readable description of what this test verifies.
        tags: Provenance tags (e.g. ``["as-built"]``, ``["design"]``).
        file_path: Source file path where the test is defined.
        line_number: Source line number of the test function definition.
        doc_embedding: Vector embedding of the test's docstring + description.
    """

    # Prevent pytest from collecting this class as a test case
    __test__ = False

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Fully-qualified test identifier "
                  "(e.g. 'tests::test_member::TestUpdate::test_single_field').",
    )
    kind = StringProperty(default="test")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Test metadata ---
    test_name = StringProperty(
        default="",
        help_text="The test function name (e.g. 'test_single_field').",
    )
    test_module = StringProperty(
        default="",
        help_text="Dotted module path (e.g. 'tests.test_member').",
    )
    method = StringProperty(
        default="automated",
        help_text="Verification method type — 'automated', 'review', 'inspection'.",
    )
    description = StringProperty(
        default="",
        help_text="Human-readable description of what this test verifies.",
    )

    # --- Tags & provenance ---
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(
        FloatProperty(),
        default=[],
        help_text="Vector embedding of the test's docstring + description.",
    )

    # --- Relationships -------------------------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming) — NamespaceNode → this TestNode
    #    The parent namespace owns this test.  Traversed via
    #    ``parent_namespace``.
    #
    #  ── Composition (outgoing) ──
    #  • COMPOSES — TestNode → AssertionNode
    #    The test owns its assertion / condition nodes.
    #  • COMPOSES — TestNode → TestStepNode
    #    The test owns its action / stimulus step nodes.
    #
    #  ── Verification ──
    #  • VERIFIES — TestNode → MethodNode | FunctionNode | ClassNode |
    #    InterfaceNode | EnumNode | UnionNode | ModuleNode
    #    The test exercises / verifies the target code node.  Separate
    #    descriptors per target type so that
    #    ``find_relationship_manager()`` dispatches correctly.
    #
    #  ── File location ──
    #  • DEFINED_IN — TestNode → FileNode
    #    The source file where the test is defined.
    # --------------------------------------------------------------------------

    # Incoming composition
    parent_namespace = RelationshipFrom(
        "codegraph.models.namespace.NamespaceNode", "COMPOSES"
    )

    # Outgoing composition
    assertions = RelationshipTo(
        "codegraph.models.test.AssertionNode", "COMPOSES"
    )
    steps = RelationshipTo(
        "codegraph.models.test.TestStepNode", "COMPOSES"
    )
    fixtures = RelationshipTo(
        "codegraph.models.test.TestFixtureNode", "COMPOSES"
    )

    # Verification — separate descriptors per target type
    verifies_methods = RelationshipTo(
        "codegraph.models.member.MethodNode", "VERIFIES"
    )
    verifies_functions = RelationshipTo(
        "codegraph.models.member.FunctionNode", "VERIFIES"
    )
    verifies_classes = RelationshipTo(
        "codegraph.models.compound.ClassNode", "VERIFIES"
    )
    verifies_interfaces = RelationshipTo(
        "codegraph.models.compound.InterfaceNode", "VERIFIES"
    )
    verifies_enums = RelationshipTo(
        "codegraph.models.compound.EnumNode", "VERIFIES"
    )
    verifies_unions = RelationshipTo(
        "codegraph.models.compound.UnionNode", "VERIFIES"
    )
    verifies_modules = RelationshipTo(
        "codegraph.models.compound.ModuleNode", "VERIFIES"
    )

    # File location
    defined_in = RelationshipTo(
        "codegraph.models.file.FileNode", "DEFINED_IN"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "tags",
        "test_name", "test_module", "method", "description",
    }

    _markdown_keyword = "Test"

    # --- Queries ---

    @classmethod
    def fetch_by_tag(cls, tag: str):
        """Return all TestNodes whose ``tags`` array contains *tag*.

        neomodel's ``ArrayProperty`` doesn't support a native
        array-membership filter, so we fetch all nodes and filter in
        Python.  Fine for the expected cardinality (hundreds of tests).
        """
        return [n for n in cls.nodes.all() if tag in (n.tags or [])]


# ══════════════════════════════════════════════════════════════════════════
# AssertionNode — a pre/post-condition assertion in a test
# ══════════════════════════════════════════════════════════════════════════


class AssertionNode(StructuredNode, CodeGraphNode):
    """A test assertion / pre/post-condition — Neo4j label ``:Assertion``.

    An AssertionNode captures a single condition checked during a test:

    - **Pre-conditions** (``phase="pre"``): state that must hold before
      the test action runs (e.g. ``engine.is_running == True``).
    - **Post-conditions** (``phase="post"``): the actual assertions —
      state that must hold after the test action (e.g.
      ``engine.result == 30``).

    Operands are connected via ``LEFT_OPERAND`` and ``RIGHT_OPERAND``
    edges to code-graph nodes (attributes, methods, literals, etc.).
    Separate relationship descriptors are declared per target type so
    that ``find_relationship_manager()`` and ``LayerGraph.to_neo4j()``
    dispatch correctly.

    Example::

        AssertionNode: Engine.result == 30

        (AssertionNode) -[:LEFT_OPERAND]->  (AttributeNode "Engine::result")
        (AssertionNode) -[:RIGHT_OPERAND]-> (LiteralNode value="30")

    Attributes:
        qualified_name: Human-readable identifier for this assertion.
        uid: Deterministic SHA-1 hash of ``qualified_name``.
        kind: Always ``"assertion"``.
        phase: ``"pre"`` or ``"post"``.
        order: Sort order within the phase (0-based).
        operator: Comparison operator (e.g. ``"=="``, ``">"``, ``"!="``).
        description: Human-readable description of the condition.
        tags: Provenance tags.
    """

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable identifier for this assertion.",
    )
    kind = StringProperty(default="assertion")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Assertion fields ---
    phase = StringProperty(
        required=True,
        help_text="Condition phase — 'pre' or 'post'.",
    )
    order = IntegerProperty(
        default=0,
        help_text="Sort order within the phase (0-based).",
    )
    operator = StringProperty(
        default="==",
        help_text="Comparison operator (e.g. '==', '>', '<', '!=').",
    )
    description = StringProperty(
        default="",
        help_text="Human-readable description of the condition.",
    )

    # --- Tags & provenance ---
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Relationships -------------------------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming) — TestNode → this AssertionNode
    #    The parent test owns this assertion.
    #
    #  ── Operand edges (outgoing) ──
    #  • LEFT_OPERAND — AssertionNode → AttributeNode | MethodNode |
    #    ClassNode | LiteralNode
    #    The subject / left-hand side of the comparison.
    #  • RIGHT_OPERAND — AssertionNode → AttributeNode | MethodNode |
    #    ClassNode | LiteralNode
    #    The expected / right-hand side of the comparison.
    #
    # Separate descriptors per target type so that
    # ``find_relationship_manager()`` dispatches correctly.
    # --------------------------------------------------------------------------

    # Incoming composition
    test = RelationshipFrom("codegraph.models.test.TestNode", "COMPOSES")

    # Incoming — TestFixtureNodes defined within this step
    defined_fixtures = RelationshipFrom(
        "codegraph.models.test.TestFixtureNode", "DEFINED_IN"
    )

    # Incoming — a TestFixtureNode that is checked by this assertion
    checked_by_fixtures = RelationshipFrom(
        "codegraph.models.test.TestFixtureNode", "CHECKED_BY"
    )

    # Left operand — subject of the comparison
    left_operand_compound = RelationshipTo(
        "codegraph.models.compound.CompoundNode", "LEFT_OPERAND"
    )
    left_operand_attribute = RelationshipTo(
        "codegraph.models.member.AttributeNode", "LEFT_OPERAND"
    )
    left_operand_method = RelationshipTo(
        "codegraph.models.member.MethodNode", "LEFT_OPERAND"
    )
    left_operand_function = RelationshipTo(
        "codegraph.models.member.FunctionNode", "LEFT_OPERAND"
    )
    left_operand_literal = RelationshipTo(
        "codegraph.models.literal.LiteralNode", "LEFT_OPERAND"
    )

    # Right operand — expected value
    right_operand_compound = RelationshipTo(
        "codegraph.models.compound.CompoundNode", "RIGHT_OPERAND"
    )
    right_operand_attribute = RelationshipTo(
        "codegraph.models.member.AttributeNode", "RIGHT_OPERAND"
    )
    right_operand_method = RelationshipTo(
        "codegraph.models.member.MethodNode", "RIGHT_OPERAND"
    )
    right_operand_function = RelationshipTo(
        "codegraph.models.member.FunctionNode", "RIGHT_OPERAND"
    )
    right_operand_literal = RelationshipTo(
        "codegraph.models.literal.LiteralNode", "RIGHT_OPERAND"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "tags",
        "phase", "operator", "description", "order",
    }

    _markdown_keyword = "Assertion"

    def markdown_body_type(self) -> str | None:
        """AssertionNode has no member/enum body section."""
        return None


# ══════════════════════════════════════════════════════════════════════════
# TestStepNode — a stimulus action performed during a test
# ══════════════════════════════════════════════════════════════════════════


class TestStepNode(StructuredNode, CodeGraphNode):
    """A test action / stimulus step — Neo4j label ``:TestStep``.

    A TestStepNode captures a **block** of test code — not necessarily a
    single line, but a logical unit of stimulus or setup.  A step may be
    as granular as a single function call, or as coarse as an entire
    ``arrange`` / ``act`` / ``assert`` block within a test.

    Steps are **not** functions — they have no ``type_signature`` or
    ``argsstring``.  However, they *can* carry their source code block
    via a ``HAS_IMPLEMENTATION`` relationship to an
    :class:`ImplementationNode`, using the same lazy-loading pattern as
    ``MethodNode`` and ``CompoundNode``.  This keeps the step node
    lightweight for listing/counting queries while making the full
    source text available on demand:

    .. code-block:: python

        impl_nodes = step.implementation_ref.all()
        if impl_nodes:
            source_code = impl_nodes[0].implementation

    Steps also reference the code-graph nodes they interact with via
    ``CALLEE`` and ``CALLER`` edges.

    Example::

        TestStepNode: "arrange" block

        (TestStepNode) -[:CALLEE]->      (MethodNode "Engine::set_target")
        (TestStepNode) -[:CALLER]->      (TestNode "test_set_target")
        (TestStepNode) -[:HAS_IMPLEMENTATION]-> (ImplementationNode source="engine = Engine()…")

    Attributes:
        qualified_name: Human-readable identifier for this step.
        uid: Deterministic SHA-1 hash of ``qualified_name``.
        kind: Always ``"test_step"``.
        order: Sort order within the test (0-based).
        description: Human-readable description of the action.
        tags: Provenance tags.
        body_start: Start line of the source block within the test file
            (1-based).  0 means no source block is available.
        body_end: End line of the source block within the test file
            (1-based).  0 means no source block is available.
    """

    # Prevent pytest from collecting this class as a test case
    __test__ = False

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable identifier for this test step.",
    )
    kind = StringProperty(default="test_step")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Step fields ---
    order = IntegerProperty(
        default=0,
        help_text="Sort order within the test (0-based).",
    )
    description = StringProperty(
        default="",
        help_text="Human-readable description of the action step.",
    )
    body_start = IntegerProperty(
        default=0,
        help_text="Start line of the source block within the test file "
                  "(1-based). 0 means no source block is available.",
    )
    body_end = IntegerProperty(
        default=0,
        help_text="End line of the source block within the test file "
                  "(1-based). 0 means no source block is available.",
    )

    # --- Tags & provenance ---
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this step → ImplementationNode
    #    The full source code block of the step and its vector embedding.
    #    Kept on a separate node so that lightweight queries (listing,
    #    counting, serializing) do not pull potentially large source text
    #    or embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``step.implementation_ref.all()`` when source code is needed.
    #    This is the same pattern used by MethodNode and CompoundNode.
    # --------------------------------------------------------------------------

    implementation_ref = RelationshipTo(
        "codegraph.models.implementation.ImplementationNode", "HAS_IMPLEMENTATION"
    )

    # --- Relationships -------------------------------------------------------
    #
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming) — TestNode → this TestStepNode
    #    The parent test owns this step.
    #
    #  ── Call edges (outgoing) ──
    #  • CALLEE — TestStepNode → MethodNode | FunctionNode | ClassNode
    #    The function/method being called in this step.
    #  • CALLER — TestStepNode → MethodNode | FunctionNode | ClassNode |
    #    TestNode
    #    The entity performing the call (often the test itself).
    #
    # Separate descriptors per target type so that
    # ``find_relationship_manager()`` dispatches correctly.
    # --------------------------------------------------------------------------

    # Incoming composition
    test = RelationshipFrom("codegraph.models.test.TestNode", "COMPOSES")

    # Incoming — TestFixtureNodes defined within this step
    defined_fixtures = RelationshipFrom(
        "codegraph.models.test.TestFixtureNode", "DEFINED_IN"
    )

    # Callee — the function/method being called
    callee_method = RelationshipTo(
        "codegraph.models.member.MethodNode", "CALLEE"
    )
    callee_function = RelationshipTo(
        "codegraph.models.member.FunctionNode", "CALLEE"
    )
    callee_class = RelationshipTo(
        "codegraph.models.compound.ClassNode", "CALLEE"
    )

    # Caller — the entity performing the call
    caller_method = RelationshipTo(
        "codegraph.models.member.MethodNode", "CALLER"
    )
    caller_function = RelationshipTo(
        "codegraph.models.member.FunctionNode", "CALLER"
    )
    caller_class = RelationshipTo(
        "codegraph.models.compound.ClassNode", "CALLER"
    )
    caller_test = RelationshipTo(
        "codegraph.models.test.TestNode", "CALLER"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "tags",
        "description", "order",
    }

    _markdown_keyword = "TestStep"

    def markdown_body_type(self) -> str | None:
        """TestStepNode has no member/enum body section."""
        return None

# ══════════════════════════════════════════════════════════════════════════
# TestFixtureNode — a variable defined within a test
# ══════════════════════════════════════════════════════════════════════════


class TestFixtureNode(StructuredNode, CodeGraphNode):
    """A test-local variable — Neo4j label ``:TestFixture``.

    A TestFixtureNode tracks a variable that is defined within a test
    function.  This includes:

    - **Direct instances** of graph types — e.g. ``foo = Foo()`` where
      ``Foo`` is a ClassNode in the graph.
    - **Intermediate / derived values** — e.g.
      ``parents = enum_node.parent_namespace.all()`` where ``parents``
      is a ``list[NamespaceNode]``.  These may be primitive Python types
      (dict, str, list, int) or collections of graph types.

    The node is intentionally flexible: ``type_signature`` captures the
    type as a string (covering primitives that have no graph node), while
    the ``OF_TYPE`` relationship links to the actual graph node when the
    type exists in the codegraph.

    Structure::

        TestNode -[:COMPOSES]-> TestFixtureNode
        TestFixtureNode -[:OF_TYPE]-> ClassNode | EnumNode | NamespaceNode | ...
        TestFixtureNode -[:CHECKED_BY]-> AssertionNode
        TestFixtureNode -[:DEFINED_IN]-> TestStepNode

    Attributes:
        qualified_name: Fully-qualified identifier
            (e.g. ``"tests::test_enum::ns_node"``).
        uid: Deterministic SHA-1 hash of ``qualified_name``.
        kind: Always ``"test_fixture"``.
        name: The variable name as written in the test
            (e.g. ``"ns_node"``, ``"parents"``, ``"foo"``).
        description: Why this variable is used and why it is necessary.
        type_signature: The type as a string — covers both graph types
            (e.g. ``"Foo"``, ``"NamespaceNode"``) and primitives
            (e.g. ``"dict"``, ``"str"``, ``"list[NamespaceNode]"``).
        tags: Provenance tags (e.g. ``["as-built"]``).
        doc_embedding: Vector embedding of the description.
    """

    # Prevent pytest from collecting this class as a test case
    __test__ = False

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Fully-qualified fixture identifier "
                  "(e.g. 'tests::test_enum::ns_node').",
    )
    kind = StringProperty(default="test_fixture")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Fixture fields ---
    name = StringProperty(
        required=True,
        help_text="The variable name as written in the test "
                  "(e.g. 'ns_node', 'parents', 'foo').",
    )
    description = StringProperty(
        default="",
        help_text="Why this variable is used and why it is necessary.",
    )
    type_signature = StringProperty(
        default="",
        help_text="The type as a string.  Covers both graph types "
                  "(e.g. 'Foo', 'NamespaceNode') and primitives "
                  "(e.g. 'dict', 'str', 'list[NamespaceNode]').",
    )

    # --- Tags & provenance ---
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(
        FloatProperty(),
        default=[],
        help_text="Vector embedding of the fixture's description.",
    )

    # --- Relationships -------------------------------------------------------
    #
    #  -- Composition (incoming) --
    #  - COMPOSES (incoming) - TestNode -> this TestFixtureNode
    #    The parent test owns this fixture variable.
    #
    #  -- Type link (outgoing) --
    #  - OF_TYPE - TestFixtureNode -> ClassNode | EnumNode | InterfaceNode |
    #    UnionNode | NamespaceNode
    #    Links to the actual graph node when the type exists in the
    #    codegraph.  For primitive types (dict, str, int, etc.) there is
    #    no OF_TYPE edge; the ``type_signature`` string carries the type
    #    information instead.
    #    Separate descriptors per target type so that
    #    find_relationship_manager() dispatches correctly.
    #
    #  -- Assertion link (outgoing) --
    #  - CHECKED_BY - TestFixtureNode -> AssertionNode
    #    Indicates that an assertion explicitly checks this fixture.
    #    Intentionally flexible - does not constrain whether the fixture
    #    is the left operand, right operand, or otherwise involved.
    #
    #  -- Step link (outgoing) --
    #  - DEFINED_IN - TestFixtureNode -> TestStepNode
    #    Indicates which test step defines this variable.  Provides
    #    ordering/structure: if a variable depends on a prior step's
    #    output, this edge places it in the correct step.
    # --------------------------------------------------------------------------

    # Incoming composition
    test = RelationshipFrom("codegraph.models.test.TestNode", "COMPOSES")

    # OF_TYPE - separate descriptors per target type
    of_type_class = RelationshipTo(
        "codegraph.models.compound.ClassNode", "OF_TYPE"
    )
    of_type_enum = RelationshipTo(
        "codegraph.models.compound.EnumNode", "OF_TYPE"
    )
    of_type_interface = RelationshipTo(
        "codegraph.models.compound.InterfaceNode", "OF_TYPE"
    )
    of_type_union = RelationshipTo(
        "codegraph.models.compound.UnionNode", "OF_TYPE"
    )
    of_type_namespace = RelationshipTo(
        "codegraph.models.namespace.NamespaceNode", "OF_TYPE"
    )

    # Assertion link
    checked_by = RelationshipTo(
        "codegraph.models.test.AssertionNode", "CHECKED_BY"
    )

    # Step link
    defined_in = RelationshipTo(
        "codegraph.models.test.TestStepNode", "DEFINED_IN"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "tags",
        "description", "type_signature",
    }

    _markdown_keyword = "TestFixture"

    def markdown_body_type(self) -> str | None:
        """TestFixtureNode has no member/enum body section."""
        return None
