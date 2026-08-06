"""Drift detection — find stale memories after codegraph re-index.

Cross-references memory node targets against current code graph state.
All data access goes through the public backend repository APIs so the
same code runs on Neo4j and SQLite.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend
from codegraph.models.tags import CodeGraphNode

_MEMORY_TO_CODE_RELS = (
    "MOTIVATES", "CONSTRAINS", "EXPLAINS", "ASSUMES", "TRADES_OFF", "INSIGHT_INTO",
)
_ORPHAN_RELS = ("MOTIVATES", "CONSTRAINS", "EXPLAINS")
_MEMORY_TYPES = (
    "DecisionNode", "ConstraintNode", "RationaleNode",
    "AssumptionNode", "TradeoffNode", "InsightNode",
)


def _design_memories(backend, source: str | None) -> list[CodeGraphNode]:
    """Design-tagged memory nodes, optionally filtered by source."""
    nodes = backend.memory.find_by_tag("design")
    if source:
        nodes = [n for n in nodes if getattr(n, "source", None) == source]
    return nodes


def _linked_code(backend, memory: CodeGraphNode) -> list[tuple[CodeGraphNode, str]]:
    """All (code_node, rel_type) pairs a memory links to, via non-meta edges."""
    links: list[tuple[CodeGraphNode, str]] = []
    for edge in backend.get_all_edges_outgoing(memory):
        if edge.relation_type not in _MEMORY_TO_CODE_RELS:
            continue
        target = backend.graph.find_by_uid(edge.target_uid)
        if target is not None:
            links.append((target, edge.relation_type))
    return links


def detect_drift(source: str | None = None) -> list[dict[str, Any]]:
    """Detect stale memories after a codegraph re-index."""
    backend = get_backend()
    findings: list[dict[str, Any]] = []

    # 1. Tag divergence: design-tagged memory → code without design tag
    for memory in _design_memories(backend, source):
        for code, _rel in _linked_code(backend, memory):
            code_tags = list(getattr(code, "tags", None) or [])
            if "design" not in code_tags:
                findings.append({
                    "memory": memory.serialize(),
                    "status": "tag_divergence",
                    "detail": (
                        f"Memory is design-tagged but target code "
                        f"'{code.qualified_name}' no longer has design tag. "
                        f"Current tags: {code_tags}"
                    ),
                })

    # 2. Orphan decisions: design-tagged with no code links
    for memory in _design_memories(backend, source):
        if type(memory).__name__ not in ("DecisionNode", "ConstraintNode", "RationaleNode"):
            continue
        if not _linked_code(backend, memory):
            findings.append({
                "memory": memory.serialize(),
                "status": "orphan",
                "detail": (
                    f"Memory '{memory.qualified_name}' has no linked code node. "
                    "Target code may have been deleted or renamed."
                ),
            })

    # 3. Confidence staleness
    for memory in backend.graph.find_all_by_kind("memory"):
        confidence = getattr(memory, "confidence", None)
        updated_at = getattr(memory, "updated_at", None)
        if confidence is None or confidence >= 0.5 or updated_at is None:
            continue
        if source and getattr(memory, "source", None) != source:
            continue
        for code, _rel in _linked_code(backend, memory):
            findings.append({
                "memory": memory.serialize(),
                "status": "confidence_stale",
                "detail": (
                    f"Memory '{memory.qualified_name}' has confidence "
                    f"{confidence} and was last updated {updated_at}. "
                    f"Linked code: '{code.qualified_name}'. Review whether the "
                    f"low confidence is still warranted."
                ),
            })

    return findings


def confidence_decay(code_node_uid: str, decay_factor: float = 0.9) -> int:
    """Reduce confidence on memories linked to a code node that changed."""
    backend = get_backend()
    count = 0
    for entry in backend.memory.find_for_code_node(code_node_uid):
        memory = entry["node"]
        old_conf = getattr(memory, "confidence", None) or 1.0
        new_conf = max(0.0, old_conf * decay_factor)
        backend.graph.update_properties(memory._uid_value(), {"confidence": new_conf})
        count += 1
    return count


def find_orphan_decisions(source: str | None = None) -> list[dict[str, Any]]:
    """Find decisions whose target code was deleted."""
    backend = get_backend()
    orphans: list[dict[str, Any]] = []
    for memory in _design_memories(backend, source):
        if type(memory).__name__ != "DecisionNode":
            continue
        has_motivates = any(
            e.relation_type == "MOTIVATES"
            for e in backend.get_all_edges_outgoing(memory)
        )
        if not has_motivates:
            orphans.append(memory.serialize())
    return orphans
