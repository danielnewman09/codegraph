"""Integration test: build the full Calculator graph from design_graph.json.

Uses ``LayerGraph`` to create all nodes and edges from the JSON fixture,
serialize the complete graph to a single JSON file, read it back, and
assert the graph roundtrips correctly.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"

SKIP_FIELDS = {"qualified_name", "refid", "edges", "type"}


def _count_all_entries(graph: LayerGraph) -> int:
    """Count all CompositeEntry instances across the entire tree."""
    return sum(1 for _ in graph._all_entries())


def _flatten_items(items: list[dict]) -> list[dict]:
    """Flatten nested composes items into a single list."""
    result = []
    for item in items:
        result.append(item)
        if "composes" in item:
            result.extend(_flatten_items(item["composes"]))
    return result


def test_graph_integration():
    with open(FIXTURE) as f:
        nodes_data = json.load(f)

    # Pure deserialization — no DB interaction
    graph = LayerGraph.deserialize(nodes_data)

    assert _count_all_entries(graph) == len(nodes_data), (
        f"Expected {len(nodes_data)} nodes, got {_count_all_entries(graph)}"
    )

    # Explicit persistence
    graph.to_neo4j()

    # Serialize the entire graph to a single JSON file (nested format)
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "graph_integration.json"

    graph_serialized = graph.serialize()
    with open(out_path, "w") as f:
        json.dump(graph_serialized, f, indent=2)

    # Read it back and verify every node roundtrips
    with open(out_path) as f:
        loaded = json.load(f)

    # Flatten the nested output for total node count comparison
    flat_loaded = _flatten_items(loaded)
    assert len(flat_loaded) == len(nodes_data), (
        f"Expected {len(nodes_data)} total nodes, "
        f"got {len(flat_loaded)} ({len(loaded)} root + nested)"
    )

    flat = graph._flat_index()

    # Build a key-based lookup from the flattened output
    loaded_by_key: dict[str, dict] = {}
    for item in flat_loaded:
        k = LayerGraph._node_key(item)
        loaded_by_key[k] = item

    for original in nodes_data:
        key = LayerGraph._node_key(original)
        entry = flat.get(key)
        assert entry is not None, f"Missing entry for key {key}"
        saved = entry.node

        roundtripped_data = loaded_by_key.get(key)
        assert roundtripped_data is not None, f"Missing roundtripped entry for key {key}"

        assert roundtripped_data["type"] == original["type"], (
            f"{original['type']} {key}: "
            f"expected {original['type']!r}, got {roundtripped_data['type']!r}"
        )

        roundtripped = CodeGraphNode.deserialize(roundtripped_data)
        original_fields = {k: v for k, v in saved.serialize().items() if k != "edges"}
        roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
        assert original_fields == roundtripped_fields, (
            f"Fields mismatch for {original['type']} '{key}':\n"
            f"  expected: {original_fields}\n"
            f"  actual:   {roundtripped_fields}"
        )

    # Every fixture edge exists in the live graph
    total_fixture_edges = 0
    for original in nodes_data:
        key = LayerGraph._node_key(original)
        entry = flat.get(key)
        assert entry is not None, f"Missing entry for key {key}"
        saved = entry.node
        for edge in original.get("edges", []):
            total_fixture_edges += 1
            target_entry = flat.get(edge["target_local_id"])
            assert target_entry is not None, f"Missing target {edge['target_local_id']}"
            target = target_entry.node
            found = [
                e for e in saved.serialize()["edges"]
                if e["relation_type"] == edge["relation_type"]
                and e["target_uid"] == target._uid_value()
            ]
            assert len(found) >= 1, (
                f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                f"{edge['target_type']} {edge['target_local_id']}"
            )

    total_live_edges = sum(
        len(entry.node.serialize()["edges"]) for entry in graph._all_entries()
    )
    assert total_live_edges >= total_fixture_edges, (
        f"Live edges ({total_live_edges}) < fixture edges ({total_fixture_edges})"
    )


if __name__ == "__main__":
    test_graph_integration()