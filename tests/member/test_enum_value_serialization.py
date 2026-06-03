"""Unit test: EnumValueNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import EnumValueNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "enum_value_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


def test_enum_value_node_full_deserialization():
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.from_json(data)

    assert isinstance(node, EnumValueNode)
    assert data["type"] == "EnumValueNode"
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_enum_value_node_full_deserialization()