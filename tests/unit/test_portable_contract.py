"""Focused tests for canonical-only LayerGraph identity handling."""

from __future__ import annotations

import pytest

from codegraph import ClassNode
from codegraph.graph import LayerGraph
from codegraph.identity import IdentityScope, resolve_identity_for


def _node(name: str, *, description: str = "") -> dict:
    node = ClassNode(
        name=name,
        qualified_name=f"demo::{name}",
        kind="class",
        source="demo",
        tags=["as-built"],
        brief_description=description,
    )
    node.canonical_key = resolve_identity_for(
        node, IdentityScope.repository("demo", "demo")
    ).key()
    data = node.serialize(fields="all")
    for field in (
        "uid", "refid", "compound_refid", "member_refid", "parent_refid",
        "child_refid", "from_refid", "to_refid",
    ):
        data.pop(field, None)
    return data


def test_canonical_target_key_resolves_reference():
    left = _node("Left")
    right = _node("Right")
    left["edges"] = [{
        "relation_type": "DEPENDS_ON",
        "target_key": right["canonical_key"],
        "target_type": "ClassNode",
    }]
    graph = LayerGraph.deserialize([left, right])
    left_entry = next(
        entry for entry in graph._all_entries()
        if entry.node.qualified_name == "demo::Left"
    )
    assert left_entry.references == [
        ("DEPENDS_ON", right["canonical_key"], "ClassNode")
    ]


def test_distinct_nodes_with_duplicate_canonical_key_are_rejected():
    first = _node("Widget", description="one")
    second = _node("Widget", description="two")
    with pytest.raises(ValueError, match="identity conflict|already claimed"):
        LayerGraph.deserialize([first, second])
