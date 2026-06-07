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

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_attribute_defined_in_file():
    # 1. Create and save both nodes, then connect them
    file_node = FileNode(
        name="widget.h",
        path="/src/widget.h",
        language="cpp",
    ).save()

    attr_node = AttributeNode(
        name="width",
        kind="attribute",
        type_signature="int",
        visibility="private",
        brief_description="Widget width in pixels",
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
    assert isinstance(roundtripped, AttributeNode)
    assert data["type"] == "AttributeNode"

    # 4. Compare fields (edges differ across instances)
    original_fields = {k: v for k, v in attr_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields, (
        f"Fields mismatch:\n  expected: {original_fields}\n  actual:   {roundtripped_fields}"
    )

    # 5. The edges array contains the DEFINED_IN relationship
    assert "edges" in data
    assert isinstance(data["edges"], list)
    defined_in_edges = [e for e in data["edges"] if e["relation_type"] == "DEFINED_IN"]
    assert len(defined_in_edges) == 1

    edge = defined_in_edges[0]
    assert edge["target_type"] == "FileNode"
    assert edge["target_uid"] == file_node._uid_value()

    # 6. Verify the live graph agrees
    connected = attr_node.defined_in.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == file_node._uid_value()


if __name__ == "__main__":
    test_attribute_defined_in_file()