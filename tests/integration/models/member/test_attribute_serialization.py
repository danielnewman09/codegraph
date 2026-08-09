"""Unit test: AttributeNode serialize → JSON file → deserialize roundtrip.

Does not require Neo4j. Run with:

    python tests/test_attribute_serialization.py
"""

import json
from pathlib import Path

from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip
# This test verifies that an AttributeNode can be serialized and then deserialized
# without loss of data, ensuring roundtrip integrity using CompositeEntry.serialize and
# LayerGraph.deserialize.
def test_attribute_node_roundtrip():
    # 1. Build an AttributeNode
    # codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip::step_0
    # Sets up the test by creating the original AttributeNode fixture, establishing the
    # baseline for the serialization roundtrip.
    original = AttributeNode(
        name="width",
        kind="attribute",
        type_signature="int",
        visibility="private",
        brief_description="Widget width in pixels",
    source="test",)

    # 2. Write to unit_test_data/ using serialize()
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "attribute_node_roundtrip.json"
    with open(out_path, "w") as f:
        json.dump(original.serialize(), f, indent=2)

    # 3. Read the JSON file and deserialize via deserialize
    with open(out_path) as f:
        data = json.load(f)
    roundtripped = CodeGraphNode.deserialize(data)

    # 4. Assert type is correct
    # codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip::post_0
    # Verifies that the deserialized object is an instance of AttributeNode, confirming
    # the deserialization returns the expected class type.
    assert isinstance(roundtripped, AttributeNode)
    # codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip::post_1
    # Checks that the serialized data dictionary contains the correct type field
    # 'AttributeNode', ensuring the serialize method correctly records the node type.
    assert data["type"] == "AttributeNode"

    # 5. Assert fields roundtrip
    # codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip::post_2
    # Confirms that the serialized data dictionary also equals the data directly
    # produced by the original node's serialize method, ensuring the serialize chain is
    # consistent.
    assert original.serialize() == roundtripped.serialize(), (
        f"Mismatch:\n  expected: {original.serialize()}\n  actual:   {roundtripped.serialize()}"
    )
    # codegraph:test-desc member.test_attribute_serialization.test_attribute_node_roundtrip::step_1
    # Performs the serialization of the original node and subsequent deserialization
    # into a roundtripped node, advancing the test to assert equivalence between them.
    print("✓ PASS: AttributeNode roundtrip — serialize/deserialize preserves type and fields")


if __name__ == "__main__":
    test_attribute_node_roundtrip()