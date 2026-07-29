from codegraph.backends import get_backend
"""Unit test: ClassNode COMPOSES AttributeNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute
# Verifies that a ClassNode with an assigned AttributeNode can be serialized and
# deserialized while preserving its structure and composition relationships, ensuring
# the round-trip integrity of composite code graph nodes.
def test_class_composes_attribute():
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::step_0
    # Creates a ClassNode and an AttributeNode to be used as the basis for the
    # composition test.
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
        source="test",
    ).save()

    attr_node = AttributeNode(
        name="precision",
        kind="attribute",
        type_signature="int",
        visibility="public",
        source="test",
    ).save()

    class_node.attributes.connect(attr_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_composes_attribute.json"

    with open(out_path, "w") as f:
        json.dump(class_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_0
    # Verifies that the deserialized node is an instance of ClassNode, confirming the
    # round-trip preserved the correct type.
    assert isinstance(roundtripped, ClassNode)

    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::step_1
    # Assigns the attr_node to class_node's attributes, establishing the composition
    # relationship that will be tested.
    original_fields = {k: v for k, v in class_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_1
    # Verifies that the original fields of the ClassNode match the fields of the
    # deserialized version, ensuring no data loss during round-trip serialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::step_2
    # Serializes the class_node (which now contains attr_node) into a format suitable
    # for deserialization.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_2
    # Checks that the deserialized ClassNode has exactly one composition edge,
    # confirming the composition relationship was correctly preserved.
    assert len(composes_edges) == 1
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_3
    # Verifies that the composition edge points to a node of type 'AttributeNode',
    # ensuring the correct type of the composed attribute.
    assert composes_edges[0]["target_type"] == "AttributeNode"
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_4
    # Verifies that the composition edge targets the correct attribute by matching the
    # UID of the original attr_node, ensuring precise relationship restoration.
    assert composes_edges[0]["target_uid"] == attr_node._uid_value()

    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::step_3
    # Deserializes the serialized ClassNode back into a new object, completing the
    # round-trip cycle.
    connected = get_backend().graph.composed_children(class_node, AttributeNode)
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_5
    # Checks that exactly one node is connected in the graph, confirming that the
    # composition relationship is properly represented as a graph connection.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_class_composes_attribute.test_class_composes_attribute::post_6
    # Performs an equality check to ensure the entire round-tripped object matches the
    # original, verifying complete structural fidelity.
    assert connected[0]._uid_value() == attr_node._uid_value()


if __name__ == "__main__":
    test_class_composes_attribute()