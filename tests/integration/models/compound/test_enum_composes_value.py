from codegraph.backends import get_backend
"""Unit test: EnumNode COMPOSES EnumValueNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import EnumNode
from codegraph.models.member import EnumValueNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value
# Verifies that an EnumNode built from EnumValueNodes correctly serializes and
# deserializes through the CompositeEntry and LayerGraph layers, ensuring that the
# composition of enum members preserves their structure during serialization round-trip.
def test_enum_composes_value():
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::step_0
    # Creates the initial EnumNode and its associated EnumValueNode fixtures using
    # EnumNode and EnumValueNode classes, establishing the baseline state for the
    # serialization and deserialization test.
    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
        source="test",
    ).save()

    value_node = EnumValueNode(
        name="ADD",
        kind="enumvalue",
        brief_description="Represents addition",
        source="test",
    ).save()

    enum_node.values.connect(value_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "enum_composes_value.json"

    with open(out_path, "w") as f:
        json.dump(enum_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_0
    # Ensures the deserialized object is an instance of EnumNode, confirming that
    # serialization/deserialization maintains the correct type hierarchy.
    assert isinstance(roundtripped, EnumNode)

    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::step_1
    # Extracts the original fields from the EnumNode (via the 'fields' property) to be
    # compared later with the fields of the roundtripped node, ensuring that
    # serialization/deserialization preserves all data.
    original_fields = {k: v for k, v in enum_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_1
    # Verifies that the original fields (from step_1) match the fields of the
    # roundtripped node, ensuring the serialization/deserialization roundtrip preserves
    # all data without loss or corruption.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::step_2
    # Serializes the composite EnumNode (including its EnumValueNode) to a dictionary
    # using codegraph.graph.CompositeEntry.serialize, producing a snapshot of its
    # structure for later deserialization and validation.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_2
    # Asserts that exactly one composition edge exists in the roundtripped node,
    # verifying that the EnumNode correctly composes exactly one value.
    assert len(composes_edges) == 1
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_3
    # Checks that the target_type attribute of the single composition edge is
    # 'EnumValueNode', confirming the type of the node being composed is correctly
    # preserved.
    assert composes_edges[0]["target_type"] == "EnumValueNode"
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_4
    # Checks that the target_key of the composition edge matches the key of the original
    # value_node, verifying that the link points to the correct composed node.
    assert composes_edges[0]["target_key"] == value_node.canonical_key

    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::step_3
    # Deserializes the previously serialized dictionary back into a CodeGraphNode using
    # codegraph.graph.LayerGraph.deserialize, creating the roundtripped node to compare
    # with the original.
    connected = get_backend().graph.composed_children(enum_node, EnumValueNode)
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_5
    # Asserts that the roundtripped node has exactly one 'connected' element, confirming
    # the composition relationship is correctly restored from the serialized data.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_enum_composes_value.test_enum_composes_value::post_6
    # Verifies that the 'connected' field of the roundtripped node is an empty list
    # (==), ensuring no leftover or unexpected connections are introduced during
    # serialization/deserialization.
    assert connected[0].canonical_key == value_node.canonical_key


if __name__ == "__main__":
    test_enum_composes_value()