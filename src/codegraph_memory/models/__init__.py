"""Memory node models — extends codegraph's CodeGraphNode with
design-decision-aware node types.

All concrete subclasses register themselves in CodeGraphNode._registry
via __init_subclass__ when imported.
"""

from codegraph_memory.models.base import MemoryNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.rationale import RationaleNode
from codegraph_memory.models.assumption import AssumptionNode
from codegraph_memory.models.tradeoff import TradeoffNode
from codegraph_memory.models.insight import InsightNode
from codegraph_memory.models.relationships import (
    get_linked_code_nodes,
    get_linked_memory_nodes,
    get_all_memory_for_code_node,
)

__all__ = [
    "MemoryNode",
    "DecisionNode",
    "ConstraintNode",
    "RationaleNode",
    "AssumptionNode",
    "TradeoffNode",
    "InsightNode",
    "get_linked_code_nodes",
    "get_linked_memory_nodes",
    "get_all_memory_for_code_node",
]