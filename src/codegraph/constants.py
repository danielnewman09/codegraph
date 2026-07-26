"""Constants for the Neo4j codebase graph layer.

Defines the vocabulary of node kinds, tags, visibility, predicates,
schema DDL, language specializations, and semantic groupings used by
both the ticketing system and Doxygen parser.
"""

from typing import Literal

# ---------------------------------------------------------------------------
# Subnode-type lists — source of truth; (key, Display) tuples
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[tuple[str, str]] = [
    ("class", "Class"),
    ("struct", "Struct"),
    ("template_class", "Template Class"),
    ("interface", "Interface"),
    ("abstract_class", "Abstract Class"),
    ("concept", "Concept"),
    ("enum", "Enum"),
    ("enum_class", "Enum Class"),
    ("union", "Union"),
]

MEMBER_KINDS: list[tuple[str, str]] = [
    ("method", "Method"),
    ("variable", "Variable"),
    ("define", "Define"),
    ("enumvalue", "Enum Value"),
    ("function", "Function"),
]

TEST_KINDS: list[tuple[str, str]] = [
    ("test", "Test"),
    ("assertion", "Assertion"),
    ("test_step", "Test Step"),
    ("test_fixture", "Test Fixture"),
]

NAMESPACE_KINDS: list[tuple[str, str]] = [
    ("namespace", "Namespace"),
    ("package", "Package"),
    ("module", "Module"),
]

UNCLASSIFIED_KINDS: list[tuple[str, str]] = [
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
    ("type_parameter", "Type Parameter"),
    ("literal", "Literal Value"),
]

TEST_KIND_KEYS: set[str] = {k for k, _ in TEST_KINDS}

# ---------------------------------------------------------------------------
# Composed node kinds
# ---------------------------------------------------------------------------

NODE_KINDS: list[tuple[str, str]] = (
    COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS
    + TEST_KINDS
)
NODE_KIND_KEYS: set[str] = {k for k, _ in NODE_KINDS}

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS: set[str] = {
    "class", "struct", "template_class", "interface",
    "abstract_class", "concept", "enum", "enum_class", "union", "type_alias",
}
VALUE_KINDS: set[str] = {"method", "variable", "define", "enumvalue", "function"}

TEST_KIND_SET: set[str] = {k for k, _ in TEST_KINDS}

# ---------------------------------------------------------------------------
# Source provenance
# ---------------------------------------------------------------------------

SOURCE_TYPES: list[tuple[str, str]] = [
    ("compound", "Compound"),
    ("member", "Member"),
    ("namespace", "Namespace"),
]
SOURCE_TYPE_KEYS: set[str] = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Tags — provenance labels for nodes
#
# Tags replace the former single-value "layer" field.  A node can carry
# multiple tags (e.g. ["design", "as-built"]), and tags can be added or
# removed independently as the code evolves.
# ---------------------------------------------------------------------------

TAGS: list[str] = ["design", "as-built", "dependency", "scaffold", "requirements", "test"]

Tag = Literal["design", "as-built", "dependency", "scaffold", "requirements", "test"]

# Backward-compatible aliases


# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[tuple[str, str]] = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]

# ---------------------------------------------------------------------------
# Predicates — lowercase names mapped to UPPER_SNAKE_CASE Neo4j rel types
# ---------------------------------------------------------------------------

PREDICATE_TO_REL_TYPE: dict[str, str] = {
    "associates": "ASSOCIATES",
    "aggregates": "AGGREGATES",
    "composes": "COMPOSES",
    "depends_on": "DEPENDS_ON",
    "inherits_from": "INHERITS_FROM",
    "realizes": "REALIZES",
    "references": "REFERENCES",
    "invokes": "INVOKES",
    "has_argument": "HAS_ARGUMENT",
    "returns": "RETURNS",
    "type_argument": "TYPE_ARGUMENT",
    "template_param": "TEMPLATE_PARAM",
    "enforces_concept": "ENFORCES_CONCEPT",
    "implements": "IMPLEMENTS",
    "of_type": "OF_TYPE",
    "checked_by": "CHECKED_BY",
    "defined_in": "DEFINED_IN",
    "verifies": "VERIFIES",
    "left_operand": "LEFT_OPERAND",
    "right_operand": "RIGHT_OPERAND",
    "callee": "CALLEE",
    "caller": "CALLER",
}

PREDICATES: list[str] = list(PREDICATE_TO_REL_TYPE.keys())

DEFAULT_PREDICATES: list[tuple[str, str]] = [
    ("associates", "General association between two entities"),
    ("aggregates", "Whole-part relationship where the part can exist independently. "
     "Specify mechanism for container types (e.g., std::vector, std::list)"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another (e.g., for a header include)"),
    ("inherits_from", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("references", "One entity holds a reference or pointer to another. "
     "Specify mechanism (e.g., std::unique_ptr, std::shared_ptr, raw_pointer, reference)"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type (method → type)"),
    ("returns", "A method returns a value of the given entity type (method → type)"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
    ("enforces_concept", "A type parameter is constrained by a C++20 concept"),
    ("of_type", "A test fixture variable is of the given type (fixture to class/enum/namespace/etc.)"),
    ("checked_by", "A test fixture variable is checked by an assertion (fixture to assertion)"),
    ("defined_in", "A test fixture variable is defined within a test step (fixture to step)"),
    ("verifies", "A test verifies / exercises a code node (test → method, function, class)"),
    ("left_operand", "The subject (left-hand side) of a test assertion comparison"),
    ("right_operand", "The expected value (right-hand side) of a test assertion comparison"),
    ("callee", "A test step calls the target function/method"),
    ("caller", "A test step is invoked by the target entity"),
]

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------

LANGUAGE_SPECIALIZATIONS: dict[str, dict[str, list[str]]] = {
    "cpp": {
        "class": [
            "struct",
            "template_class",
            "abstract_class",
        ],
        "method": [
            "virtual_method",
            "pure_virtual_method",
            "template_method",
            "static_method",
            "const_method",
            "operator_overload",
        ],
        "function": [
            "template_function",
        ],
        "define": [
            "constexpr",
            "const",
        ],
        "enum": [
            "enum_class",
        ],
        "type_alias": [
            "using",
            "typedef",
        ],
        "module": [
            "namespace",
        ],
    },
    "python": {
        "class": [
            "dataclass",
            "namedtuple",
        ],
        "method": [
            "classmethod",
            "staticmethod",
            "property",
            "abstractmethod",
            "async_method",
        ],
        "function": [
            "async_function",
            "generator",
            "decorator",
        ],
        "interface": [
            "protocol",
            "abc",
        ],
        "define": [
            "final",
        ],
        "module": [
            "package",
        ],
    },
    "javascript": {
        "class": [],
        "method": [
            "getter",
            "setter",
            "static_method",
            "async_method",
        ],
        "function": [
            "arrow_function",
            "async_function",
            "generator",
        ],
        "module": [
            "es_module",
            "commonjs_module",
        ],
    },
}

SUPPORTED_LANGUAGES: set[str] = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language: str, kind: str) -> set[str]:
    """Return the set of valid specializations for a language + kind.

    Args:
        language: The programming language (e.g. "cpp", "python").
        kind: The node kind (e.g. "class", "method").

    Returns:
        A set of valid specialization strings for the given language and kind.
    """
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))

# ---------------------------------------------------------------------------
# Schema DDL — constraints and indexes for Neo4j
# ---------------------------------------------------------------------------

CONSTRAINTS_AND_INDEXES: list[str] = [
    # Uniqueness constraints
    "CREATE CONSTRAINT file_refid IF NOT EXISTS FOR (f:File) REQUIRE f.refid IS UNIQUE",
    # uid constraints are auto-created by neomodel for every node type.
    # file_refid constraint above is sufficient; refid is only used by FileNode.
    # Lookup indexes
    "CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)",
    "CREATE INDEX namespace_qualified IF NOT EXISTS FOR (n:Namespace) ON (n.qualified_name)",
    "CREATE INDEX compound_name IF NOT EXISTS FOR (c:Compound) ON (c.name)",
    "CREATE INDEX compound_qualified IF NOT EXISTS FOR (c:Compound) ON (c.qualified_name)",
    "CREATE INDEX compound_kind IF NOT EXISTS FOR (c:Compound) ON (c.kind)",
    "CREATE INDEX member_name IF NOT EXISTS FOR (m:Member) ON (m.name)",
    "CREATE INDEX member_qualified IF NOT EXISTS FOR (m:Member) ON (m.qualified_name)",
    "CREATE INDEX member_kind IF NOT EXISTS FOR (m:Member) ON (m.kind)",
    # Tag indexes (array membership)
    "CREATE INDEX compound_tags IF NOT EXISTS FOR (c:Compound) ON (c.tags)",
    "CREATE INDEX member_tags IF NOT EXISTS FOR (m:Member) ON (m.tags)",
    "CREATE INDEX namespace_tags IF NOT EXISTS FOR (n:Namespace) ON (n.tags)",
    # Source provenance
    "CREATE INDEX file_source IF NOT EXISTS FOR (f:File) ON (f.source)",
    "CREATE INDEX compound_source IF NOT EXISTS FOR (c:Compound) ON (c.source)",
    "CREATE INDEX member_source IF NOT EXISTS FOR (m:Member) ON (m.source)",
    "CREATE INDEX namespace_source IF NOT EXISTS FOR (n:Namespace) ON (n.source)",
    # Full-text search — documentation and signatures on compounds and members
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition]",
    # Full-text search — implementation source code on implementation nodes
    "CREATE FULLTEXT INDEX impl_search IF NOT EXISTS FOR (n:Implementation) ON EACH [n.implementation]",
    # Lookup indexes for Implementation nodes
    "CREATE INDEX impl_qualified IF NOT EXISTS FOR (i:Implementation) ON (i.qualified_name)",
    "CREATE INDEX impl_kind IF NOT EXISTS FOR (i:Implementation) ON (i.kind)",
    # Vector search — documentation embeddings on methods and functions
    "CREATE VECTOR INDEX doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Vector search — implementation embeddings on implementation nodes
    "CREATE VECTOR INDEX impl_embedding IF NOT EXISTS FOR (n:Implementation) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Lookup indexes for Test nodes
    "CREATE INDEX test_qualified IF NOT EXISTS FOR (t:Test) ON (t.qualified_name)",
    "CREATE INDEX test_name IF NOT EXISTS FOR (t:Test) ON (t.name)",
    "CREATE INDEX test_kind IF NOT EXISTS FOR (t:Test) ON (t.kind)",
    "CREATE INDEX test_test_name IF NOT EXISTS FOR (t:Test) ON (t.test_name)",
    "CREATE INDEX test_module IF NOT EXISTS FOR (t:Test) ON (t.test_module)",
    "CREATE INDEX test_tags IF NOT EXISTS FOR (t:Test) ON (t.tags)",
    "CREATE INDEX test_source IF NOT EXISTS FOR (t:Test) ON (t.source)",
    # Lookup indexes for Assertion nodes
    "CREATE INDEX assertion_qualified IF NOT EXISTS FOR (a:Assertion) ON (a.qualified_name)",
    "CREATE INDEX assertion_kind IF NOT EXISTS FOR (a:Assertion) ON (a.kind)",
    "CREATE INDEX assertion_phase IF NOT EXISTS FOR (a:Assertion) ON (a.phase)",
    "CREATE INDEX assertion_tags IF NOT EXISTS FOR (a:Assertion) ON (a.tags)",
    # Lookup indexes for TestStep nodes
    "CREATE INDEX teststep_qualified IF NOT EXISTS FOR (s:TestStep) ON (s.qualified_name)",
    "CREATE INDEX teststep_kind IF NOT EXISTS FOR (s:TestStep) ON (s.kind)",
    "CREATE INDEX teststep_tags IF NOT EXISTS FOR (s:TestStep) ON (s.tags)",
    # Lookup indexes for TestFixture nodes
    "CREATE INDEX testfixture_qualified IF NOT EXISTS FOR (f:TestFixture) ON (f.qualified_name)",
    "CREATE INDEX testfixture_kind IF NOT EXISTS FOR (f:TestFixture) ON (f.kind)",
    "CREATE INDEX testfixture_tags IF NOT EXISTS FOR (f:TestFixture) ON (f.tags)",
    # Full-text search — test descriptions and assertions
    "CREATE FULLTEXT INDEX test_search IF NOT EXISTS FOR (n:Test) ON EACH [n.name, n.qualified_name, n.test_name, n.description]",
    # Vector search — test doc embeddings
    "CREATE VECTOR INDEX test_embedding IF NOT EXISTS FOR (n:Test) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
]
