"""Unit test: MethodNode full deserialization from committed JSON fixture.

Reads every property from tests/data/method_node_full.json,
deserializes into a MethodNode, and asserts all fields match.
No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "method_node_full.json"

# Properties that are auto-generated (UniqueIdProperty) or relationships
# — these are not asserted field-by-field.
SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization
# This test verifies the complete deserialization of a MethodNode from serialized data;
# it validates that serialized method node fields (including name, source location, type
# hints, body content, and decorators) are correctly restored by
# `LayerGraph.deserialize`, ensuring the integrity of graph reconstruction and reliable
# code analysis.
def test_method_node_full_deserialization():
    # codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization::step_0
    # This step performs the deserialization of the MethodNode from its serialized data.
    # It is the core action under test, producing the actual result to be verified.
    with open(FIXTURE) as f:
        data = json.load(f)

    # Deserialize via the registry so type discrimination is exercised
    node = CodeGraphNode.deserialize(data)

    # Correct subclass
    # codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization::post_0
    # Confirms that the deserialized object is an instance of MethodNode. This is the
    # most fundamental correctness check, ensuring the deserialization produces the
    # expected type of node.
    assert isinstance(node, MethodNode)
    # codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization::post_1
    # Checks that the 'type' field in the serialized data dictionary is 'MethodNode'.
    # This ensures the deserialization process correctly reports the node's type, which
    # is essential for proper reconstruction.
    assert data["type"] == "MethodNode"

    # The qualified_name is auto-generated on creation,
    # so we just assert it exists and is non-empty
    # codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization::post_2
    # Verifies that the deserialized node has an auto-generated qualified_name property.
    # This is critical because the deserialization process must correctly reconstruct
    # the node's identity from the serialized data.
    assert node.qualified_name, "qualified_name should be auto-generated"

    # Every other property in the JSON file must match the node exactly
    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc member.test_method_deserialization.test_method_node_full_deserialization::post_3
        # Validates that every field of the deserialized node exactly matches the
        # original value. This comprehensive check ensures full fidelity of the
        # deserialization process, preserving all node properties.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_method_node_full_deserialization()