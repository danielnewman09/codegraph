"""Unit test: NamespaceNode COMPOSES FunctionNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.member import FunctionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function
# Verifies that a NamespaceNode composes a FunctionNode correctly during deserialization
# of a LayerGraph, ensuring the structural integrity of the code graph.
def test_namespace_composes_function():
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::step_0
    # Sets up the test by creating a `NamespaceNode` that composes a `FunctionNode`,
    # providing the initial state for the round-trip serialization process.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    function_node = FunctionNode(
        name="formatResult",
        kind="function",
        type_signature="string",
        argsstring="(double value)",
        brief_description="Formats a numeric result as a string.",
    ).save()

    namespace_node.functions.connect(function_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_function.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_0
    # Asserts that the result of deserialization is a `NamespaceNode`, confirming the
    # deserialized object retains the correct type from the original.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::step_1
    # Captures the fields of the original `namespace_node` before serialization,
    # preserving the baseline for later comparison with the round-tripped node.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_1
    # Asserts that the original namespace fields and the fields of the round-tripped
    # node are identical, verifying that serialization and deserialization preserve all
    # namespace data.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::step_2
    # Serializes the `namespace_node` into a `CompositeEntry`, producing the data that
    # will later be deserialized to test preservation of the namespace composition.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_2
    # Asserts that exactly one composes edge exists after round-trip, confirming the
    # namespace's composition relationship is preserved as a single edge.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_3
    # Asserts that the target type of the composes edge is `'FunctionNode'`, confirming
    # that the edge correctly identifies the composed node as a function.
    assert composes_edges[0]["target_type"] == "FunctionNode"
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_4
    # Asserts that the UID of the target node in the first composes edge matches the
    # `function_node`'s UID, confirming the edge links to the correct function.
    assert composes_edges[0]["target_uid"] == function_node._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::step_3
    # Deserializes the `CompositeEntry` back into a `CodeGraphNode` and extracts its
    # `composes_edges`, completing the round-trip action so that the extracted edges can
    # be verified against the original composition.
    connected = GraphRepository.composed_children(namespace_node, FunctionNode)
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_5
    # Asserts that the `connected` list (derived from the round-tripped node) contains
    # exactly one element, confirming that the node retains its single connection.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_function.test_namespace_composes_function::post_6
    # Asserts that the first composes edge from round-trip equals a specific numerical
    # check (likely the target UID matches the function node’s UID via `==`), ensuring
    # the edge points to the exact intended function node.
    assert connected[0]._uid_value() == function_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_function()