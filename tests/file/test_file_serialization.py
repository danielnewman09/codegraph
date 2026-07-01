"""Unit test: FileNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/test_file_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.file import FileNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


# codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip
# Verifies that a FileNode can be serialized and then deserialized back to an identical
# FileNode, ensuring the roundtrip serialization logic of the code under test is
# correct.
def test_file_node_roundtrip():
    # 1. Build a FileNode
    # codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip::step_0
    # Sets up the test by creating the original FileNode instance, establishing the data
    # to be serialized and later deserialized.
    original = FileNode(
        name="foo.h",
        path="/src/foo.h",
        language="cpp",
        source="codegraph",
    )

    # 2. Write to unit_test_data/ using serialize()
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "file_node_roundtrip.json"
    with open(out_path, "w") as f:
        json.dump(original.serialize(), f, indent=2)

    # 3. Read the JSON file and deserialize via deserialize
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.deserialize(data)

    # 4. Assert type is correct
    # codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip::post_0
    # Validates that the deserialized object is an instance of FileNode, confirming the
    # deserialization produces the correct class type.
    assert isinstance(roundtripped, FileNode)
    # codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip::post_1
    # Checks that the serialized data contains a 'type' key with value 'FileNode',
    # ensuring the serialization correctly identifies the node type.
    assert data["type"] == "FileNode"

    # 5. Assert fields roundtrip
    # codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip::post_2
    # Verifies that the original and roundtripped nodes are equal, confirming the
    # serialization/deserialization process preserves all data.
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    # codegraph:test-desc file.test_file_serialization.test_file_node_roundtrip::step_1
    # Performs the serialization of the original FileNode and then deserializes the
    # result, producing the roundtripped node for comparison.
    print("✓ PASS: FileNode roundtrip — serialize/deserialize preserves type and fields")


if __name__ == "__main__":
    test_file_node_roundtrip()