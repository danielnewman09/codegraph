from codegraph.backends import get_backend
"""Integration test: ClassNode COMPOSES MethodNode relationship roundtrip.

Backend-agnostic — queries through GraphRepository instead of
neomodel's ``.all()`` relationship managers.
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


def test_class_composes_method():
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
        source="test",
    ).save()

    method_node = MethodNode(
        name="add",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(double a, double b)",
        visibility="public",
        source="test",
    ).save()

    class_node.methods.connect(method_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_composes_method.json"

    with open(out_path, "w") as f:
        json.dump(class_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    assert isinstance(roundtripped, ClassNode)

    original_fields = {k: v for k, v in class_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    assert len(composes_edges) == 1
    assert composes_edges[0]["target_type"] == "MethodNode"
    assert composes_edges[0]["target_uid"] == method_node._uid_value()

    # Backend-agnostic: use get_backend().graph.composed_children() instead of .methods.all()
    connected = get_backend().graph.composed_children(class_node, MethodNode)
    assert len(connected) == 1
    assert connected[0]._uid_value() == method_node._uid_value()


if __name__ == "__main__":
    test_class_composes_method()
