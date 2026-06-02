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
from codegraph.models.tags import LlmSerializable

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_method_defined_in_file():
    # 1. Create and save both nodes, then connect them
    file_node = FileNode(
        name="widget.h",
        path="/src/widget.h",
        language="cpp",
    ).save()

    method_node = MethodNode(
        name="draw",
        kind="method",
        type_signature="void",
        argsstring="(Canvas c)",
        visibility="public",
        brief_description="Renders the widget onto a canvas",
    ).save()

    method_node.defined_in.connect(file_node)

    # 2. Serialize and write to JSON
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "method_defined_in_file.json"

    with open(out_path, "w") as f:
        json.dump(method_node.serialize(), f, indent=2)

    # 3. Read back and deserialize via from_json
    with open(out_path) as f:
        data = json.load(f)

    roundtripped = LlmSerializable.from_json(data)
    assert isinstance(roundtripped, MethodNode)
    assert data["type"] == "MethodNode"

    # 4. Compare fields (edges differ across instances)
    original_fields = {k: v for k, v in method_node.serialize().items() if k != "edges"}
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
    connected = method_node.defined_in.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == file_node._uid_value()


if __name__ == "__main__":
    test_method_defined_in_file()