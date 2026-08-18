from codegraph.backends import get_backend
"""Unit test: NamespaceNode COMPOSES EnumNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import EnumNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum
# Verifies that a NamespaceNode, which contains an EnumNode, can be composed,
# serialized, and deserialized correctly within a LayerGraph, ensuring the integrity of
# composed enum structures in the graph model.
def test_namespace_composes_enum():
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::step_0
    # Sets up the test by creating a NamespaceNode with an EnumNode field, preparing the
    # initial state for the round-trip serialization test.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
        source="test",
    ).save()

    namespace_node.enums.connect(enum_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_enum.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_0
    # Verifies that the deserialized object is indeed a NamespaceNode, confirming that
    # the type information was correctly preserved during serialization and
    # deserialization.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::step_1
    # Serializes the NamespaceNode and its contained EnumNode to a dictionary, capturing
    # the original structure and relationships for later comparison.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_1
    # Ensures that the serialized and deserialized NamespaceNode have identical field
    # values, verifying that all scalar data is faithfully preserved.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::step_2
    # Deserializes the dictionary back into a CodeGraphNode object, recreating the nodes
    # and edges from the serialized data.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_2
    # Confirms that the deserialized node has exactly one 'composes' edge, validating
    # that the composition relationship to EnumNode was correctly reconstructed.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_3
    # Checks that the target type of the 'composes' edge is 'EnumNode', verifying that
    # the relationship points to the correct type of composed node.
    assert composes_edges[0]["target_type"] == "EnumNode"
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_4
    # Verifies that the target UID of the 'composes' edge matches the UID of the
    # original EnumNode, ensuring that the specific composed node is correctly linked.
    assert composes_edges[0]["target_key"] == enum_node.canonical_key

    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::step_3
    # Extracts the 'composes' edges from the deserialized node and queries connected
    # nodes, setting up data for assertions on the round-tripped structure.
    connected = get_backend().graph.composed_children(namespace_node, EnumNode)
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_5
    # Checks that exactly one node is connected to the deserialized namespace via
    # 'composes' edges, confirming the cardinality of the composition relationship.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_enum.test_namespace_composes_enum::post_6
    # Compares the deserialized connected node with the original EnumNode for equality,
    # verifying that the entire node (including its data) was accurately reconstructed.
    assert connected[0].canonical_key == enum_node.canonical_key


if __name__ == "__main__":
    test_namespace_composes_enum()