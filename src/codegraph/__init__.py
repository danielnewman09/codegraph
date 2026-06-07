"""Codegraph — shared Neo4j codebase graph data model and connection.

Provides atomized neomodel Node models (Class, Interface, Enum, Union, Module,
Method, Attribute, EnumValue, Function, Define, Namespace, File, Parameter),
LayerGraph container, GraphRepository for ORM reads, direct Cypher access
via get_session() and cypher_query(), and constants (kinds, layers, predicates,
schema DDL, language specializations).
"""

from codegraph.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.connection import cypher_query, get_session, verify_connectivity
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
    Layer,
    valid_specializations,
)
from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.repository import GraphRepository
from codegraph.models import (
    ClassNode,
    InterfaceNode,
    EnumNode,
    UnionNode,
    ModuleNode,
    ConceptNode,
    MethodNode,
    AttributeNode,
    EnumValueNode,
    FunctionNode,
    DefineNode,
    NamespaceNode,
    FileNode,
    ParameterNode,
    ImplementationNode,
)

__all__ = [
    # Nodes (neomodel, atomized)
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ModuleNode",
    "ConceptNode",
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
    "FunctionNode",
    "DefineNode",
    "NamespaceNode",
    "FileNode",
    "ParameterNode",
    "ImplementationNode",
    # Graph container
    "LayerGraph",
    "CompositeEntry",
    # Repository
    "GraphRepository",
    # Config
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    # Connection
    "get_session",
    "cypher_query",
    "verify_connectivity",
    # Constants
    "PREDICATES",
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "DEFAULT_PREDICATES",
    "LANGUAGE_SPECIALIZATIONS",
    "LAYERS",
    "Layer",
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
