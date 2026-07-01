"""Unit test: FileNode full deserialization from committed JSON fixture.

Reads every property from tests/data/file_node_full.json,
deserializes into a FileNode, and asserts all fields match.
No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.file import FileNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "file_node_full.json"

# Auto-generated (UniqueIdProperty) or structural — not asserted field-by-field.
SKIP_FIELDS = {"refid", "edges", "type"}


# codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization
# Verifies that a FileNode can be fully deserialized from JSON data by
# LayerGraph.deserialize, ensuring round-trip integrity of file node metadata.
def test_file_node_full_deserialization():
    # codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization::step_0
    # Sets up the test by calling LayerGraph.deserialize with predefined JSON
    # representing a complete FileNode, producing the 'node' fixture for subsequent
    # verification.
    with open(FIXTURE) as f:
        data = json.load(f)

    # Deserialize via the registry so type discrimination is exercised
    node = CodeGraphNode.deserialize(data)

    # Correct subclass
    # codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization::post_0
    # Verifies that the deserialized object is an instance of FileNode, confirming the
    # deserializer correctly identifies the node type.
    assert isinstance(node, FileNode)
    # codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization::post_1
    # Verifies that the deserialized data dictionary contains the type 'FileNode',
    # ensuring the serialized metadata preserves the node type field.
    assert data["type"] == "FileNode"

    # The refid is auto-generated on creation,
    # so we just assert it exists and is non-empty
    # codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization::post_2
    # Verifies that the node has a non-empty refid after deserialization, confirming
    # that auto-generation or loading of unique identifiers works correctly.
    assert node.refid, "refid should be auto-generated"

    # Every other property in the JSON file must match the node exactly
    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc file.test_file_deserialization.test_file_node_full_deserialization::post_3
        # Iteratively compares all expected fields of the deserialized node against
        # known values, ensuring every attribute matches the original data.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_file_node_full_deserialization()