"""Memory lookup tools — targeted queries for specific memory types.

Implements: memory_of, constraints_for, decision_chain, insights_for,
rationales_for, assumptions_for, tradeoffs_for, affected_decisions.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend


def memory_of(qualified_name: str) -> list[dict[str, Any]]:
    """Return all memory nodes linked to a code node."""
    node = get_backend().graph.find_by_qualified_name(qualified_name)
    if node is None:
        return []
    uid = node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
    ]


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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "ConstraintNode"
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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "DecisionNode"
    ]


def decision_chain(qualified_name: str) -> list[dict[str, Any]]:
    """Return decisions linked to a code node, with SUPERSEDES chains.

    Finds all DecisionNodes linked to the code node matching
    *qualified_name*, then walks each decision's SUPERSEDES chain
    and returns the decisions with a ``supersession_chain`` field.
    """
    code_node = get_backend().graph.find_by_qualified_name(qualified_name)
    if code_node is None:
        return []

    uid = code_node._uid_value()
    if not uid:
        return []

    results = get_backend().memory.find_for_code_node(uid)
    decisions = [
        r["node"] for r in results
        if type(r["node"]).__name__ == "DecisionNode"
    ]

    chain: list[dict[str, Any]] = []
    for dec in decisions:
        entry = dec.serialize()
        supersession_chain = _walk_supersedes(dec)
        entry["supersession_chain"] = supersession_chain
        chain.append(entry)

    return chain


def _walk_supersedes(decision) -> list[dict[str, Any]]:
    """Walk the SUPERSEDES chain from *decision* and serialize each."""
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    current = decision
    while current is not None:
        for older in current.supersedes.all():
            if older.uid in visited:
                continue
            visited.add(older.uid)
            chain.append(older.serialize())
            current = older
            break  # follow one level per iteration
        else:
            break  # no more superseded decisions
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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "InsightNode"
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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "RationaleNode"
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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "AssumptionNode"
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
        r["node"].serialize() | {"relation": r["rel_type"]}
        for r in results
        if type(r["node"]).__name__ == "TradeoffNode"
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
