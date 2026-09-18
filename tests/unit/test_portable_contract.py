"""Focused tests for canonical-only LayerGraph identity handling."""

from __future__ import annotations

import pytest

from codegraph import ClassNode
from codegraph.graph import GraphDocumentError, LayerGraph
from codegraph.identity import IdentityScope, resolve_identity_for
from codegraph.models.member import MethodNode

#: The identity scope every node in this module is keyed under.
_SCOPE = IdentityScope.repository("demo", "demo")


def _serialized(node) -> dict:
    """Canonical, portable serialized form of *node* under ``_SCOPE``."""
    node.canonical_key = resolve_identity_for(node, _SCOPE).key()
    data = node.serialize(fields="all")
    for field in (
        "uid", "refid", "compound_refid", "member_refid", "parent_refid",
        "child_refid", "from_refid", "to_refid",
    ):
        data.pop(field, None)
    return data


def _node(name: str, *, description: str = "") -> dict:
    return _serialized(ClassNode(
        name=name,
        qualified_name=f"demo::{name}",
        kind="class",
        source="demo",
        tags=["as-built"],
        brief_description=description,
    ))


def _method(qname: str) -> dict:
    return _serialized(MethodNode(
        name=qname.rsplit("::", 1)[-1].split("(")[0],
        qualified_name=qname,
        kind="function",
        source="demo",
        tags=["as-built"],
        argsstring="()",
    ))


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


def _tree() -> tuple[LayerGraph, dict, dict]:
    """A two-node nested graph: ``demo::Widget`` COMPOSES ``demo::Widget::run()``."""
    parent = _node("Widget")
    child = _method("demo::Widget::run()")
    parent["composes"] = [child]
    return LayerGraph.deserialize([parent]), parent, child


class TestFlatLayoutOption:
    """WP5.2 — an explicit, lossless flat wire layout.

    The flat layout emits each canonical node exactly once and carries every
    ``COMPOSES`` relation as a logical edge, so a composition DAG survives
    serialization.  Nested output stays the default for callers who do not
    ask for a layout.
    """

    def test_flat_layout_is_an_explicit_public_option(self):
        graph, parent, child = _tree()

        document = graph.serialize(fields="all", document=True, layout="flat")

        assert set(document) == {
            "format_version", "identity_version", "entries",
        }
        entries = {e["canonical_key"]: e for e in document["entries"]}
        assert set(entries) == {parent["canonical_key"], child["canonical_key"]}
        assert [
            edge for edge in entries[parent["canonical_key"]]["edges"]
            if edge["relation_type"] == "COMPOSES"
        ] == [{
            "relation_type": "COMPOSES",
            "target_key": child["canonical_key"],
            "target_type": "MethodNode",
        }]
        # The composed node is a record of its own, not nested under a parent.
        assert "composes" not in entries[child["canonical_key"]]
        assert entries[child["canonical_key"]]["edges"] == []

    def test_flat_output_is_a_strict_fixpoint(self):
        graph, _parent, _child = _tree()
        document = graph.serialize(fields="all", document=True, layout="flat")

        restored = LayerGraph.deserialize(document)
        again = restored.serialize(
            fields="all", document=True, layout="flat"
        )

        assert again == document

    def test_default_layout_output_is_unchanged(self):
        graph, _parent, child = _tree()

        default = graph.serialize(fields="all", document=True)
        explicit = graph.serialize(fields="all", document=True, layout="nested")

        assert default == explicit
        nested_children = default["entries"][0]["composes"]
        assert [c["canonical_key"] for c in nested_children] == [
            child["canonical_key"]
        ]

    def test_unknown_layout_is_rejected(self):
        graph, _parent, _child = _tree()
        with pytest.raises(ValueError, match="layout"):
            graph.serialize(layout="sideways")

    def test_duplicate_canonical_composition_child_is_rejected(self):
        """One parent composing the same canonical node twice is refused.

        The two placements carry different bucket keys (as a merge can
        produce), so only the canonical identity reveals the duplication.
        """
        graph, parent, child = _tree()
        entry = next(
            e for e in graph._all_entries()
            if LayerGraph._node_key(e.node) == parent["canonical_key"]
        )
        entry.children["MethodNode"]["duplicate-placement"] = next(
            e for e in graph._all_entries()
            if LayerGraph._node_key(e.node) == child["canonical_key"]
        )

        with pytest.raises(GraphDocumentError, match="duplicate canonical"):
            graph.serialize(fields="all", document=True, layout="flat")

    def test_conflicting_duplicate_endpoint_triples_are_rejected(self):
        """The same ``(relation, target)`` with two target types is refused."""
        target = _node("Widget")
        source = _node("Client")
        source["edges"] = [
            {
                "relation_type": "DEPENDS_ON",
                "target_key": target["canonical_key"],
                "target_type": "ClassNode",
            },
            {
                "relation_type": "DEPENDS_ON",
                "target_key": target["canonical_key"],
                "target_type": "InterfaceNode",
            },
        ]
        graph = LayerGraph.deserialize([source, target])

        with pytest.raises(GraphDocumentError, match="conflicting duplicate"):
            graph.serialize(fields="all", document=True, layout="flat")
