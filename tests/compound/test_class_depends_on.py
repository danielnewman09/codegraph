"""Unit test: ClassNode DEPENDS_ON ClassNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_class_depends_on():
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
    assert isinstance(roundtripped, ClassNode)

    original_fields = {k: v for k, v in dependent.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    depends_edges = [e for e in data["edges"] if e["relation_type"] == "DEPENDS_ON"]
    assert len(depends_edges) == 1
    assert depends_edges[0]["target_type"] == "ClassNode"
    assert depends_edges[0]["target_uid"] == dependency._uid_value()

    connected = dependent.depends_on.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == dependency._uid_value()


if __name__ == "__main__":
    test_class_depends_on()