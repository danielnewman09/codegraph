"""Unit test: InterfaceNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import InterfaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "interface_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization
# Validates that an InterfaceNode is correctly reconstructed from its serialized data by
# verifying its type, the presence of an auto-generated qualified name, and the exact
# match of all deserialized fields to their expected values, which is critical for
# ensuring round-trip serialization fidelity in the codegraph library.
def test_interface_node_full_deserialization():
    # codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization::step_0
    # Invokes LayerGraph.deserialize with pre-defined input data to produce a
    # CodeGraphNode, which is then stored as the 'node' fixture; this action advances
    # the test by generating the object that all assertions will later validate.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization::post_0
    # Asserts that the deserialized node is an instance of InterfaceNode, confirming
    # that the deserializer correctly reconstructs a node with the expected specialized
    # type rather than a generic or different node subclass.
    assert isinstance(node, InterfaceNode)
    # codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization::post_1
    # Asserts that the serialized data dictionary includes the key 'type' with the value
    # 'InterfaceNode', verifying that the node's type information is preserved correctly
    # during the serialization process.
    assert data["type"] == "InterfaceNode"
    # codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization::post_2
    # Verifies that the deserialized node possesses a non-empty qualified_name
    # attribute, which is expected to be auto-generated if not provided, guaranteeing
    # that this essential identifier is always present after deserialization.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc compound.test_interface_serialization.test_interface_node_full_deserialization::post_3
        # Asserts that each field in the deserialized node exactly matches the
        # corresponding expected value; this provides a comprehensive check of the
        # entire deserialization output, ensuring no data loss or corruption occurs for
        # any field.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_interface_node_full_deserialization()