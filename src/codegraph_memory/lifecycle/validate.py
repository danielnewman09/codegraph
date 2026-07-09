"""Memory validation — cross-reference design vs as-built tags.

Compares design-tagged memories against as-built code to surface:
  - Design decisions not yet reflected in implementation
  - Implementations that lack design documentation
  - Inconsistencies between decision content and code structure
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph_memory.models.relationships import _inflate_code_node


def validate_memories(source: str | None = None) -> list[dict[str, Any]]:
    """Cross-reference design-tagged memories against as-built code.

    Finds memory nodes that have "design" in their tags but whose linked
    code nodes do NOT have "as-built" in their tags — meaning the design
    decision hasn't been implemented yet (a TODO item).

    Also finds memory nodes tagged only "as-built" (observed but never
    designed) — implementation without design documentation.

    Args:
        source: Optional source project filter. When provided, only
            memories from this source are checked.

    Returns:
        A list of validation findings, each with keys:
        - ``memory``: serialized memory node
        - ``status``: "design_not_implemented" or "undocumented_impl"
        - ``code_qualified_name``: the linked code node's qualified_name
    """
    source_filter = "AND m.source = $source" if source else ""
    params: dict[str, Any] = {}
    if source:
        params["source"] = source

    # Design-tagged memories whose linked code lacks as-built
    results, _ = db.cypher_query(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'design' IN m.tags "
        "AND NOT 'as-built' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name",
        params,
    )
    findings: list[dict[str, Any]] = []
    for row in results:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "design_not_implemented",
                "code_qualified_name": row[1],
            })

    # As-built memories whose linked code lacks design
    results, _ = db.cypher_query(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'as-built' IN m.tags "
        "AND NOT 'design' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name",
        params,
    )
    for row in results:
        memory = _inflate_code_node(row[0])
        if memory:
            findings.append({
                "memory": memory.serialize(),
                "status": "undocumented_impl",
                "code_qualified_name": row[1],
            })

    return findings


def tag_gap_report(source: str | None = None) -> dict[str, Any]:
    """Summary of design-tagged vs as-built-tagged memories.

    Provides counts of:
    - Design-only memories (design tag but not as-built)
    - Validated memories (both design and as-built)
    - As-built-only memories (as-built tag but not design)
    - Design memories whose code targets haven't been built

    Args:
        source: Optional source project filter.

    Returns:
        A dict with count fields and lists of unvalidated decision names.
    """
    source_filter = "WHERE m.source = $source" if source else ""
    params: dict[str, Any] = {}
    if source:
        params["source"] = source

    # Count by tag combination
    results, _ = db.cypher_query(
        "MATCH (m) "
        "WHERE (m:DecisionNode OR m:ConstraintNode OR m:RationaleNode "
        "OR m:AssumptionNode OR m:TradeoffNode OR m:InsightNode) "
        + ("AND m.source = $source" if source else "") +
        " RETURN "
        "sum(CASE WHEN 'design' IN m.tags AND 'as-built' IN m.tags THEN 1 ELSE 0 END) AS validated, "
        "sum(CASE WHEN 'design' IN m.tags AND NOT 'as-built' IN m.tags THEN 1 ELSE 0 END) AS design_only, "
        "sum(CASE WHEN 'as-built' IN m.tags AND NOT 'design' IN m.tags THEN 1 ELSE 0 END) AS built_only, "
        "count(m) AS total",
        params,
    )

    if results:
        row = results[0]
        counts = {
            "validated": row[0] or 0,
            "design_only": row[1] or 0,
            "built_only": row[2] or 0,
            "total": row[3] or 0,
        }
    else:
        counts = {"validated": 0, "design_only": 0, "built_only": 0, "total": 0}

    # Unvalidated decisions (design but not as-built)
    results, _ = db.cypher_query(
        "MATCH (m:DecisionNode) "
        "WHERE 'design' IN m.tags AND NOT 'as-built' IN m.tags "
        + ("AND m.source = $source" if source else "") +
        " RETURN m.qualified_name AS qname, m.content AS content "
        "ORDER BY m.confidence DESC",
        params,
    )
    counts["unvalidated_decisions"] = [
        {"qualified_name": row[0], "content": row[1]}
        for row in results
    ]

    return counts