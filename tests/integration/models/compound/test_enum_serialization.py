"""Unit test: EnumNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import EnumNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "enum_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization
# This test verifies that an EnumNode can be fully deserialized from its JSON
# representation, ensuring that serialization and deserialization are symmetric and
# preserve all fields.
def test_enum_node_full_deserialization():
    # codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization::step_0
    # Sets up the test by providing the JSON data needed for deserialization, advancing
    # the test toward verification.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization::post_0
    # Confirms the deserialized object is actually an EnumNode instance, which is
    # fundamental for type safety and correct behavior.
    assert isinstance(node, EnumNode)
    # codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization::post_1
    # Ensures the deserialized data retains the correct type identifier 'EnumNode',
    # which is essential for proper type classification.
    assert data["type"] == "EnumNode"
    # codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization::post_2
    # Checks that the node has a non-empty qualified_name after deserialization, which
    # is crucial for identifying the node in the graph.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc compound.test_enum_serialization.test_enum_node_full_deserialization::post_3
        # Verifies that each field of the deserialized node matches the expected value,
        # ensuring all data is correctly restored.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_enum_node_full_deserialization()