"""Unit test: ClassNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "class_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


# codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization
# Verifies that a full ClassNode can be correctly deserialized from a dictionary,
# confirming the integrity of the deserialization process.
def test_class_node_full_deserialization():
    # codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization::step_0
    # Calls `LayerGraph.deserialize` with a complete dictionary representing a
    # ClassNode, producing the `node` fixture for subsequent validation.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization::post_0
    # Ensures the deserialized object is an instance of `ClassNode`, confirming the
    # class type is preserved.
    assert isinstance(node, ClassNode)
    # codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization::post_1
    # Checks that the raw data dictionary retains the expected type key, verifying the
    # type metadata is correctly serialized.
    assert data["type"] == "ClassNode"
    # codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization::post_2
    # Verifies that the `qualified_name` attribute is automatically generated and
    # non-empty, ensuring essential naming metadata is present.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc compound.test_class_serialization.test_class_node_full_deserialization::post_3
        # Compares each field of the deserialized node against expected values,
        # identifying any mismatches that indicate correctness or completeness issues.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_class_node_full_deserialization()