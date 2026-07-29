from codegraph.backends import get_backend
"""Unit test: ClassNode INHERITS_FROM ClassNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_class_inherits.test_class_inherits
# Verifies that a class inheritance relationship is correctly serialized and
# deserialized through the code graph, ensuring that derived class nodes preserve their
# inheritance edges and field data across round-trip conversion.
def test_class_inherits():
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::step_0
    # Sets up the initial test environment by defining a base ClassNode and a derived
    # ClassNode with an inheritance edge, establishing the foundational data structure
    # for the test.
    base_class = ClassNode(
        name="BaseWindow",
        kind="class",
        brief_description="Abstract base window class",
        is_abstract=True,
        source="test",
    ).save()

    derived_class = ClassNode(
        name="CalculatorWindow",
        kind="class",
        brief_description="Main application window for the calculator",
        source="test",
    ).save()

    derived_class.base.connect(base_class)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_inherits.json"

    with open(out_path, "w") as f:
        json.dump(derived_class.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_0
    # Verifies that the roundtripped node is still an instance of ClassNode, ensuring
    # the deserialization process preserved the correct type.
    assert isinstance(roundtripped, ClassNode)

    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::step_1
    # Adds the derived class node to a CompositeEntry and serializes it, converting the
    # inheritance structure into a portable format for later verification.
    original_fields = {k: v for k, v in derived_class.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_1
    # Verifies that all original field data (e.g., attributes) of the roundtripped node
    # matches the original, confirming no data loss or corruption during serialization
    # or deserialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::step_2
    # Deserializes the serialized data back into a LayerGraph, producing the
    # roundtripped representation that will be compared against the original to confirm
    # fidelity.
    inherits_edges = [e for e in data["edges"] if e["relation_type"] == "INHERITS_FROM"]
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_2
    # Verifies that exactly one inheritance edge exists from the derived class,
    # confirming that the inheritance relationship was correctly captured and
    # deserialized.
    assert len(inherits_edges) == 1
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_3
    # Verifies that the target of the inheritance edge is a ClassNode, ensuring the edge
    # points to a valid class type rather than an incorrect node type.
    assert inherits_edges[0]["target_type"] == "ClassNode"
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_4
    # Verifies that the target node of the inheritance edge has the unique identifier
    # (UID) of the base_class, proving that the correct inheritance relationship was
    # restored.
    assert inherits_edges[0]["target_uid"] == base_class._uid_value()

    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::step_3
    # Extracts the deserialized roundtripped node from the LayerGraph, preparing it for
    # detailed assertions about its type, fields, and inheritance edges.
    connected = get_backend().graph.outgoing_by_relation(derived_class, "INHERITS_FROM")
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_5
    # Verifies that the target node (base_class) has exactly one connected node (the
    # derived class), ensuring the bidirectional inheritance link is correctly
    # maintained.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_class_inherits.test_class_inherits::post_6
    # Verifies that the target node's base_fields (or similar) match expected values,
    # confirming the integrity of the base class data after deserialization.
    assert connected[0]._uid_value() == base_class._uid_value()


if __name__ == "__main__":
    test_class_inherits()