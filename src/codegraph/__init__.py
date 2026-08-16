"""Codegraph — backend-agnostic codebase knowledge graph data model.

Provides atomized Node models (Class, Interface, Enum, Union, Module,
Method, Attribute, EnumValue, Function, Define, Namespace, File, Parameter),
LayerGraph container, GraphRepository for data access, and constants
(kinds, tags, predicates, schema DDL, language specializations).
"""

from codegraph.backends import get_backend
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
from codegraph.persistence.repository import GraphRepository
from codegraph.export.plantuml import (export_plantuml, import_plantuml,
                                PlantUMLExporter, PlantUMLImporter,
                                PlantUMLParseError, ParseDiagnostic)
from codegraph.export.markdown import (export_markdown, import_markdown,
                                MarkdownExporter, MarkdownImporter)
from codegraph.export.format import export_graph, import_graph
from codegraph.export.viz import export_html
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
    SourceFragmentNode,
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
    "SourceFragmentNode",
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
    # Backend
    "get_backend",
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
