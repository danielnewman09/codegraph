"""Unit test: ClassNode INHERITS_FROM ClassNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_class_inherits():
    base_class = ClassNode(
        name="BaseWindow",
        kind="class",
        brief_description="Abstract base window class",
        is_abstract=True,
    ).save()

    derived_class = ClassNode(
        name="CalculatorWindow",
        kind="class",
        brief_description="Main application window for the calculator",
    ).save()

    derived_class.base.connect(base_class)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "class_inherits.json"

    with open(out_path, "w") as f:
        json.dump(derived_class.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.from_json(data)
    assert isinstance(roundtripped, ClassNode)

    original_fields = {k: v for k, v in derived_class.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    inherits_edges = [e for e in data["edges"] if e["relation_type"] == "INHERITS_FROM"]
    assert len(inherits_edges) == 1
    assert inherits_edges[0]["target_type"] == "ClassNode"
    assert inherits_edges[0]["target_uid"] == base_class._uid_value()

    connected = derived_class.base.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == base_class._uid_value()


if __name__ == "__main__":
    test_class_inherits()