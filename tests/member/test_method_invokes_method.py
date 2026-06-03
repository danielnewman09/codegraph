"""Unit test: MethodNode INVOKES MethodNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_method_invokes_method():
    caller = MethodNode(
        name="handleEquals",
        kind="method",
        type_signature="void",
        argsstring="()",
        visibility="private",
    ).save()

    callee = MethodNode(
        name="performCalculation",
        kind="method",
        type_signature="void",
        argsstring="()",
        visibility="private",
    ).save()

    caller.invokes.connect(callee)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "method_invokes_method.json"

    with open(out_path, "w") as f:
        json.dump(caller.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.from_json(data)
    assert isinstance(roundtripped, MethodNode)

    original_fields = {k: v for k, v in caller.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    invokes_edges = [e for e in data["edges"] if e["relation_type"] == "INVOKES"]
    assert len(invokes_edges) == 1
    assert invokes_edges[0]["target_type"] == "MethodNode"
    assert invokes_edges[0]["target_uid"] == callee._uid_value()

    connected = caller.invokes.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == callee._uid_value()


if __name__ == "__main__":
    test_method_invokes_method()