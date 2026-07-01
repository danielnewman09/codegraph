"""Unit test: DefineNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import DefineNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "define_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


# codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization
# Verifies that the full Node object can be correctly reconstructed from its serialized
# representation via LayerGraph.deserialize, ensuring serialization fidelity is
# maintained for reliable graph state restoration.
def test_define_node_full_deserialization():
    # codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization::step_0
    # This step sets up the necessary environment or data structures required for the
    # deserialization operation to be performed and verified.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization::post_0
    # It checks that the deserialized object is an instance of 'DefineNode', ensuring
    # the correct class is instantiated by the deserialization method.
    assert isinstance(node, DefineNode)
    # codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization::post_1
    # It verifies that the 'type' field of the deserialized data is 'DefineNode',
    # confirming that the deserialization correctly identifies the node type.
    assert data["type"] == "DefineNode"
    # codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization::post_2
    # It ensures that the deserialized node has a non-empty 'qualified_name', confirming
    # that the deserialization method automatically generates this important identifier.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc member.test_define_serialization.test_define_node_full_deserialization::post_3
        # It compares each actual field value of the deserialized node against the
        # expected value, ensuring that all data fields are accurately restored during
        # deserialization.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_define_node_full_deserialization()