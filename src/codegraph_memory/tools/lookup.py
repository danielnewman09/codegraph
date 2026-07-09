"""Memory lookup tools — retrieve memories linked to code nodes.

Implements: memory_of, constraints_for, decision_chain, insights_for,
rationales_for, assumptions_for, tradeoffs_for, affected_decisions.
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph.models.tags import CodeGraphNode
from codegraph_memory.models.relationships import _inflate_code_node


def memory_of(qualified_name: str) -> list[dict[str, Any]]:
    """Return all memory nodes linked to a code node by qualified_name.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of dicts, each with the memory node's serialized data
        plus the relationship type and linked code node info.
    """
    from codegraph_memory.graph.memory_graph import MemoryGraph

    graph = MemoryGraph.for_code_node(qualified_name)
    return graph.serialize()


def constraints_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all constraints governing a code node.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized ConstraintNode dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (c:ConstraintNode)-[:CONSTRAINS]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN c ORDER BY c.confidence DESC",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]


def decision_chain(qualified_name: str) -> list[dict[str, Any]]:
    """Return decisions linked to a code node, plus their SUPERSEDES chain.

    Traverses SUPERSEDES edges to show the evolution of decisions over time.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of dicts, each with a decision and its supersession chain.
    """
    # First, find all decisions linked to the code node
    results, _ = db.cypher_query(
        "MATCH (d:DecisionNode)-[:MOTIVATES]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN d ORDER BY d.decided_at DESC",
        {"qname": qualified_name},
    )
    decisions = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    output: list[dict[str, Any]] = []
    for decision in decisions:
        entry = decision.serialize()
        # Traverse SUPERSEDES chain (both directions)
        chain_results, _ = db.cypher_query(
            "MATCH (d:DecisionNode)-[:SUPERSEDES*0..10]->(older) "
            "WHERE elementId(d) = $did "
            "RETURN older.qualified_name AS qname, older.content AS content, "
            "older.decided_at AS decided_at, older.tags AS tags "
            "ORDER BY older.decided_at DESC",
            {"did": db.parse_element_id(decision.element_id)},
        )
        entry["supersession_chain"] = [
            {
                "qualified_name": row[0],
                "content": row[1],
                "decided_at": str(row[2]) if row[2] else None,
                "tags": list(row[3]) if row[3] else [],
            }
            for row in chain_results
        ]
        output.append(entry)
    return output


def insights_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all insights learned from a code node.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized InsightNode dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (i:InsightNode)-[:INSIGHT_INTO]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN i ORDER BY i.decided_at DESC",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]


def rationales_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all rationales explaining a code node.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized RationaleNode dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (r:RationaleNode)-[:EXPLAINS]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN r ORDER BY r.decided_at DESC",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]


def assumptions_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all assumptions underpinning a code node.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized AssumptionNode dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (a:AssumptionNode)-[:ASSUMES]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN a ORDER BY a.confidence ASC",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]


def tradeoffs_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all tradeoffs applying to a code node.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized TradeoffNode dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (t:TradeoffNode)-[:TRADES_OFF]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN t",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]


def affected_decisions(qualified_name: str) -> list[dict[str, Any]]:
    """Return all memories linked to a code node or its composed children.

    Traverses COMPOSES edges to find memories linked to any descendant.

    Args:
        qualified_name: The qualified_name of the code node.

    Returns:
        A list of serialized memory node dicts.
    """
    results, _ = db.cypher_query(
        "MATCH (target)<-[:COMPOSES*0..10]-(parent) "
        "WHERE parent.qualified_name = $qname "
        "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(target) "
        "RETURN DISTINCT m",
        {"qname": qualified_name},
    )
    nodes = [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]
    return [n.serialize() for n in nodes]