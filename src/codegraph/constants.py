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

# ---------------------------------------------------------------------------
# Composed node kinds
# ---------------------------------------------------------------------------

NODE_KINDS: list[tuple[str, str]] = (
    COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS
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

TAGS: list[str] = ["design", "as-built", "dependency", "scaffold", "codebase"]

Tag = Literal["design", "as-built", "dependency", "scaffold", "codebase"]

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
    # Use INDEX instead of CONSTRAINT for refid to allow design-tag nodes
    # (which have no refid) to coexist with as-built/dependency nodes.
    "CREATE INDEX namespace_refid IF NOT EXISTS FOR (n:Namespace) ON (n.refid)",
    "CREATE INDEX compound_refid IF NOT EXISTS FOR (c:Compound) ON (c.refid)",
    "CREATE INDEX member_refid IF NOT EXISTS FOR (m:Member) ON (m.refid)",
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
]
