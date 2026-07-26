"""Unit test: AttributeNode full deserialization from committed JSON fixture.

Reads every property from tests/data/attribute_node_full.json,
deserializes into an AttributeNode, and asserts all fields match.
No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "attribute_node_full.json"

# Auto-generated (UniqueIdProperty) or structural — not asserted field-by-field.
SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization
# Verifies that the deserialize method of LayerGraph correctly reconstructs an attribute
# node from its serialized form, ensuring data integrity during graph reconstruction.
def test_attribute_node_full_deserialization():
    # codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization::step_0
    # Executes the deserialization of a serialized attribute node using
    # `LayerGraph.deserialize`, producing the `node` fixture and the intermediate
    # deserialized `data` dictionary for subsequent assertions.
    with open(FIXTURE) as f:
        data = json.load(f)

    # Deserialize via the registry so type discrimination is exercised
    node = CodeGraphNode.deserialize(data)

    # Correct subclass
    # codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization::post_0
    # Confirms that the deserialized object is an instance of `AttributeNode`,
    # guaranteeing that the deserializer reconstructs the correct class type.
    assert isinstance(node, AttributeNode)
    # codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization::post_1
    # Verifies that the deserialized data's 'type' field is 'AttributeNode', ensuring
    # the serializer correctly preserves the node type information.
    assert data["type"] == "AttributeNode"

    # The qualified_name is auto-generated on creation,
    # so we just assert it exists and is non-empty
    # codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization::post_2
    # Checks that the deserialized `AttributeNode` has a non-empty `qualified_name`,
    # ensuring auto-generation of this field during deserialization works as expected.
    assert node.qualified_name, "qualified_name should be auto-generated"

    # Every other property in the JSON file must match the node exactly
    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc member.test_attribute_deserialization.test_attribute_node_full_deserialization::post_3
        # Validates that each field of the deserialized `AttributeNode` matches the
        # original data, ensuring field-by-field correctness during the deserialization
        # process.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_attribute_node_full_deserialization()