"""Unit test: AttributeNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/test_attribute_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_attribute_node_roundtrip():
    # 1. Build an AttributeNode
    original = AttributeNode(
        name="width",
        kind="attribute",
        type_signature="int",
        visibility="private",
        brief_description="Widget width in pixels",
    )

    # 2. Write to unit_test_data/ using serialize()
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "attribute_node_roundtrip.json"
    with open(out_path, "w") as f:
        json.dump(original.serialize(), f, indent=2)

    # 3. Read the JSON file and deserialize via from_json
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.from_json(data)

    # 4. Assert type is correct
    assert isinstance(roundtripped, AttributeNode)
    assert data["type"] == "AttributeNode"

    # 5. Assert fields roundtrip
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    print("✓ PASS: AttributeNode roundtrip — serialize/from_json preserves type and fields")


if __name__ == "__main__":
    test_attribute_node_roundtrip()