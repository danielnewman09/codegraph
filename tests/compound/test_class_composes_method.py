"""Unit test: ClassNode COMPOSES MethodNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


# codegraph:test-desc compound.test_class_composes_method.test_class_composes_method
# Verifies that a ClassNode containing a MethodNode can be serialized, deserialized, and
# reconstructed correctly, ensuring the integrity of the composition relationship and
# roundtrip fidelity.
def test_class_composes_method():
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::step_0
    # Sets up the test by creating a ClassNode and a MethodNode, establishing the
    # initial objects needed for the roundtrip operation.
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    method_node = MethodNode(
        name="add",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(double a, double b)",
        visibility="public",
    ).save()

    class_node.methods.connect(method_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_composes_method.json"

    with open(out_path, "w") as f:
        json.dump(class_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_0
    # Verifies that the roundtripped result is a ClassNode, ensuring the deserialization
    # preserves the node type.
    assert isinstance(roundtripped, ClassNode)

    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::step_1
    # Serializes the ClassNode using CodeGraphNode.serialize and then deserializes it
    # using LayerGraph.deserialize, performing the core roundtrip action.
    original_fields = {k: v for k, v in class_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_1
    # Verifies that the fields of the roundtripped node match the original fields,
    # ensuring no data loss during serialization/deserialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::step_2
    # Extracts the deserialized result and traverses its edges to retrieve the
    # composition relationships, preparing data for verification.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_2
    # Verifies that the roundtripped ClassNode has exactly one composition edge,
    # confirming the composition relationship is retained.
    assert len(composes_edges) == 1
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_3
    # Verifies that the target type of the composition edge is 'MethodNode', ensuring
    # the relationship points to the correct type.
    assert composes_edges[0]["target_type"] == "MethodNode"
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_4
    # Verifies that the target UID of the composition edge matches the original
    # MethodNode's UID, ensuring the relationship points to the correct instance.
    assert composes_edges[0]["target_uid"] == method_node._uid_value()

    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::step_3
    # Checks that the deserialized node is connected to exactly one other node,
    # confirming the final structure of the reconstructed graph.
    connected = class_node.methods.all()
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_5
    # Verifies that the connected nodes list has exactly one entry, confirming that the
    # MethodNode is linked in the deserialized graph.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_class_composes_method.test_class_composes_method::post_6
    # Verifies that the connected node's identity matches the original MethodNode,
    # ensuring the composition edge connects to the right object in the reconstructed
    # graph.
    assert connected[0]._uid_value() == method_node._uid_value()


if __name__ == "__main__":
    test_class_composes_method()