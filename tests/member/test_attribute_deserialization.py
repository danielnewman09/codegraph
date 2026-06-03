"""Unit test: AttributeNode full deserialization from committed JSON fixture.

Reads every property from tests/data/attribute_node_full.json,
deserializes into an AttributeNode, and asserts all fields match.
No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "attribute_node_full.json"

# Auto-generated (UniqueIdProperty) or structural — not asserted field-by-field.
SKIP_FIELDS = {"qualified_name", "edges", "type"}


def test_attribute_node_full_deserialization():
    with open(FIXTURE) as f:
        data = json.load(f)

    # Deserialize via the registry so type discrimination is exercised
    node = CodeGraphNode.from_json(data)

    # Correct subclass
    assert isinstance(node, AttributeNode)
    assert data["type"] == "AttributeNode"

    # The qualified_name is auto-generated on creation,
    # so we just assert it exists and is non-empty
    assert node.qualified_name, "qualified_name should be auto-generated"

    # Every other property in the JSON file must match the node exactly
    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )


if __name__ == "__main__":
    test_attribute_node_full_deserialization()