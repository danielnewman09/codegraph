"""Unit test: MethodNode with DEFINED_IN → FileNode relationship roundtrip.

Creates a MethodNode, saves it, connects it to a FileNode via DEFINED_IN,
serializes to JSON, reads back, and asserts the roundtrip is faithful
including type discrimination and edges.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.file import FileNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file
# Verifies that a method defined in a file is correctly serialized, deserialized, and
# represented within the code graph's layer hierarchy, ensuring accurate representation
# of code structure and relationships across the CodeGraphNode, CompositeEntry,
# LayerGraph, MethodNode, and FileNode components.
def test_method_defined_in_file():
    # 1. Create and save both nodes, then connect them
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::step_0
    # Creates the initial method_node with sample fields, serving as the baseline for
    # the roundtrip test.
    file_node = FileNode(
        name="widget.h",
        path="/src/widget.h",
        language="cpp",
        source="test",
    ).save()

    method_node = MethodNode(
        name="draw",
        kind="method",
        type_signature="void",
        argsstring="(Canvas c)",
        visibility="public",
        brief_description="Renders the widget onto a canvas",
        source="test",
    ).save()

    method_node.defined_in.connect(file_node)

    # 2. Serialize and write to JSON
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "method_defined_in_file.json"

    with open(out_path, "w") as f:
        json.dump(method_node.serialize(), f, indent=2)

    # 3. Read back and deserialize via deserialize
    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_0
    # Verifies that the roundtripped object is an instance of MethodNode, ensuring the
    # type of the node is preserved through serialization and deserialization.
    assert isinstance(roundtripped, MethodNode)
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_1
    # Verifies that the serialized data contains the correct type field 'MethodNode',
    # ensuring the type information is accurately embedded in the serialized format.
    assert data["type"] == "MethodNode"

    # 4. Compare fields (edges differ across instances)
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::step_1
    # Creates the file_node and establishes a 'defined_in' edge from the method_node to
    # the file_node, setting up the relationship that will be verified in later
    # assertions.
    original_fields = {k: v for k, v in method_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_2
    # Verifies that all fields of the original MethodNode match the fields of the
    # roundtripped node, ensuring data integrity through the
    # serialization-deserialization cycle.
    assert original_fields == roundtripped_fields, (
        f"Fields mismatch:\n  expected: {original_fields}\n  actual:   {roundtripped_fields}"
    )

    # 5. The edges array contains the DEFINED_IN relationship
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_3
    # Verifies that the serialized data includes an 'edges' key, confirming that edge
    # metadata is present in the serialized representation.
    assert "edges" in data
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_4
    # Verifies that the 'edges' field in the serialized data is a list, ensuring that
    # edge data is stored in an iterable format as expected.
    assert isinstance(data["edges"], list)
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::step_2
    # Serializes the method_node into a JSON-like data structure, preparing it for
    # deserialization and field comparison.
    defined_in_edges = [e for e in data["edges"] if e["relation_type"] == "DEFINED_IN"]
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_5
    # Verifies that exactly one 'defined_in' edge exists for the method node, ensuring
    # that the method-to-file relationship is uniquely defined and correctly serialized.
    assert len(defined_in_edges) == 1

    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::step_3
    # Deserializes the previously serialized data back into a CodeGraphNode, producing
    # the roundtripped fixture for comparison.
    edge = defined_in_edges[0]
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_6
    # Verifies that the edge from the method node points to a FileNode, confirming that
    # the relationship type is correctly serialized.
    assert edge["target_type"] == "FileNode"
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_7
    # Verifies that the edge from the method node correctly references the file_node's
    # UID, confirming the 'defined_in' relationship points to the right file.
    assert edge["target_uid"] == file_node._uid_value()

    # 6. Verify the live graph agrees
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::step_4
    # Extracts the 'defined_in' edges from the roundtripped node's serialized data and
    # filters them for verification.
    connected = GraphRepository.outgoing_by_relation(method_node, "DEFINED_IN")
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_8
    # Verifies that the filtered 'connected' nodes list contains exactly one item,
    # ensuring that the method node has the expected single relationship to its defining
    # file.
    assert len(connected) == 1
    # codegraph:test-desc member.test_method_defined_in_file.test_method_defined_in_file::post_9
    # Verifies that the UID of the connected node matches the file_node's UID,
    # confirming that the deserialized node's file association is consistent.
    assert connected[0]._uid_value() == file_node._uid_value()


if __name__ == "__main__":
    test_method_defined_in_file()