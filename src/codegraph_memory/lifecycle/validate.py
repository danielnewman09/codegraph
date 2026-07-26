"""Memory validation — cross-reference design vs as-built tags.

Compares design-tagged memories against as-built code to surface
inconsistencies.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend
from codegraph_memory.models.relationships import _inflate_code_node


def validate_memories(source: str | None = None) -> list[dict[str, Any]]:
    """Cross-reference design-tagged memories against as-built code."""
    backend = get_backend()
    params: dict[str, Any] = {}
    source_filter = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    findings: list[dict[str, Any]] = []

    # Design-tagged memories whose linked code lacks as-built
    rows, _ = backend.execute_raw(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'design' IN m.tags "
        "AND NOT 'as-built' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name",
        params,
    )
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "design_not_implemented",
                "code_qualified_name": row[1],
            })

    # As-built memories whose linked code lacks design
    rows, _ = backend.execute_raw(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'as-built' IN m.tags "
        "AND NOT 'design' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name",
        params,
    )
    for row in rows:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "undocumented_impl",
                "code_qualified_name": row[1],
            })

    return findings


def tag_gap_report(source: str | None = None) -> dict[str, Any]:
    """Summary of design-tagged vs as-built-tagged memories."""
    backend = get_backend()
    params: dict[str, Any] = {}
    source_clause = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    rows, _ = backend.execute_raw(
        "MATCH (m) "
        "WHERE (m:DecisionNode OR m:ConstraintNode OR m:RationaleNode "
        "OR m:AssumptionNode OR m:TradeoffNode OR m:InsightNode) "
        + source_clause +
        " RETURN "
        "sum(CASE WHEN 'design' IN m.tags AND 'as-built' IN m.tags THEN 1 ELSE 0 END) AS validated, "
        "sum(CASE WHEN 'design' IN m.tags AND NOT 'as-built' IN m.tags THEN 1 ELSE 0 END) AS design_only, "
        "sum(CASE WHEN 'as-built' IN m.tags AND NOT 'design' IN m.tags THEN 1 ELSE 0 END) AS built_only, "
        "count(m) AS total",
        params,
    )

    if rows:
        r = rows[0]
        counts = {
            "validated": r["validated"] or 0,
            "design_only": r["design_only"] or 0,
            "built_only": r["built_only"] or 0,
            "total": r["total"] or 0,
        }
    else:
        counts = {"validated": 0, "design_only": 0, "built_only": 0, "total": 0}

    rows, _ = backend.execute_raw(
        "MATCH (m:DecisionNode) "
        "WHERE 'design' IN m.tags AND NOT 'as-built' IN m.tags "
        + source_clause +
        " RETURN m.qualified_name AS qname, m.content AS content "
        "ORDER BY m.confidence DESC",
        params,
    )
    counts["unvalidated_decisions"] = [
        {"qualified_name": r["qname"], "content": r["content"]}
        for r in rows
    ]

    return counts
