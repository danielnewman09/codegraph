"""Unit test: FileNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/test_file_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.file import FileNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_file_node_roundtrip():
    # 1. Build a FileNode
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

    # 3. Read the JSON file and deserialize via from_json
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.from_json(data)

    # 4. Assert type is correct
    assert isinstance(roundtripped, FileNode)
    assert data["type"] == "FileNode"

    # 5. Assert fields roundtrip
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    print("✓ PASS: FileNode roundtrip — serialize/from_json preserves type and fields")


if __name__ == "__main__":
    test_file_node_roundtrip()