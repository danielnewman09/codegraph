"""Codegraph-Memory — persistent design memory extension for codegraph.

Registers memory node types (DecisionNode, ConstraintNode, RationaleNode,
AssumptionNode, TradeoffNode, InsightNode) into CodeGraphNode._registry
and provides the MemoryGraph container for querying and persisting
design rationale, constraints, tradeoffs, and insights linked to
codebase knowledge graphs.
"""

from codegraph_memory.models import (
    # Mixin
    MemoryNode,
    # Concrete nodes
    DecisionNode,
    ConstraintNode,
    RationaleNode,
    AssumptionNode,
    TradeoffNode,
    InsightNode,
    # Relationship helpers
    get_linked_code_nodes,
    get_linked_memory_nodes,
    get_all_memory_for_code_node,
)
from codegraph_memory.graph.memory_graph import MemoryGraph, MemoryEntry
from codegraph_memory.schema import apply_schema, MEMORY_CONSTRAINTS_AND_INDEXES

from codegraph_memory.tools.record import record_memory
from codegraph_memory.tools.context import memory_context

__all__ = [
    # Mixin
    "MemoryNode",
    # Concrete nodes
    "DecisionNode",
    "ConstraintNode",
    "RationaleNode",
    "AssumptionNode",
    "TradeoffNode",
    "InsightNode",
    # Relationship helpers
    "get_linked_code_nodes",
    "get_linked_memory_nodes",
    "get_all_memory_for_code_node",
    # Graph container
    "MemoryGraph",
    "MemoryEntry",
    # Schema
    "apply_schema",
    "MEMORY_CONSTRAINTS_AND_INDEXES",
    # Tools
    "record_memory",
    "memory_context",
]