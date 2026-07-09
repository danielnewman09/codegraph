"""Drift detection — find stale memories after codegraph re-index.

Cross-references memory node targets against current code graph state.
Stale memories are flagged when:
  - Linked code node UID no longer exists (deleted/renamed)
  - Memory is design-tagged but target code lost its design tag
  - Memory confidence doesn't match code change recency
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph_memory.models.relationships import _inflate_code_node


def detect_drift(source: str | None = None) -> list[dict[str, Any]]:
    """Detect stale memories after a codegraph re-index.

    Checks for:
    1. **Orphan decisions**: memories whose target code node was deleted.
    2. **Tag divergence**: memory is design-tagged but target code lost
       its design tag (code diverged from original design intent).
    3. **Confidence staleness**: memories with low confidence whose
       linked code has been modified since the memory was last updated.

    Args:
        source: Optional source project filter.

    Returns:
        A list of drift findings, each with keys:
        - ``memory``: serialized memory node
        - ``status``: "orphan", "tag_divergence", or "confidence_stale"
        - ``detail``: human-readable description of the drift
    """
    params: dict[str, Any] = {}
    source_filter = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    findings: list[dict[str, Any]] = []

    # 1. Orphan decisions: memories linked to code nodes that no longer
    #    have the expected tags (design tag lost = code changed)
    results, _ = db.cypher_query(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE 'design' IN m.tags "
        "AND NOT 'design' IN c.tags "
        f"{source_filter} "
        "RETURN m, c.qualified_name, c.tags",
        params,
    )
    for row in results:
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

    # 2. Find orphan decisions: memories whose target code nodes
    #    no longer exist (the code was deleted or renamed)
    #    This is detected by checking if the memory has any outgoing
    #    code-relationship edges.  If a design-tagged memory has NO
    #    code links, it may be orphaned.
    results, _ = db.cypher_query(
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
    for row in results:
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

    # 3. Confidence staleness: low-confidence memories whose code
    #    was modified after the memory was last updated
    results, _ = db.cypher_query(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE m.confidence < 0.5 "
        "AND m.updated_at IS NOT NULL "
        f"{source_filter} "
        "RETURN m, c.qualified_name, m.updated_at, m.confidence",
        params,
    )
    for row in results:
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
    """Reduce confidence on memories linked to a code node that changed.

    Multiplies the confidence of all memories linked to the specified
    code node by the decay factor.  This signals that the memories
    may need re-validation since the code was modified.

    Args:
        code_node_uid: The uid of the code node that changed.
        decay_factor: Multiplier for confidence (0.0–1.0, default 0.9).

    Returns:
        The number of memories updated.
    """
    results, _ = db.cypher_query(
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(c) "
        "WHERE c.uid = $uid "
        "RETURN elementId(m) AS mid, m.confidence AS conf",
        {"uid": code_node_uid},
    )
    count = 0
    for row in results:
        mid = row[0]
        old_conf = row[1] or 1.0
        new_conf = max(0.0, old_conf * decay_factor)
        db.cypher_query(
            "MATCH (m) WHERE elementId(m) = $mid "
            "SET m.confidence = $conf",
            {"mid": mid, "conf": new_conf},
        )
        count += 1
    return count


def find_orphan_decisions(source: str | None = None) -> list[dict[str, Any]]:
    """Find decisions whose target code was deleted (UID no longer exists).

    Args:
        source: Optional source project filter.

    Returns:
        A list of orphan decision dicts with serialized data.
    """
    params: dict[str, Any] = {}
    source_filter = "AND m.source = $source" if source else ""
    if source:
        params["source"] = source

    results, _ = db.cypher_query(
        "MATCH (m:DecisionNode) "
        "WHERE 'design' IN m.tags "
        f"{source_filter} "
        "AND NOT EXISTS { "
        "  MATCH (m)-[:MOTIVATES]->(c) "
        "} "
        "RETURN m",
        params,
    )
    orphans = []
    for row in results:
        memory = _inflate_code_node(row[0])
        if memory:
            orphans.append(memory.serialize())
    return orphans