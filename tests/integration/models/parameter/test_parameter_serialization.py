"""Unit test: ParameterNode full deserialization from committed JSON fixture.

No Neo4j required. ParameterNode has no UniqueIdProperty, so all fields
are asserted directly (no auto-generated uid skip).
"""

import json
from pathlib import Path

from codegraph.models.parameter import ParameterNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "parameter_node_full.json"

SKIP_FIELDS = {"edges", "type"}

# codegraph:test-desc parameter.test_parameter_serialization.test_parameter_node_full_deserialization
# Verifies that a fully populated ParameterNode can be correctly reconstructed from its
# serialized data using LayerGraph.deserialize, ensuring round-trip serialization
# integrity for parameters with all optional fields.
def test_parameter_node_full_deserialization():
    # codegraph:test-desc parameter.test_parameter_serialization.test_parameter_node_full_deserialization::step_0
    # This setup block likely performs the initial configuration and possibly the
    # deserialization call to prepare the node and data structures needed for subsequent
    # assertions, advancing the test toward verifying the correct reconstruction of the
    # parameter node.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc parameter.test_parameter_serialization.test_parameter_node_full_deserialization::post_0
    # This assertion verifies that the object obtained after deserialization is an
    # instance of ParameterNode, confirming that the deserialize method returns the
    # correct type of node, which is fundamental for the integrity of the graph
    # structure.
    assert isinstance(node, ParameterNode)
    # codegraph:test-desc parameter.test_parameter_serialization.test_parameter_node_full_deserialization::post_1
    # This assertion checks that the deserialized data dictionary contains a 'type'
    # field equal to 'ParameterNode', ensuring that the serialization format correctly
    # identifies the node type, which is essential for type-safe reconstruction.
    assert data["type"] == "ParameterNode"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc parameter.test_parameter_serialization.test_parameter_node_full_deserialization::post_2
        # This assertion verifies that for each field of the deserialized node, the
        # actual value matches the expected value from the original data, which is
        # crucial to confirm that the entire parameter node is accurately reconstructed
        # without any data loss or corruption.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_parameter_node_full_deserialization()