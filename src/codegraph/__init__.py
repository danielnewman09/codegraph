"""Codegraph — shared Neo4j codebase graph data model.

Provides Pydantic models for Nodes (File, Namespace, Compound, Member, Parameter),
edge definitions (CodebaseEdge), and constants (kinds, layers, predicates,
schema DDL).
"""

from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    VISIBILITY_CHOICES,
)
from codegraph.edges import CodebaseEdge
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
    # Constants
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "LAYERS",
    "MEMBER_KINDS",
    "NAMESPACE_KINDS",
    "NODE_KINDS",
    "PREDICATE_TO_REL_TYPE",
    "VISIBILITY_CHOICES",
]
