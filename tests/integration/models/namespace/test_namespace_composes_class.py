"""Unit test: NamespaceNode COMPOSES ClassNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class
# Verifies that the composite namespace and class serialization/deserialization pipeline
# correctly reconstructs a NamespaceNode from a ClassNode, ensuring round-trip integrity
# of the code graph model.
def test_namespace_composes_class():
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::step_0
    # Creates the initial namespace_node and class_node fixtures and establishes their
    # composition relationship, setting up the test scenario for round-trip
    # verification.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    namespace_node.classes.connect(class_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_class.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_0
    # Verifies that the round-tripped node is still a NamespaceNode, confirming that the
    # serialization/deserialization process preserves the node type.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::step_1
    # Serializes the original namespace_node (along with its class_node composition)
    # into a dictionary format, preserving all fields and structure as the first stage
    # of the round-trip verification.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_1
    # Verifies that all original node fields (such as name, attributes) are preserved
    # after the round-trip, confirming data integrity during
    # serialization/deserialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::step_2
    # Deserializes the dictionary produced in step_1 back into a CodeGraphNode object
    # (roundtripped), completing the round-trip and generating the structure that will
    # be validated in subsequent assertions.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_2
    # Checks that there is exactly one composition edge, confirming that the namespace
    # contains exactly one class composition as expected.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_3
    # Verifies that the target of the composition edge is indeed of type ClassNode,
    # confirming that the type information is correctly maintained during the
    # round-trip.
    assert composes_edges[0]["target_type"] == "ClassNode"
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_4
    # Verifies that the composition edge points to the correct class node by matching
    # its unique identifier, ensuring the relationship is accurately preserved.
    assert composes_edges[0]["target_uid"] == class_node._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::step_3
    # Extracts the composed graph edge from the deserialized roundtripped node,
    # isolating the connection between the namespace and its contained class for
    # detailed inspection.
    connected = GraphRepository.composed_children(namespace_node, ClassNode)
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_5
    # Checks that there is exactly one connected node via the composition relationship,
    # confirming the graph's connectivity is correctly restored.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_class.test_namespace_composes_class::post_6
    # Verifies that the connected node retrieved via the composition edge is equal to
    # the original class_node, ensuring the graph connection is correctly reconstructed.
    assert connected[0]._uid_value() == class_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_class()