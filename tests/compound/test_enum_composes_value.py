"""Unit test: EnumNode COMPOSES EnumValueNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import EnumNode
from codegraph.models.member import EnumValueNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_enum_composes_value():
    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
    ).save()

    value_node = EnumValueNode(
        name="ADD",
        kind="enumvalue",
        brief_description="Represents addition",
    ).save()

    enum_node.values.connect(value_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "enum_composes_value.json"

    with open(out_path, "w") as f:
        json.dump(enum_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    assert isinstance(roundtripped, EnumNode)

    original_fields = {k: v for k, v in enum_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    assert len(composes_edges) == 1
    assert composes_edges[0]["target_type"] == "EnumValueNode"
    assert composes_edges[0]["target_uid"] == value_node._uid_value()

    connected = enum_node.values.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == value_node._uid_value()


if __name__ == "__main__":
    test_enum_composes_value()