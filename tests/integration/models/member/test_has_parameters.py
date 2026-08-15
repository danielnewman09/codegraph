"""Integration test: HAS_PARAMETER edge round-trip through the backend.

Phase 0 codegen blocker — the context builder must be able to resolve a
member's parameter list in order.  This pins the full path:

    MethodNode/FunctionNode ─[:HAS_PARAMETER]→ ParameterNode

- connect via the ``has_parameters`` relationship manager
- backend lists the outgoing edges
- ``node.serialize()`` carries the edges
- ``LayerGraph.from_backend`` retains them as references (codegen reads
  the graph through LayerGraph, not raw backend calls)

Runs against the default backend (in-memory SQLite under the standard
test plugin; Neo4j when CODEGRAPH_BACKEND=neo4j).
"""

import pytest

from codegraph.backends import get_backend
from codegraph.graph import LayerGraph
from codegraph.models.member import FunctionNode, MethodNode
from codegraph.models.parameter import ParameterNode


def _make_member_and_params(node_cls, member_name, param_specs):
    member = node_cls(
        name=member_name,
        kind="method" if node_cls is MethodNode else "function",
        qualified_name=f"cpp_sqlite::{member_name}",
        source="test",
        tags=["as-built"],
    ).save()
    params = []
    for spec in param_specs:
        param = ParameterNode(
            name=spec["name"],
            type=spec["type"],
            position=spec["position"],
            default_value=spec.get("default", ""),
            source="test",
            tags=["as-built"],
        ).save()
        params.append(param)
    return member, params


@pytest.mark.parametrize("node_cls", [MethodNode, FunctionNode])
def test_has_parameters_roundtrip(node_cls):
    member, (p0, p1) = _make_member_and_params(
        node_cls,
        "register_migration",
        [
            {"name": "migration", "type": "std::unique_ptr<Migration>", "position": 0},
            {"name": "force", "type": "bool", "position": 1, "default": "false"},
        ],
    )

    member.has_parameters.connect(p0)
    member.has_parameters.connect(p1)

    # 1. Manager traversal (typed API surface)
    connected = member.has_parameters.all()
    assert len(connected) == 2

    # 2. Backend lists the outgoing edges
    edges = get_backend().get_all_edges_outgoing(member)
    hp = [e for e in edges if e.relation_type == "HAS_PARAMETER"]
    assert len(hp) == 2
    assert all(e.target_type == "ParameterNode" for e in hp)

    # 3. serialize() carries the edges
    serialized = member.serialize(fields="all")
    ser_hp = [
        e for e in serialized["edges"]
        if e["relation_type"] == "HAS_PARAMETER"
    ]
    assert len(ser_hp) == 2

    # 4. LayerGraph.from_backend retains them as references
    graph = LayerGraph.from_backend(get_backend(), "as-built")
    refs = []
    for entry in graph.entries.values():
        refs.extend(
            r for r in entry.references if r[0] == "HAS_PARAMETER"
        )
    assert len(refs) == 2

    # 5. The referenced targets are the saved parameters (resolvable via
    #    the graph's flat index — what the codegen context builder does).
    flat = graph._flat_index()
    resolved = [flat[key] for _, key, _ in refs]
    assert {e.node.name for e in resolved} == {"migration", "force"}
    # Position ordering is on the ParameterNode itself, not the edge —
    # the context builder sorts by it.
    positions = sorted(e.node.position for e in resolved)
    assert positions == [0, 1]


def test_parameter_position_ordering_semantics():
    """Position is the source of truth for order; the builder sorts.

    The relationship manager does not promise traversal order (edges
    come back in backend/insertion order) — the codegen context builder
    sorts by ``ParameterNode.position``.  Both parameters must be
    reachable, and the position-sorted order must be the declaration
    order.
    """
    member, (p0, p1) = _make_member_and_params(
        MethodNode,
        "rollback",
        [
            {"name": "target_version", "type": "int", "position": 0},
            {"name": "dry_run", "type": "bool", "position": 1},
        ],
    )
    member.has_parameters.connect(p1)  # connect out of order
    member.has_parameters.connect(p0)

    resolved = member.has_parameters.all()
    assert {p.position for p in resolved} == {0, 1}  # both reachable
    # The manager does not promise order; sorting by position is the
    # context builder's responsibility (codegen/context/member.py).
    ordered = sorted(resolved, key=lambda p: p.position)
    assert [p.position for p in ordered] == [0, 1]
    assert [p.name for p in ordered] == ["target_version", "dry_run"]
