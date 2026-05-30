"""Constants for the Neo4j codebase graph layer.

Defines the vocabulary of node kinds, layers, visibility, predicates,
and schema DDL used by both the ticketing system and Doxygen parser.
"""

# ---------------------------------------------------------------------------
# Node kinds — organized by Neo4j node label
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[str] = [
    "class",
    "struct",
    "template_class",
    "interface",
    "abstract_class",
    "enum",
    "enum_class",
]

MEMBER_KINDS: list[str] = [
    "method",
    "attribute",
    "constant",
    "enum_value",
    "function",
]

NAMESPACE_KINDS: list[str] = [
    "namespace",
    "package",
    "module",
]

NODE_KINDS: list[str] = COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS

# ---------------------------------------------------------------------------
# Layers — where a node originates
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[str] = ["public", "private", "protected"]

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
