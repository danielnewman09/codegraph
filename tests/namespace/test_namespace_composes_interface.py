"""Unit test: NamespaceNode COMPOSES InterfaceNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import InterfaceNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface
# Verifies that a NamespaceNode can successfully compose with an InterfaceNode and be
# serialized and deserialized via CompositeEntry and LayerGraph, ensuring correct
# round-trip integrity of the graph structure.
def test_namespace_composes_interface():
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::step_0
    # Sets up the initial state by creating the namespace_node, interface_node, and
    # other necessary objects, providing the foundation for the composition test.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
    ).save()

    namespace_node.interfaces.connect(interface_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_interface.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_0
    # Asserts that the roundtripped node is an instance of NamespaceNode, ensuring that
    # deserialization restores the correct type for the namespace.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::step_1
    # Serializes the namespace_node to a dictionary and then deserializes it back into a
    # CodeGraphNode (roundtripped), advancing the test to verify serialization fidelity.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_1
    # Asserts that the serialized fields of the original namespace node match those of
    # the roundtripped node, ensuring that serialization and deserialization preserve
    # the node's data.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::step_2
    # Retrieves the 'composes' edges from the roundtripped node, extracting the
    # composition relationship data needed for verification.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_2
    # Asserts that exactly one composes edge exists, confirming that a single
    # composition relationship was created between the namespace and the interface.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_3
    # Asserts that the target type of the composes edge is 'InterfaceNode', confirming
    # that the composition relationship targets an interface node.
    assert composes_edges[0]["target_type"] == "InterfaceNode"
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_4
    # Asserts that the target UID of the composes edge matches the interface node's UID,
    # verifying that the composition links to the correct interface.
    assert composes_edges[0]["target_uid"] == interface_node._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::step_3
    # Queries the connected nodes from the composes edges to obtain the list of target
    # nodes, completing the data extraction for the final assertions.
    connected = namespace_node.interfaces.all()
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_5
    # Asserts that exactly one connected node is found from the composes edge, verifying
    # that the composition relationship points to a single target.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_interface.test_namespace_composes_interface::post_6
    # Asserts that the roundtripped node's fields match the original interface node's
    # fields, verifying that the serialize-deserialize process preserves the node's
    # data.
    assert connected[0]._uid_value() == interface_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_interface()