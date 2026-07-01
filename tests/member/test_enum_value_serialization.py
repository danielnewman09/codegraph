"""Unit test: EnumValueNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import EnumValueNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "enum_value_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


# codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization
# Verifies that an EnumValueNode is correctly deserialized from its serialized form,
# ensuring data integrity for enumerated types in graph operations.
def test_enum_value_node_full_deserialization():
    # codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization::step_0
    # Executes the `LayerGraph.deserialize` method with input data to produce the `node`
    # fixture, setting up the object to be verified by subsequent assertions.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization::post_0
    # Confirms that the deserialized object is an instance of `EnumValueNode`,
    # validating that `LayerGraph.deserialize` returns the correct Python type for enum
    # value node data.
    assert isinstance(node, EnumValueNode)
    # codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization::post_1
    # Checks that the deserialized data's type field matches 'EnumValueNode', ensuring
    # the serialization metadata is correctly preserved and identifies the node type.
    assert data["type"] == "EnumValueNode"
    # codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization::post_2
    # Asserts that the deserialized node has a non-empty `qualified_name`, confirming
    # that the deserialization process auto-generates this required identifier when not
    # provided in the input data.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc member.test_enum_value_serialization.test_enum_value_node_full_deserialization::post_3
        # Verifies that each field of the deserialized node matches the expected value
        # from the input data, ensuring complete and accurate field-by-field
        # reconstruction of the original node.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_enum_value_node_full_deserialization()