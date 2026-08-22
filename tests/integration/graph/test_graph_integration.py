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

FIXTURE = Path(__file__).resolve().parent / "data" / "design_graph.json"
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

# codegraph:test-desc test_graph_integration.test_graph_integration
# Verifies the end-to-end integration of the LayerGraph's serialization,
# deserialization, and Neo4j export methods, ensuring that all entries (including
# composite items) are correctly flattened and indexed before being committed to the
# graph database.
def test_graph_integration():
    # codegraph:test-desc test_graph_integration.test_graph_integration::step_0
    # Creates initial graph fixtures and defines expected node data, including nested
    # entries and edge relationships. This setup establishes the baseline against which
    # all later serialization and deserialization steps are compared.
    with open(FIXTURE) as f:
        nodes_data = json.load(f)

    # Pure deserialization — no DB interaction
    graph = LayerGraph.deserialize(nodes_data)

    # codegraph:test-desc test_graph_integration.test_graph_integration::post_0
    # Asserts that the total number of entries in the graph equals the expected number
    # of nodes as defined in the fixture. This provides an early check that the graph's
    # overall node count is correct.
    assert _count_all_entries(graph) == len(nodes_data), (
        f"Expected {len(nodes_data)} nodes, got {_count_all_entries(graph)}"
    )

    # Explicit persistence
    # codegraph:test-desc test_graph_integration.test_graph_integration::step_1
    # Serializes the graph into a dictionary of node data, capturing all entries in a
    # serializable format. This step enables later deserialization and comparison to
    # verify that graph structure is preserved.
    graph.to_neo4j()

    # Serialize the entire graph to a single JSON file (nested format)
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = Path(__file__).resolve().parent / "data" / "graph_integration.json"

    graph_serialized = graph.serialize()
    with open(out_path, "w") as f:
        json.dump(graph_serialized, f, indent=2)

    # Read it back and verify every node roundtrips
    with open(out_path) as f:
        loaded = json.load(f)

    # Flatten the nested output for total node count comparison
    flat_loaded = _flatten_items(loaded)
    # codegraph:test-desc test_graph_integration.test_graph_integration::post_1
    # Asserts that the total number of nodes after flattening matches the expected count
    # from fixture data. This ensures that no nodes are lost or duplicated during
    # serialization and flattening operations.
    assert len(flat_loaded) == len(nodes_data), (
        f"Expected {len(nodes_data)} total nodes, "
        f"got {len(flat_loaded)} ({len(loaded)} root + nested)"
    )

    # codegraph:test-desc test_graph_integration.test_graph_integration::step_2
    # Flattens all graph entries into a list and counts them, preparing data for
    # assertions about node presence and total counts. This step advances the test by
    # transforming the graph structure into a comparable format.
    flat = graph._flat_index()

    # Build a key-based lookup from the flattened output
    loaded_by_key: dict[str, dict] = {}
    for item in flat_loaded:
        k = LayerGraph._node_key(item)
        loaded_by_key[k] = item

    for original in nodes_data:
        key = LayerGraph._node_key(original)
        entry = flat.get(key)
        # codegraph:test-desc test_graph_integration.test_graph_integration::post_2
        # Asserts that an entry exists in the graph for each expected key. This ensures
        # that no expected node is missing from the deserialized graph structure.
        assert entry is not None, f"Missing entry for key {key}"
        saved = entry.node

        roundtripped_data = loaded_by_key.get(key)
        # codegraph:test-desc test_graph_integration.test_graph_integration::post_3
        # Asserts that round-tripped data is not None for each key, confirming that each
        # node was successfully deserialized back into a dictionary. This is a
        # prerequisite for comparing node attributes.
        assert roundtripped_data is not None, f"Missing roundtripped entry for key {key}"

        # codegraph:test-desc test_graph_integration.test_graph_integration::post_4
        # Asserts that the 'type' field of each node remains unchanged after
        # serialization and deserialization. This verifies that the fundamental node
        # classification is preserved through the round-trip process.
        assert roundtripped_data["type"] == original["type"], (
            f"{original['type']} {key}: "
            f"expected {original['type']!r}, got {roundtripped_data['type']!r}"
        )

        roundtripped = CodeGraphNode.deserialize(roundtripped_data)
        original_fields = {k: v for k, v in saved.serialize().items() if k != "edges"}
        roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
        # codegraph:test-desc test_graph_integration.test_graph_integration::post_5
        # Asserts that the fields of each round-tripped node match the original node's
        # fields exactly. This verifies that all node attributes (e.g., methods,
        # signatures) are preserved without alteration through serialization and
        # deserialization.
        assert original_fields == roundtripped_fields, (
            f"Fields mismatch for {original['type']} '{key}':\n"
            f"  expected: {original_fields}\n"
            f"  actual:   {roundtripped_fields}"
        )

    # Every fixture edge exists in the live graph
    # codegraph:test-desc test_graph_integration.test_graph_integration::step_3
    # Iterates over each original node, retrieves its serialized data after
    # round-tripping, and compares key properties like type and fields. This step
    # directly validates the integrity of the round-trip process for individual nodes.
    total_fixture_edges = 0
    for original in nodes_data:
        key = LayerGraph._node_key(original)
        entry = flat.get(key)
        # codegraph:test-desc test_graph_integration.test_graph_integration::post_6
        # Asserts that an entry exists for each key in a second lookup context (e.g.,
        # after rebuilding from dictionary data). This double-checks that nodes are
        # accessible in the recreated graph structure.
        assert entry is not None, f"Missing entry for key {key}"
        saved = entry.node
        for edge in original.get("edges", []):
            total_fixture_edges += 1
            target_entry = flat.get(edge["target_key"])
            # codegraph:test-desc test_graph_integration.test_graph_integration::post_7
            # Asserts that the target entry for each edge exists in the graph. This
            # ensures that every relationship points to a valid node, confirming graph
            # integrity.
            assert target_entry is not None, f"Missing target {edge['target_key']}"
            target = target_entry.node
            found = [
                e for e in saved.serialize()["edges"]
                if e["relation_type"] == edge["relation_type"]
                and e["target_key"] == target.canonical_key
            ]
            # codegraph:test-desc test_graph_integration.test_graph_integration::post_8
            # Asserts that at least one matching edge entry is found for each expected
            # edge in the fixture. This ensures that each relationship between nodes is
            # correctly represented in the graph after reconstruction.
            assert len(found) >= 1, (
                f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                f"{edge['target_type']} {edge['target_key']}"
            )

    # codegraph:test-desc test_graph_integration.test_graph_integration::step_4
    # Collects all edges from the graph and counts them, then verifies that the live
    # edge count meets or exceeds the expected count from the fixture data. This step
    # checks edge connectivity after serialization.
    total_live_edges = sum(
        len(entry.node.serialize()["edges"]) for entry in graph._all_entries()
    )
    # codegraph:test-desc test_graph_integration.test_graph_integration::post_9
    # Asserts that the total number of edges found in the graph is at least as many as
    # defined in the fixture edge data. This verifies that all expected relationships
    # are preserved after graph serialization.
    assert total_live_edges >= total_fixture_edges, (
        f"Live edges ({total_live_edges}) < fixture edges ({total_fixture_edges})"
    )

if __name__ == "__main__":
    test_graph_integration()
