"""Unit test: NamespaceNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "namespace_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


# codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization
# Verifies that a fully populated namespace node can be deserialized correctly from its
# serialized representation, ensuring that the deserialization method preserves the
# complete structure of the node and its relationships.
def test_namespace_node_full_deserialization():
    # codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization::step_0
    # Sets up the test by calling LayerGraph.deserialize with serialized data that
    # includes all namespace fields, producing the node fixture used for subsequent
    # assertions.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization::post_0
    # Verifies that the deserialized object is an instance of NamespaceNode, confirming
    # that the deserialization process produces the correct node type for namespace
    # data.
    assert isinstance(node, NamespaceNode)
    # codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization::post_1
    # Checks that the serialized data dictionary contains the expected type field
    # 'NamespaceNode', ensuring that the node's type information is correctly stored
    # during serialization.
    assert data["type"] == "NamespaceNode"
    # codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization::post_2
    # Asserts that the node's qualified_name attribute is automatically populated after
    # deserialization, verifying that this derived field is generated as expected for
    # NamespaceNode instances.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc namespace.test_namespace_serialization.test_namespace_node_full_deserialization::post_3
        # Compares each deserialized field against its expected value to confirm that
        # all attributes (e.g., name, path) are preserved accurately during the
        # deserialization round-trip.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_namespace_node_full_deserialization()