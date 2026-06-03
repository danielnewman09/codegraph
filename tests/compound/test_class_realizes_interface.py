"""Unit test: ClassNode REALIZES InterfaceNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode, InterfaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_class_realizes_interface():
    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
        is_abstract=True,
    ).save()

    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    class_node.realizes.connect(interface_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_realizes_interface.json"

    with open(out_path, "w") as f:
        json.dump(class_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.from_json(data)
    assert isinstance(roundtripped, ClassNode)

    original_fields = {k: v for k, v in class_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    realizes_edges = [e for e in data["edges"] if e["relation_type"] == "REALIZES"]
    assert len(realizes_edges) == 1
    assert realizes_edges[0]["target_type"] == "InterfaceNode"
    assert realizes_edges[0]["target_uid"] == interface_node._uid_value()

    connected = class_node.realizes.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == interface_node._uid_value()


if __name__ == "__main__":
    test_class_realizes_interface()