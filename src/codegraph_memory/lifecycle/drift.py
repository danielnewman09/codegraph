"""Drift detection — find stale memories after codegraph re-index.

Cross-references memory node targets against current code graph state.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend
from codegraph_memory.models.relationships import _inflate_code_node


def detect_drift(source: str | None = None) -> list[dict[str, Any]]:
    """Detect stale memories after a codegraph re-index."""
    backend = get_backend()
    params: dict[str, Any] = {}
    source_filter = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    findings: list[dict[str, Any]] = []

    # 1. Tag divergence: design-tagged memory → code without design tag
    rows, _ = backend.execute_raw(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'design' IN m.tags "
        "AND NOT 'design' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name, c.tags",
        params,
    )
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "tag_divergence",
                "detail": (
                    f"Memory is design-tagged but target code "
                    f"'{row[1]}' no longer has design tag. "
                    f"Current tags: {list(row[2]) if row[2] else []}"
                ),
            })

    # 2. Orphan decisions: design-tagged with no code links
    rows, _ = backend.execute_raw(
        "MATCH (m) "
        "WHERE (m:DecisionNode OR m:ConstraintNode OR m:RationaleNode) "
        "AND 'design' IN m.tags "
        f"{source_filter} "
        "AND NOT EXISTS { "
        "  MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS]->(c) "
        "} "
        "RETURN m",
        params,
    )
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "orphan",
                "detail": (
                    f"Memory '{memory.qualified_name}' has no linked code node. "
                    "Target code may have been deleted or renamed."
                ),
            })

    # 3. Confidence staleness
    rows, _ = backend.execute_raw(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE m.confidence < 0.5 "
        "AND m.updated_at IS NOT NULL "
        f"{source_filter} "
        "RETURN m, c.qualified_name, m.updated_at, m.confidence",
        params,
    )
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "confidence_stale",
                "detail": (
                    f"Memory '{memory.qualified_name}' has confidence "
                    f"{row[3]} and was last updated {row[2]}. "
                    f"Linked code: '{row[1]}'. Review whether the "
                    f"low confidence is still warranted."
                ),
            })

    return findings


def confidence_decay(code_node_uid: str, decay_factor: float = 0.9) -> int:
    """Reduce confidence on memories linked to a code node that changed."""
    backend = get_backend()
    rows, _ = backend.execute_raw(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE c.uid = $uid "
        "RETURN elementId(m) AS mid, m.confidence AS conf",
        {"uid": code_node_uid},
    )
    count = 0
    for row in rows:
        mid = row[0]
        old_conf = row[1] or 1.0
        new_conf = max(0.0, old_conf * decay_factor)
        backend.execute_raw(
            "MATCH (m) WHERE elementId(m) = $mid "
            "SET m.confidence = $conf",
            {"mid": mid, "conf": new_conf},
        )
        count += 1
    return count


def find_orphan_decisions(source: str | None = None) -> list[dict[str, Any]]:
    """Find decisions whose target code was deleted."""
    params: dict[str, Any] = {}
    source_filter = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    backend = get_backend()
    rows, _ = backend.execute_raw(
        "MATCH (m:DecisionNode) "
        "WHERE 'design' IN m.tags "
        f"{source_filter} "
        "AND NOT EXISTS { "
        "  MATCH (m)-[:MOTIVATES]->(c) "
        "} "
        "RETURN m",
        params,
    )
    orphans: list[dict[str, Any]] = []
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            orphans.append(memory.serialize())
    return orphans
