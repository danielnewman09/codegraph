"""Unit test: MethodNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/member/test_method_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_method_node_roundtrip():
    # 1. Build a MethodNode
    original = MethodNode(
        name="draw",
        kind="method",
        type_signature="void",
        argsstring="(Canvas c)",
        visibility="public",
        brief_description="Renders the widget onto a canvas",
    )

    # 2. Write to unit_test_data/ using serialize()
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "method_node_roundtrip.json"
    with open(out_path, "w") as f:
        json.dump(original.serialize(), f, indent=2)

    # 3. Read the JSON file and deserialize via from_json
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.from_json(data)

    # 4. Assert type is correct
    assert isinstance(roundtripped, MethodNode)
    assert data["type"] == "MethodNode"

    # 5. Assert fields roundtrip
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    print("✓ PASS: MethodNode roundtrip — serialize/from_json preserves type and fields")


if __name__ == "__main__":
    test_method_node_roundtrip()