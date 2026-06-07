"""Unit test: ParameterNode full deserialization from committed JSON fixture.

No Neo4j required. ParameterNode has no UniqueIdProperty, so all fields
are asserted directly (no auto-generated uid skip).
"""

import json
from pathlib import Path

from codegraph.models.parameter import ParameterNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "parameter_node_full.json"

SKIP_FIELDS = {"edges", "type"}


def test_parameter_node_full_deserialization():
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    assert isinstance(node, ParameterNode)
    assert data["type"] == "ParameterNode"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_parameter_node_full_deserialization()