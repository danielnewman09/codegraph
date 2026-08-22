"""Shared fixtures for per-builder context tests.

Codegen context tests are pure Python (D2): they deserialize small
hand-built graph dicts into LayerGraphs (no backend) and call the
builders directly with a fresh BuildState.
"""

from __future__ import annotations

import pytest

from codegraph.codegen.context import BuildState
from codegraph.graph import LayerGraph


@pytest.fixture
def deserialize_graph():
    def _deserialize(data):
        return LayerGraph.deserialize(data)

    return _deserialize


@pytest.fixture
def make_state(deserialize_graph):
    def _make(data):
        graph = deserialize_graph(data)
        return graph, BuildState(graph=graph, flat=graph._flat_index())

    return _make


@pytest.fixture
def find_entry():
    def _find(graph, *, type_name=None, name=None):
        for entry in graph._all_entries():
            if type_name and type(entry.node).__name__ != type_name:
                continue
            if name and entry.node.name != name:
                continue
            return entry
        raise LookupError(f"entry not found: type={type_name} name={name}")

    return _find


def node_dict(**overrides):
    """Base serialized-node dict with identity fields pre-filled."""
    data = {
        "type": "ClassNode",
        "name": "Thing",
        "qualified_name": "ns::Thing",
        "canonical_key": "cg:v1:repository:codegraph-suite%2Fcodegraph:class:qualified_name=ns%3A%3AThing",
        "kind": "class",
        "source": "test",
        "tags": ["design"],
    }
    data.update(overrides)
    return data
