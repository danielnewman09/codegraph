"""Memory lookup tools — targeted queries for specific memory types.

Implements: constraints_for, decision_chain, insights_for, rationales_for,
assumptions_for, tradeoffs_for, affected_decisions.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend


def constraints_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all constraints governing a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "ConstraintNode"
    ]


def decisions_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all decisions motivating a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "DecisionNode"
    ]


def decision_chain(qualified_name: str) -> list[dict[str, Any]]:
    """Return the SUPERSEDES chain for a decision.

    Walks SUPERSEDES edges from the decision matching *qualified_name*
    to find all older decisions it supersedes.
    """
    backend = get_backend()
    rows, _ = backend.execute_raw(
        "MATCH (d:DecisionNode)-[:SUPERSEDES*0..10]->(older) "
        "WHERE d.qualified_name = $qname "
        "RETURN older",
        {"qname": qualified_name},
    )
    from codegraph_memory.models.relationships import _inflate_code_node
    chain: list[dict[str, Any]] = []
    for row in rows:
        node = _inflate_code_node(row[0])
        if node is not None:
            chain.append(node.serialize())
    return chain


def insights_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all insights learned from a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "InsightNode"
    ]


def rationales_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all rationales explaining a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "RationaleNode"
    ]


def assumptions_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all assumptions underpinning a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "AssumptionNode"
    ]


def tradeoffs_for(qualified_name: str) -> list[dict[str, Any]]:
    """Return all tradeoffs applying to a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["memory"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["memory"]).__name__ == "TradeoffNode"
    ]


def affected_decisions(qualified_name: str) -> list[dict[str, Any]]:
    """Return all decisions linked to this node or its descendants.

    Walks COMPOSES downward and collects all distinct memories.
    """
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    nodes = get_backend().memory.find_linked_to_descendants(uid)
    return [n.serialize() for n in nodes]
