"""Unit test: NamespaceNode COMPOSES NamespaceNode relationship roundtrip (nesting).

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace
# Verifies that a NamespaceNode can be correctly serialized and deserialized via
# CodeGraphNode.serialize, LayerGraph.deserialize, and CompositeEntry.serialize,
# ensuring round‑trip consistency for namespace composition in code graphs.
def test_namespace_composes_namespace():
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::step_0
    # Sets up the test environment by initializing the inner and outer NamespaceNode
    # fixtures, providing a well-defined starting state for the composition test.
    outer_ns = NamespaceNode(
        name="outer",
        kind="namespace",
        description="Outer namespace",
    ).save()

    inner_ns = NamespaceNode(
        name="inner",
        kind="namespace",
        description="Inner nested namespace",
    ).save()

    outer_ns.namespaces.connect(inner_ns)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_namespace.json"

    with open(out_path, "w") as f:
        json.dump(outer_ns.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_0
    # Checks that the deserialized object is still a NamespaceNode, ensuring the type
    # identity is preserved across the serialization roundtrip, which is crucial for
    # further operations.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::step_1
    # Serializes the outer NamespaceNode using CompositeEntry.serialize, converting the
    # namespace structure into a format suitable for storage or transmission, advancing
    # the test toward the roundtrip verification.
    original_fields = {k: v for k, v in outer_ns.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_1
    # Compares the original fields of the outer namespace with the fields of the
    # roundtripped node, ensuring that all metadata is preserved exactly, verifying data
    # integrity across the roundtrip.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::step_2
    # Deserializes the serialized data back into a CodeGraphNode using
    # LayerGraph.deserialize, completing the roundtrip and creating the roundtripped
    # fixture for comparison with the original.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_2
    # Verifies that exactly one 'composes' edge was found in the deserialized node,
    # confirming that the composition relationship between outer and inner namespaces is
    # correctly tracked.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_3
    # Asserts that the target type of the single composes edge is 'NamespaceNode',
    # ensuring the composition relationship points to the correct type of node,
    # validating the semantic correctness of the graph.
    assert composes_edges[0]["target_type"] == "NamespaceNode"
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_4
    # Checks that the target UID of the composes edge matches the UID of the inner
    # namespace, confirming that the composition relationship correctly identifies the
    # composed namespace node.
    assert composes_edges[0]["target_uid"] == inner_ns._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::step_3
    # Extracts the original fields from the outer namespace and the roundtripped fields
    # from the deserialized node, plus retrieves the composition edges, preparing the
    # data for all subsequent assertions.
    connected = outer_ns.namespaces.all()
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_5
    # Verifies that only one node is connected to the roundtripped node via the composes
    # relationship, ensuring no extraneous connections exist, confirming the graph
    # structure is as expected.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_namespace.test_namespace_composes_namespace::post_6
    # Likely compares the connected node's identity to the inner namespace, confirming
    # that the single connected node is indeed the correct inner namespace, final
    # verification of composition fidelity.
    assert connected[0]._uid_value() == inner_ns._uid_value()


if __name__ == "__main__":
    test_namespace_composes_namespace()