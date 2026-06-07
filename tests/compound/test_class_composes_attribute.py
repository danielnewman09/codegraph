"""Unit test: ClassNode COMPOSES AttributeNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_class_composes_attribute():
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    attr_node = AttributeNode(
        name="precision",
        kind="attribute",
        type_signature="int",
        visibility="public",
    ).save()

    class_node.attributes.connect(attr_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_composes_attribute.json"

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
    assert composes_edges[0]["target_type"] == "AttributeNode"
    assert composes_edges[0]["target_uid"] == attr_node._uid_value()

    connected = class_node.attributes.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == attr_node._uid_value()


if __name__ == "__main__":
    test_class_composes_attribute()