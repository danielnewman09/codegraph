"""Unit test: NamespaceNode COMPOSES NamespaceNode relationship roundtrip (nesting).

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_namespace_composes_namespace():
    outer_ns = NamespaceNode(
        name="outer",
        kind="namespace",
        description="Outer namespace",
    ).save()

    inner_ns = NamespaceNode(
        name="inner",
        kind="namespace",
        description="Inner nested namespace",
    ).save()

    outer_ns.namespaces.connect(inner_ns)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_namespace.json"

    with open(out_path, "w") as f:
        json.dump(outer_ns.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    assert isinstance(roundtripped, NamespaceNode)

    original_fields = {k: v for k, v in outer_ns.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    assert original_fields == roundtripped_fields

    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    assert len(composes_edges) == 1
    assert composes_edges[0]["target_type"] == "NamespaceNode"
    assert composes_edges[0]["target_uid"] == inner_ns._uid_value()

    connected = outer_ns.namespaces.all()
    assert len(connected) == 1
    assert connected[0]._uid_value() == inner_ns._uid_value()


if __name__ == "__main__":
    test_namespace_composes_namespace()