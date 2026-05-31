"""Codegraph — shared Neo4j codebase graph data model.

Provides neomodel Node models (File, Namespace, Compound, Member, Parameter),
edge definitions (CodebaseEdge), and constants (kinds, layers, predicates,
schema DDL, language specializations, semantic groupings).
"""

from codegraph.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    DEFAULT_PREDICATES,
    LANGUAGE_SPECIALIZATIONS,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KIND_KEYS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    SOURCE_TYPE_KEYS,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    TYPE_KINDS,
    UNCLASSIFIED_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    valid_specializations,
)
from codegraph.edges import CodebaseEdge
from codegraph.graph import CompoundGraph, GraphEdge, NamespaceGraph, OntologyGraph
from codegraph.models import (
    CompoundNode,
    FileNode,
    MemberNode,
    NamespaceNode,
    ParameterNode,
)

__all__ = [
    # Nodes (neomodel)
    "CompoundNode",
    "FileNode",
    "MemberNode",
    "NamespaceNode",
    "ParameterNode",
    # Edges
    "CodebaseEdge",
    "PREDICATES",
    # Graph containers
    "CompoundGraph",
    "GraphEdge",
    "NamespaceGraph",
    "OntologyGraph",
    # Config
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    # Constants
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "DEFAULT_PREDICATES",
    "LANGUAGE_SPECIALIZATIONS",
    "LAYERS",
    "MEMBER_KINDS",
    "NAMESPACE_KINDS",
    "NODE_KIND_KEYS",
    "NODE_KINDS",
    "PREDICATE_TO_REL_TYPE",
    "SOURCE_TYPE_KEYS",
    "SOURCE_TYPES",
    "SUPPORTED_LANGUAGES",
    "TYPE_KINDS",
    "UNCLASSIFIED_KINDS",
    "VALUE_KINDS",
    "VISIBILITY_CHOICES",
    "valid_specializations",
]
