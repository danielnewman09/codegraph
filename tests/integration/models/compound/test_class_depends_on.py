"""Unit test: ClassNode DEPENDS_ON ClassNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc compound.test_class_depends_on.test_class_depends_on
# Tests the serialization and deserialization of ClassNode with dependency edges to
# ensure round-tripping preserves the node type, fields, and dependency relationships
# correctly.
def test_class_depends_on():
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::step_0
    # Initializes the test by creating original field values, a dependent ClassNode, a
    # dependency ClassNode, and establishing a dependency edge between them.
    dependency = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    dependent = ClassNode(
        name="CalculatorWindow",
        kind="class",
        brief_description="Main application window for the calculator",
    ).save()

    dependent.depends_on.connect(dependency)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_depends_on.json"

    with open(out_path, "w") as f:
        json.dump(dependent.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_0
    # Verifies that the round-tripped object is an instance of ClassNode, ensuring the
    # deserialization process correctly restores the node type.
    assert isinstance(roundtripped, ClassNode)

    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::step_1
    # Serializes the dependent ClassNode into a CompositeEntry using
    # CompositeEntry.serialize, capturing the node's data and its dependency edge.
    original_fields = {k: v for k, v in dependent.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_1
    # Asserts that the original field values are equal to those in the round-tripped
    # node, confirming field preservation during serialization and deserialization.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::step_2
    # Deserializes the CompositeEntry back into a ClassNode using
    # LayerGraph.deserialize, completing the round-trip from node to serialized form and
    # back.
    depends_edges = [e for e in data["edges"] if e["relation_type"] == "DEPENDS_ON"]
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_2
    # Checks that exactly one dependency edge exists in the round-tripped node,
    # validating that the dependency relationship was not duplicated or lost.
    assert len(depends_edges) == 1
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_3
    # Confirms that the target type of the dependency edge is 'ClassNode', ensuring the
    # type metadata is correctly preserved during the round-trip.
    assert depends_edges[0]["target_type"] == "ClassNode"
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_4
    # Verifies that the target UID of the dependency edge matches the UID of the
    # dependency fixture, ensuring the correct dependency link is maintained.
    assert depends_edges[0]["target_uid"] == dependency._uid_value()

    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::step_3
    # Retrieves the dependency edges from the round-tripped ClassNode to extract the
    # connected nodes for subsequent verification.
    connected = GraphRepository.outgoing_by_relation(dependent, "DEPENDS_ON")
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_5
    # Asserts that exactly one connected node is retrieved from the round-tripped node,
    # confirming that the dependency graph structure is preserved.
    assert len(connected) == 1
    # codegraph:test-desc compound.test_class_depends_on.test_class_depends_on::post_6
    # Validates that the connected node is the expected dependency node, ensuring the
    # dependency relationship is accurately restored in the graph.
    assert connected[0]._uid_value() == dependency._uid_value()


if __name__ == "__main__":
    test_class_depends_on()