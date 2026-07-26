"""Unit test: ClassNode REALIZES InterfaceNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode, InterfaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface
# This test verifies that a ClassNode correctly realizes an InterfaceNode by serializing
# and deserializing the relationships through CompositeEntry and LayerGraph, ensuring
# the compound model can persist and restore interface implementations correctly.
def test_class_realizes_interface():
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::step_0
    # Creates and sets up the interface_node and class_node fixtures, establishing the
    # initial state by defining a class that realizes an interface.
    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
        is_abstract=True,
    ).save()

    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    class_node.realizes.connect(interface_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_realizes_interface.json"

    with open(out_path, "w") as f:
        json.dump(class_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_0
    # Asserts that the deserialized node is still an instance of ClassNode; this ensures
    # the type information is correctly restored after the roundtrip.
    assert isinstance(roundtripped, ClassNode)

    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::step_1
    # Serializes the class_node to JSON and then deserializes it back into a
    # CodeGraphNode; this roundtrip creates the 'roundtripped' fixture for comparison.
    original_fields = {k: v for k, v in class_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_1
    # Verifies that all fields of the original ClassNode are preserved after
    # serialization and deserialization; this ensures data integrity during the
    # roundtrip.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::step_2
    # Retrieves the 'realizes' edges from the roundtripped node; this step collects the
    # edges that represent the realization relationship for subsequent assertions.
    realizes_edges = [e for e in data["edges"] if e["relation_type"] == "REALIZES"]
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_2
    # Checks that exactly one 'realizes' edge exists on the roundtripped node; this
    # confirms the realization relationship is not lost or duplicated during
    # serialization.
    assert len(realizes_edges) == 1
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_3
    # Asserts that the target type of the first 'realizes' edge is 'InterfaceNode'; this
    # validates the edge correctly references the interface type.
    assert realizes_edges[0]["target_type"] == "InterfaceNode"
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_4
    # Asserts that the target UID of the 'realizes' edge matches the interface_node's
    # UID; this verifies the edge points to the correct interface instance.
    assert realizes_edges[0]["target_uid"] == interface_node._uid_value()

    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::step_3
    # Fetches the 'connected' nodes from the 'realizes' edges to validate the target of
    # the relationship; this step prepares data to verify the edge target details.
    connected = GraphRepository.outgoing_by_relation(class_node, "REALIZES")
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_5
    # Checks that the 'connected' list has exactly one element; this ensures the edge
    # resolution yields a single, correct target.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_class_realizes_interface.test_class_realizes_interface::post_6
    # Verifies equality between the 'connected' list and the expected edges; this
    # confirms that the roundtripped node's edge data matches the original.
    assert connected[0]._uid_value() == interface_node._uid_value()


if __name__ == "__main__":
    test_class_realizes_interface()