"""Unit test: InterfaceNode COMPOSES MethodNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import InterfaceNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method
# Verifies that an InterfaceNode correctly composes and serializes a MethodNode through
# CompositeEntry and LayerGraph operations, ensuring structural integrity of graph-based
# interface representations.
def test_interface_composes_method():
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::step_0
    # Sets up the test by creating the fixture objects (interface_node, method_node) and
    # preparing them for use in subsequent steps. This establishes the initial state
    # required for the round-trip operation.
    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
        is_abstract=True,
    ).save()

    method_node = MethodNode(
        name="calculate",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(Operation op, double a, double b)",
        visibility="public",
    ).save()

    interface_node.methods.connect(method_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "interface_composes_method.json"

    with open(out_path, "w") as f:
        json.dump(interface_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_0
    # Verifies that the roundtripped object is still an instance of InterfaceNode. This
    # ensures the deserialization preserved the node's type correctly.
    assert isinstance(roundtripped, InterfaceNode)

    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::step_1
    # Performs the first action by serializing the interface_node using
    # CodeGraphNode.serialize. This produces a JSON-serializable representation of the
    # node and its composition edges.
    original_fields = {k: v for k, v in interface_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_1
    # Verifies that the original fields of the interface_node exactly match the fields
    # of the roundtripped object. This ensures the round-trip preserves all field data
    # without corruption.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::step_2
    # Performs the second action by deserializing the serialized data back into a
    # CodeGraphNode using CompositeEntry.deserialize. This reconstructs the node from
    # its serialized form to test round-trip fidelity.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_2
    # Verifies that there is exactly one 'composes' edge in the serialized output. This
    # confirms the interface_node has a single composition relationship.
    assert len(composes_edges) == 1
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_3
    # Verifies that the target type of the composes edge is 'MethodNode'. This ensures
    # the composition correctly points to a method node.
    assert composes_edges[0]["target_type"] == "MethodNode"
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_4
    # Verifies that the target unique identifier (UID) of the composes edge matches the
    # UID of the method_node. This ensures the composition edge points to the correct
    # method instance.
    assert composes_edges[0]["target_uid"] == method_node._uid_value()

    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::step_3
    # Performs the final action by extracting the composition edges and connected nodes
    # from the roundtripped object. This prepares the data needed for verifying the
    # composition relationship.
    connected = GraphRepository.composed_children(interface_node, MethodNode)
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_5
    # Verifies that there is exactly one connected node in the roundtripped object. This
    # confirms the composition relationship was correctly reconstructed during
    # deserialization.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_interface_composes_method.test_interface_composes_method::post_6
    # Verifies that the connected node's UID matches the method_node's UID. This ensures
    # the reconstructed composition points to the correct method node.
    assert connected[0]._uid_value() == method_node._uid_value()


if __name__ == "__main__":
    test_interface_composes_method()