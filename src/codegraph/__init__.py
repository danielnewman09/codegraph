"""Codegraph — shared Neo4j codebase graph data model and connection.

Provides atomized neomodel Node models (Class, Interface, Enum, Union, Module,
Method, Attribute, EnumValue, Function, Define, Namespace, File, Parameter),
LayerGraph container, GraphRepository for ORM reads, direct Cypher access
via get_session() and cypher_query(), and constants (kinds, tags, predicates,
schema DDL, language specializations).
"""

from codegraph.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.connection import cypher_query, get_session, verify_connectivity
from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    DEFAULT_PREDICATES,
    LANGUAGE_SPECIALIZATIONS,
    TAGS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KIND_KEYS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    SOURCE_TYPE_KEYS,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    Tag,
    TYPE_KINDS,
    UNCLASSIFIED_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    valid_specializations,
)
from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.repository import GraphRepository
from codegraph.plantuml import (export_plantuml, import_plantuml,
                                PlantUMLExporter, PlantUMLImporter,
                                PlantUMLParseError, ParseDiagnostic)
from codegraph.markdown import (export_markdown, import_markdown,
                                MarkdownExporter, MarkdownImporter)
from codegraph.format import export_graph, import_graph
from codegraph.viz import export_html
from codegraph.tools import CodeGraphDispatcher, ToolDispatcher, create_dispatcher
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
    # PlantUML
    "export_plantuml",
    "import_plantuml",
    "PlantUMLExporter",
    "PlantUMLImporter",
    "PlantUMLParseError",
    "ParseDiagnostic",
    # Markdown
    "export_markdown",
    "import_markdown",
    "MarkdownExporter",
    "MarkdownImporter",
    # Unified format
    "export_graph",
    "import_graph",
    # HTML visualisation
    "export_html",
    # Tools
    "CodeGraphDispatcher",
    "ToolDispatcher",
    "create_dispatcher",
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
    "TAGS",
    "Tag",
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
