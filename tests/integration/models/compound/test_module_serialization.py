"""Unit test: ModuleNode full deserialization from committed JSON fixture.

No Neo4j required.
"""

import json
from pathlib import Path

from codegraph.models.compound import ModuleNode
from codegraph.models.tags import CodeGraphNode

FIXTURE = Path(__file__).resolve().parent / "data" / "module_node_full.json"

SKIP_FIELDS = {"qualified_name", "edges", "type"}

# codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization
# Verifies that a LayerGraph deserialization correctly produces a ModuleNode from valid
# serialized data, ensuring round‑trip fidelity of module nodes.
def test_module_node_full_deserialization():
    # codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization::step_0
    # Sets up the test by building a serialized data dictionary and then invoking
    # LayerGraph.deserialize on it to produce the node fixture.
    with open(FIXTURE) as f:
        data = json.load(f)

    node = CodeGraphNode.deserialize(data)

    # codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization::post_0
    # Asserts that the deserialized object is an instance of ModuleNode, confirming that
    # the deserializer produces the correct class type.
    assert isinstance(node, ModuleNode)
    # codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization::post_1
    # Asserts that the type marker in the serialized data matches 'ModuleNode', ensuring
    # the deserializer correctly interprets the node type from input data.
    assert data["type"] == "ModuleNode"
    # codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization::post_2
    # Asserts that the deserialized node has a non‑empty qualified_name attribute,
    # confirming that auto‑generation of the qualified name occurs and is not lost
    # during serialization.
    assert node.qualified_name, "qualified_name should be auto-generated"

    for field, expected in data.items():
        if field in SKIP_FIELDS:
            continue
        actual = getattr(node, field, None)
        # codegraph:test-desc compound.test_module_serialization.test_module_node_full_deserialization::post_3
        # Iterates over expected field values and checks that each field in the
        # deserialized node matches its expected value, verifying full fidelity of all
        # data fields.
        assert actual == expected, (
            f"Field mismatch on '{field}': expected {expected!r}, got {actual!r}"
        )

if __name__ == "__main__":
    test_module_node_full_deserialization()