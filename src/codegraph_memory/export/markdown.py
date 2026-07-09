"""Markdown export — render memory nodes as ADR-style documents.

Converts DecisionNode + linked RationaleNode/TradeoffNode trees into
Architecture Decision Records, suitable for documentation or agent
context windows.  Also provides module-level memory summaries.
"""

from __future__ import annotations

from neomodel import db

from codegraph_memory.models.relationships import _inflate_code_node


def export_adr(
    decision_qualified_name: str,
    depth: int = 2,
) -> str:
    """Export a DecisionNode as an Architecture Decision Record.

    Renders the decision and all linked rationale, tradeoffs, and
    assumptions as a structured markdown document.

    Args:
        decision_qualified_name: The qualified_name of the DecisionNode.
        depth: Starting heading level (default 2 = ``##``).

    Returns:
        A markdown string representing the ADR.
    """
    # Fetch the decision
    results, _ = db.cypher_query(
        "MATCH (d:DecisionNode {qualified_name: $qname}) RETURN d",
        {"qname": decision_qualified_name},
    )
    if not results:
        return f"<!-- Decision '{decision_qualified_name}' not found -->"

    decision = _inflate_code_node(results[0][0])
    if decision is None:
        return f"<!-- Could not inflate decision '{decision_qualified_name}' -->"

    lines: list[str] = []
    h = "#" * depth

    # ── Header ─────────────────────────────────────────────────────
    lines.append(f"{h} Decision: `{decision.qualified_name}`")
    lines.append("")
    lines.append(f"**Status:** {', '.join(decision.tags) if decision.tags else 'unknown'}")
    lines.append(f"**Confidence:** {decision.confidence:.0%}")
    if decision.decided_at:
        lines.append(f"**Decided:** {decision.decided_at}")
    if decision.updated_at:
        lines.append(f"**Updated:** {decision.updated_at}")
    lines.append("")

    # ── Context ─────────────────────────────────────────────────────
    lines.append(f"{h}# Context")
    lines.append("")
    lines.append(decision.content)
    lines.append("")

    # ── Motivated code ──────────────────────────────────────────────
    from codegraph_memory.models.relationships import get_linked_code_nodes
    motivated = get_linked_code_nodes(decision, "MOTIVATES")
    if motivated:
        lines.append(f"{h}# Motivated Code")
        lines.append("")
        for node in motivated:
            qname = getattr(node, "qualified_name", node.name)
            lines.append(f"- `{qname}`")
        lines.append("")

    # ── Rationale ──────────────────────────────────────────────────
    results, _ = db.cypher_query(
        "MATCH (r:RationaleNode)-[:REFINES]->(d:DecisionNode) "
        "WHERE d.qualified_name = $qname RETURN r",
        {"qname": decision_qualified_name},
    )
    rationales = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    if rationales:
        lines.append(f"{h}# Rationale")
        lines.append("")
        for rat in rationales:
            lines.append(f"**{rat.qualified_name}** (confidence: {rat.confidence:.0%})")
            lines.append("")
            lines.append(rat.content)
            lines.append("")

    # ── Tradeoffs ──────────────────────────────────────────────────
    # Find tradeoffs linked to the same code nodes as the decision
    if motivated:
        motivated_uids = [n.uid for n in motivated if hasattr(n, "uid")]
        if motivated_uids:
            results, _ = db.cypher_query(
                "MATCH (t:TradeoffNode)-[:TRADES_OFF]->(c) "
                "WHERE c.uid IN $uids RETURN DISTINCT t",
                {"uids": motivated_uids},
            )
            tradeoffs = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
            if tradeoffs:
                lines.append(f"{h}# Tradeoffs")
                lines.append("")
                for to in tradeoffs:
                    lines.append(f"**{to.qualified_name}** (confidence: {to.confidence:.0%})")
                    lines.append("")
                    lines.append(to.content)
                    lines.append("")

    # ── Supersession chain ─────────────────────────────────────────
    results, _ = db.cypher_query(
        "MATCH (d:DecisionNode)-[:SUPERSEDES]->(older) "
        "WHERE d.qualified_name = $qname "
        "RETURN older.qualified_name, older.content, older.decided_at, older.tags "
        "ORDER BY older.decided_at DESC",
        {"qname": decision_qualified_name},
    )
    if results:
        lines.append(f"{h}# Superseded By")
        lines.append("")
        for row in results:
            lines.append(f"### `{row[0]}`")
            lines.append("")
            lines.append(row[1] or "")
            if row[2]:
                lines.append(f"*Decided: {row[2]}*")
            lines.append("")

    return "\n".join(lines)


def export_memory_summary(
    qualified_name: str,
    depth: int = 2,
) -> str:
    """Export all memory for a code node as a design context document.

    Aggregates all memory nodes linked to the given code node and
    renders them as a structured markdown summary.

    Args:
        qualified_name: The qualified_name of the code node.
        depth: Starting heading level (default 2 = ``##``).

    Returns:
        A markdown string summarizing all linked memories.
    """
    from codegraph_memory.graph.memory_graph import MemoryGraph

    graph = MemoryGraph.for_code_node(qualified_name)
    lines: list[str] = []
    h = "#" * depth

    lines.append(f"{h} Memory for `{qualified_name}`")
    lines.append("")

    if not graph.entries:
        lines.append("*No memory nodes linked to this code node.*")
        return "\n".join(lines)

    # Group by relationship type
    by_type: dict[str, list] = {}
    for entry in graph.entries:
        key = entry.relation_type or "LINKED"
        by_type.setdefault(key, []).append(entry)

    type_labels = {
        "MOTIVATES": "Decisions",
        "CONSTRAINS": "Constraints",
        "EXPLAINS": "Rationale",
        "ASSUMES": "Assumptions",
        "TRADES_OFF": "Tradeoffs",
        "INSIGHT_INTO": "Insights",
    }

    for rel_type, label in type_labels.items():
        entries = by_type.get(rel_type, [])
        if not entries:
            continue
        lines.append(f"{h}# {label}")
        lines.append("")
        for entry in entries:
            mem = entry.memory
            lines.append(f"**{mem.qualified_name}** "
                        f"(confidence: {mem.confidence:.0%}, tags: {', '.join(mem.tags) if mem.tags else 'none'})")
            lines.append("")
            lines.append(mem.content)
            lines.append("")

    return "\n".join(lines)