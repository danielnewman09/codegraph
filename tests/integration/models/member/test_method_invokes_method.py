from codegraph.backends import get_backend
"""Unit test: MethodNode INVOKES MethodNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method
# This test verifies that a method invocation is correctly serialized and deserialized
# by the CodeGraph system, ensuring the integrity of method node data across the graph
# representation.
def test_method_invokes_method():
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::step_0
    # Creates the caller MethodNode with an invokes relationship to the callee, setting
    # up the initial state for testing method invocation relationships.
    caller = MethodNode(
        name="handleEquals",
        kind="method",
        type_signature="void",
        argsstring="()",
        visibility="private",
        source="test",
    ).save()

    callee = MethodNode(
        name="performCalculation",
        kind="method",
        type_signature="void",
        argsstring="()",
        visibility="private",
        source="test",
    ).save()

    caller.invokes.connect(callee)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "method_invokes_method.json"

    with open(out_path, "w") as f:
        json.dump(caller.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_0
    # Verifies that the deserialized node is still a MethodNode, ensuring the type is
    # preserved through serialization and deserialization.
    assert isinstance(roundtripped, MethodNode)

    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::step_1
    # Serializes the original caller MethodNode and then deserializes it to create the
    # roundtripped node, enabling comparison of the original and reconstructed objects.
    original_fields = {k: v for k, v in caller.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_1
    # Verifies that all original fields are identical after serialization and
    # deserialization, ensuring data integrity during the roundtrip.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::step_2
    # Retrieves the invokes edges from the roundtripped MethodNode, advancing the test
    # to inspect the captured relationship.
    invokes_edges = [e for e in data["edges"] if e["relation_type"] == "INVOKES"]
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_2
    # Verifies that exactly one invokes edge exists, ensuring the invokes relationship
    # is correctly captured and not duplicated.
    assert len(invokes_edges) == 1
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_3
    # Verifies that the target type of the invokes edge is 'MethodNode', ensuring the
    # relationship correctly identifies the target method type.
    assert invokes_edges[0]["target_type"] == "MethodNode"
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_4
    # Verifies that the target UID of the invokes edge matches the callee's UID,
    # ensuring the edge correctly points to the expected method.
    assert invokes_edges[0]["target_uid"] == callee._uid_value()

    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::step_3
    # Retrieves connected nodes from the roundtripped MethodNode, advancing the test to
    # verify the connected structure after deserialization.
    connected = get_backend().graph.outgoing_by_relation(caller, "INVOKES")
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_5
    # Verifies that exactly one connected node exists, ensuring the relationships are
    # correctly and uniquely stored after deserialization.
    assert len(connected) == 1
    # codegraph:test-desc member.test_method_invokes_method.test_method_invokes_method::post_6
    # Verifies that the connected node matches the expected value, ensuring the
    # completeness and correctness of the relationship after deserialization.
    assert connected[0]._uid_value() == callee._uid_value()


if __name__ == "__main__":
    test_method_invokes_method()