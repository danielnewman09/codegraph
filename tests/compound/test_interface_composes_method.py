"""Unit test: InterfaceNode COMPOSES MethodNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import InterfaceNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_interface_composes_method():
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

    roundtripped = CodeGraphNode.from_json(data)
    assert isinstance(roundtripped, InterfaceNode)

    original_fields = {k: v for k, v in interface_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    assert len(composes_edges) == 1
    assert composes_edges[0]["target_type"] == "MethodNode"
    assert composes_edges[0]["target_uid"] == method_node._uid_value()

    connected = interface_node.methods.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == method_node._uid_value()


if __name__ == "__main__":
    test_interface_composes_method()