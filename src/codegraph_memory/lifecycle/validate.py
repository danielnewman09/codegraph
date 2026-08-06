"""Memory validation — cross-reference design vs as-built tags.

Compares design-tagged memories against as-built code to surface
inconsistencies.  All data access goes through the public backend
repository APIs so the same code runs on Neo4j and SQLite.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend
from codegraph_memory.lifecycle.drift import _design_memories, _linked_code


def _memory_nodes(backend, source: str | None) -> list:
    """All memory nodes, optionally filtered by source."""
    nodes = backend.graph.find_all_by_kind("memory")
    if source:
        nodes = [n for n in nodes if getattr(n, "source", None) == source]
    return nodes


def validate_memories(source: str | None = None) -> list[dict[str, Any]]:
    """Cross-reference design-tagged memories against as-built code."""
    backend = get_backend()
    findings: list[dict[str, Any]] = []

    # Design-tagged memories whose linked code lacks as-built
    for memory in _design_memories(backend, source):
        for code, _rel in _linked_code(backend, memory):
            code_tags = list(getattr(code, "tags", None) or [])
            if "as-built" not in code_tags:
                findings.append({
                    "memory": memory.serialize(),
                    "status": "design_not_implemented",
                    "code_qualified_name": code.qualified_name,
                })

    # As-built memories whose linked code lacks design
    for memory in _memory_nodes(backend, source):
        if "as-built" not in (getattr(memory, "tags", None) or []):
            continue
        for code, _rel in _linked_code(backend, memory):
            code_tags = list(getattr(code, "tags", None) or [])
            if "design" not in code_tags:
                findings.append({
                    "memory": memory.serialize(),
                    "status": "undocumented_impl",
                    "code_qualified_name": code.qualified_name,
                })

    return findings


def tag_gap_report(source: str | None = None) -> dict[str, Any]:
    """Summary of design-tagged vs as-built-tagged memories."""
    backend = get_backend()
    nodes = _memory_nodes(backend, source)

    validated = design_only = built_only = 0
    for m in nodes:
        tags = set(getattr(m, "tags", None) or [])
        if {"design", "as-built"} <= tags:
            validated += 1
        elif "design" in tags and "as-built" not in tags:
            design_only += 1
        elif "as-built" in tags and "design" not in tags:
            built_only += 1

    counts: dict[str, Any] = {
        "validated": validated,
        "design_only": design_only,
        "built_only": built_only,
        "total": len(nodes),
    }

    unvalidated = [
        m for m in nodes
        if type(m).__name__ == "DecisionNode"
        and "design" in (getattr(m, "tags", None) or [])
        and "as-built" not in (getattr(m, "tags", None) or [])
    ]
    unvalidated.sort(key=lambda m: getattr(m, "confidence", 0.0) or 0.0, reverse=True)
    counts["unvalidated_decisions"] = [
        {
            "qualified_name": getattr(m, "qualified_name", ""),
            "content": getattr(m, "content", ""),
        }
        for m in unvalidated
    ]

    return counts
