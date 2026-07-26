"""Unit test: MethodNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/member/test_method_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip
# Verifies that a MethodNode can be serialized and then deserialized without losing
# data, ensuring correctness in the persist-restore lifecycle of code elements.
def test_method_node_roundtrip():
    # 1. Build a MethodNode
    # codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip::step_0
    # Creates the original MethodNode instance that will be serialized and deserialized,
    # setting up the fundamental object for the roundtrip test.
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

    # 3. Read the JSON file and deserialize via deserialize
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.deserialize(data)

    # 4. Assert type is correct
    # codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip::post_0
    # Checks that the deserialized result is an instance of MethodNode, ensuring that
    # the deserialization process correctly reconstructs the node type.
    assert isinstance(roundtripped, MethodNode)
    # codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip::post_1
    # Verifies that the serialized data contains a 'type' field set to 'MethodNode',
    # ensuring that the type information is correctly preserved during serialization.
    assert data["type"] == "MethodNode"

    # 5. Assert fields roundtrip
    # codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip::post_2
    # Confirms that the original MethodNode and the roundtripped node are equal after
    # deserialization, establishing that the serialization-deserialization cycle
    # preserves all attributes and content.
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    # codegraph:test-desc member.test_method_serialization.test_method_node_roundtrip::step_1
    # Serializes the original MethodNode to a dictionary using the serialize method,
    # producing the data that will later be deserialized and compared to verify
    # roundtrip integrity.
    print("✓ PASS: MethodNode roundtrip — serialize/deserialize preserves type and fields")


if __name__ == "__main__":
    test_method_node_roundtrip()