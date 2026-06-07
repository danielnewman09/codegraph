"""Unit test: NamespaceNode COMPOSES FunctionNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.member import FunctionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_namespace_composes_function():
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    function_node = FunctionNode(
        name="formatResult",
        kind="function",
        type_signature="string",
        argsstring="(double value)",
        brief_description="Formats a numeric result as a string.",
    ).save()

    namespace_node.functions.connect(function_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_function.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    assert isinstance(roundtripped, NamespaceNode)

    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    assert len(composes_edges) == 1
    assert composes_edges[0]["target_type"] == "FunctionNode"
    assert composes_edges[0]["target_uid"] == function_node._uid_value()

    connected = namespace_node.functions.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == function_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_function()