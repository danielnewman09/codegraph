"""Unit test: FunctionNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import FunctionNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "function_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


# codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization
# Verifies that a fully serialized FunctionNode is correctly deserialized, ensuring the
# integrity of the graph reconstruction process for the LayerGraph.
def test_function_node_full_deserialization():
    # codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization::step_0
    # A setup step that calls deserialize on a LayerGraph to reconstruct a FunctionNode
    # from serialized data, producing the node fixture for later assertions.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization::post_0
    # Confirms that the deserialized object is indeed an instance of FunctionNode; this
    # matters because it validates that the deserialization process produces the correct
    # class type, not a generic or wrong node.
    assert isinstance(node, FunctionNode)
    # codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization::post_1
    # Verifies that the raw serialized data contains the correct type identifier
    # 'FunctionNode'; this is crucial for confirming that the serialization format
    # accurately stores node types.
    assert data["type"] == "FunctionNode"
    # codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization::post_2
    # Ensures that the deserialized node automatically generates a qualified_name; this
    # is important because a missing qualified_name would indicate incomplete or
    # incorrect deserialization logic.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc member.test_function_serialization.test_function_node_full_deserialization::post_3
        # Iterates over expected fields of the node and compares each to the actual
        # value; this ensures every field is faithfully restored by deserialization,
        # critical for maintaining data integrity across serialization boundaries.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_function_node_full_deserialization()