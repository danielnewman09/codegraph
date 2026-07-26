"""Unit test: AttributeNode with DEFINED_IN → FileNode relationship roundtrip.

Creates an AttributeNode, saves it, connects it to a FileNode via DEFINED_IN,
serializes to JSON, reads back, and asserts the roundtrip is faithful
including type discrimination and edges.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.file import FileNode
from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file
# Verifies that an attribute defined in a file is correctly serialized and deserialized
# through the system, ensuring round-trip integrity of the code graph model.
def test_attribute_defined_in_file():
    # 1. Create and save both nodes, then connect them
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::step_0
    # Sets up the test by creating the attr_node and file_node fixtures, establishing
    # the initial state needed for the serialization and roundtrip checks.
    file_node = FileNode(
        name="widget.h",
        path="/src/widget.h",
        language="cpp",
        source="test",
    ).save()

    attr_node = AttributeNode(
        name="width",
        kind="attribute",
        type_signature="int",
        visibility="private",
        brief_description="Widget width in pixels",
        source="test",
    ).save()

    attr_node.defined_in.connect(file_node)

    # 2. Serialize and write to JSON
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "attribute_defined_in_file.json"

    with open(out_path, "w") as f:
        json.dump(attr_node.serialize(), f, indent=2)

    # 3. Read back and deserialize via deserialize
    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_0
    # Confirms that the deserialized node is an instance of AttributeNode, verifying
    # that the type is preserved through ser/deser.
    assert isinstance(roundtripped, AttributeNode)
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_1
    # Ensures the serialized data dictionary has type 'AttributeNode', verifying the
    # correct type is stored for deserialization.
    assert data["type"] == "AttributeNode"

    # 4. Compare fields (edges differ across instances)
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::step_1
    # Extracts and records the original fields of the attr_node for later comparison,
    # ensuring that the roundtrip preserves all field values.
    original_fields = {k: v for k, v in attr_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_2
    # Validates that all original fields of the attr_node exactly match those after
    # roundtrip, confirming data integrity through serialization/deserialization.
    assert original_fields == roundtripped_fields, (
        f"Fields mismatch:\n  expected: {original_fields}\n  actual:   {roundtripped_fields}"
    )

    # 5. The edges array contains the DEFINED_IN relationship
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_3
    # Verifies that the serialized data contains an 'edges' key, confirming edges are
    # included in the serialized representation.
    assert "edges" in data
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_4
    # Confirms that the 'edges' field in the serialized data is a list, ensuring edge
    # data is structured correctly for serialization.
    assert isinstance(data["edges"], list)
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::step_2
    # Serializes the attr_node into a dictionary, producing the 'data' that will be used
    # for subsequent deserialization and edge checks.
    defined_in_edges = [e for e in data["edges"] if e["relation_type"] == "DEFINED_IN"]
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_5
    # Verifies that there is exactly one 'defined_in' edge present, confirming the
    # attribute has a single file relationship as expected.
    assert len(defined_in_edges) == 1

    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::step_3
    # Deserializes the serialized data back into a CodeGraphNode (roundtripped),
    # transforming it for direct comparison with the original attr_node.
    edge = defined_in_edges[0]
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_6
    # Asserts that the 'defined_in' edge's target type is 'FileNode', confirming the
    # relationship correctly points to a file node.
    assert edge["target_type"] == "FileNode"
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_7
    # Checks that the 'defined_in' edge's target UID matches the file_node's UID,
    # confirming the edge points to the correct file.
    assert edge["target_uid"] == file_node._uid_value()

    # 6. Verify the live graph agrees
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::step_4
    # Filters the deserialized node's edges to isolate those of type 'defined_in',
    # preparing them for detailed verification of the defined-in relationship.
    connected = GraphRepository.outgoing_by_relation(attr_node, "DEFINED_IN")
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_8
    # Verifies that exactly one edge connects the attr_node to the file_node, ensuring
    # the defined-in relationship is correctly established.
    assert len(connected) == 1
    # codegraph:test-desc member.test_attribute_defined_in_file.test_attribute_defined_in_file::post_9
    # Ensures some final equality condition is met (likely comparing the roundtripped
    # node's UID or field equality), completing the consistency verification.
    assert connected[0]._uid_value() == file_node._uid_value()


if __name__ == "__main__":
    test_attribute_defined_in_file()