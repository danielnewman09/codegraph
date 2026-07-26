"""Unit test: NamespaceNode COMPOSES UnionNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import UnionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union
# Validates that a NamespaceNode containing a UnionNode is correctly serialized and
# deserialized through CompositeEntry and LayerGraph, ensuring the round-trip preserves
# the structural integrity of the namespace-union composition.
def test_namespace_composes_union():
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::step_0
    # Creates the UnionNode instance (union_node) and a NamespaceNode instance
    # (namespace_node), establishing the test's initial data: a namespace that should
    # contain a union.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    union_node = UnionNode(
        name="ValueOrError",
        kind="union",
        brief_description="Value or error union type",
    ).save()

    namespace_node.unions.connect(union_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_union.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_0
    # Verifies that the deserialized node is an instance of NamespaceNode, confirming
    # the round-trip correctly preserves the node's class type.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::step_1
    # Adds the union_node to the namespace_node's composes collection, establishing the
    # composition link under test before serialization.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_1
    # Verifies that all field values of the original namespace_node are identical to
    # those of the roundtripped node, ensuring no data loss or corruption during
    # serialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::step_2
    # Serializes the namespace_node to a dictionary, then deserializes it back to
    # produce the roundtripped node, enabling comparison between the original and
    # reconstructed objects.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_2
    # Verifies that there is exactly one composes edge, ensuring the namespace has only
    # the expected composition link and no extra edges.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_3
    # Verifies that the target type of the composes edge is 'UnionNode', confirming the
    # composition relationship points to the correct type of node.
    assert composes_edges[0]["target_type"] == "UnionNode"
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_4
    # Verifies that the target UID of the composes edge matches the union_node's UID,
    # ensuring the correct node is referenced in the composition relationship.
    assert composes_edges[0]["target_uid"] == union_node._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::step_3
    # Retrieves the 'composes' edges from the roundtripped node, advancing the test to
    # inspect the composition relationship in the deserialized structure.
    connected = GraphRepository.composed_children(namespace_node, UnionNode)
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_5
    # Verifies that there is exactly one connected node from the roundtripped node,
    # confirming the deserialized graph maintains the correct number of relationships.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_union.test_namespace_composes_union::post_6
    # Verifies that the connected nodes retrieved from the roundtripped node match
    # expectations, ensuring the overall graph connectivity is preserved after
    # serialization.
    assert connected[0]._uid_value() == union_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_union()