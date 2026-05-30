"""Constants for the Neo4j codebase graph layer.

Defines the vocabulary of node kinds, layers, visibility, predicates,
schema DDL, language specializations, and semantic groupings used by
both the ticketing system and Doxygen parser.
"""

# ---------------------------------------------------------------------------
# Subnode-type lists — source of truth; (key, Display) tuples
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[tuple[str, str]] = [
    ("class", "Class"),
    ("struct", "Struct"),
    ("template_class", "Template Class"),
    ("interface", "Interface"),
    ("abstract_class", "Abstract Class"),
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
    "abstract_class", "enum", "enum_class", "union", "type_alias",
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
# Layers — where a node originates
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

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
    "generalizes": "GENERALIZES",
    "realizes": "REALIZES",
    "references": "REFERENCES",
    "invokes": "INVOKES",
    "has_argument": "HAS_ARGUMENT",
    "returns": "RETURNS",
    "type_argument": "TYPE_ARGUMENT",
    "template_param": "TEMPLATE_PARAM",
    "implements": "IMPLEMENTS",
}

PREDICATES: list[str] = list(PREDICATE_TO_REL_TYPE.keys())

DEFAULT_PREDICATES: list[tuple[str, str]] = [
    ("associates", "General association between two entities"),
    ("aggregates", "Whole-part relationship where the part can exist independently. "
     "Specify mechanism for container types (e.g., std::vector, std::list)"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another (e.g., for a header include)"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("references", "One entity holds a reference or pointer to another. "
     "Specify mechanism (e.g., std::unique_ptr, std::shared_ptr, raw_pointer, reference)"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type (method → type)"),
    ("returns", "A method returns a value of the given entity type (method → type)"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
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
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))

# ---------------------------------------------------------------------------
# Schema DDL — constraints and indexes for Neo4j
# ---------------------------------------------------------------------------

CONSTRAINTS_AND_INDEXES: list[str] = [
    # Uniqueness constraints
    "CREATE CONSTRAINT file_refid IF NOT EXISTS FOR (f:File) REQUIRE f.refid IS UNIQUE",
    # Use INDEX instead of CONSTRAINT for refid to allow design-layer nodes
    # (which have no refid) to coexist with as-built/dependency nodes.
    "CREATE INDEX namespace_refid IF NOT EXISTS FOR (n:Namespace) ON (n.refid)",
    "CREATE INDEX compound_refid IF NOT EXISTS FOR (c:Compound) ON (c.refid)",
    "CREATE INDEX member_refid IF NOT EXISTS FOR (m:Member) ON (m.refid)",
    # Lookup indexes
    "CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)",
    "CREATE INDEX compound_name IF NOT EXISTS FOR (c:Compound) ON (c.name)",
    "CREATE INDEX compound_qualified IF NOT EXISTS FOR (c:Compound) ON (c.qualified_name)",
    "CREATE INDEX compound_kind IF NOT EXISTS FOR (c:Compound) ON (c.kind)",
    "CREATE INDEX member_name IF NOT EXISTS FOR (m:Member) ON (m.name)",
    "CREATE INDEX member_qualified IF NOT EXISTS FOR (m:Member) ON (m.qualified_name)",
    "CREATE INDEX member_kind IF NOT EXISTS FOR (m:Member) ON (m.kind)",
    # Layer indexes
    "CREATE INDEX compound_layer IF NOT EXISTS FOR (c:Compound) ON (c.layer)",
    "CREATE INDEX member_layer IF NOT EXISTS FOR (m:Member) ON (m.layer)",
    "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
    # Source provenance
    "CREATE INDEX file_source IF NOT EXISTS FOR (f:File) ON (f.source)",
    "CREATE INDEX compound_source IF NOT EXISTS FOR (c:Compound) ON (c.source)",
    "CREATE INDEX member_source IF NOT EXISTS FOR (m:Member) ON (m.source)",
    "CREATE INDEX namespace_source IF NOT EXISTS FOR (n:Namespace) ON (n.source)",
    # Full-text search
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description]",
]
