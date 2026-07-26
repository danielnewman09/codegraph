"""Unit test: UnionNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import UnionNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "union_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization
# Verifies that codegraph.graph.LayerGraph.deserialize correctly reconstructs a full
# UnionNode from serialized data, ensuring data integrity and type accuracy during
# deserialization.
def test_union_node_full_deserialization():
    # codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization::step_0
    # Executes the deserialization via codegraph.graph.LayerGraph.deserialize to
    # transform serialized data into the node fixture, advancing the test from setup to
    # verification.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization::post_0
    # Checks that the deserialized node is an instance of UnionNode, confirming the
    # correct node type is produced from serialized data.
    assert isinstance(node, UnionNode)
    # codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization::post_1
    # Verifies that the serialized data dict includes a 'type' field set to 'UnionNode',
    # confirming that the deserialization source correctly identifies the node type.
    assert data["type"] == "UnionNode"
    # codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization::post_2
    # Ensures that the deserialized node has a non-empty qualified_name, indicating that
    # the auto-generation of the name during deserialization works correctly.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc compound.test_union_serialization.test_union_node_full_deserialization::post_3
        # Verifies that each field of the deserialized node matches its expected value,
        # ensuring the deserialization process accurately restores all node attributes.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_union_node_full_deserialization()