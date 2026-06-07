"""Unit test: UnionNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import UnionNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "union_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}


def test_union_node_full_deserialization():
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    assert isinstance(node, UnionNode)
    assert data["type"] == "UnionNode"
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_union_node_full_deserialization()