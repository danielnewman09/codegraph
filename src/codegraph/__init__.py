"""Codegraph — shared Neo4j codebase graph data model.

Provides Pydantic models for Nodes (File, Namespace, Compound, Member, Parameter),
edge definitions (CodebaseEdge), and constants (kinds, layers, predicates,
schema DDL, language specializations, semantic groupings).
"""

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
from codegraph.neo4j import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
from codegraph.nodes import (
    CompoundNode,
    FileNode,
    MemberNode,
    NamespaceNode,
    ParameterNode,
)

__all__ = [
    # Nodes
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
    # Neo4j connection
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
]
