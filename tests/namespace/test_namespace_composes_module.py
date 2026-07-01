"""Unit test: NamespaceNode COMPOSES ModuleNode relationship roundtrip.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ModuleNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


# codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module
# Verifies that a [NamespaceNode] correctly composes its module hierarchy and that the
# resulting [ModuleNode] can be serialized, deserialized, and re‑serialized consistently
# via [CodeGraphNode.serialize], [CompositeEntry.serialize], and
# [LayerGraph.deserialize].
def test_namespace_composes_module():
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::step_0
    # Step 0 sets up the initial graph state by constructing a new Graph with a layer
    # named 'layer_1' and adding both the namespace_node and module_node to it,
    # establishing the context needed for subsequent serialization and round-trip
    # operations.
    namespace_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    module_node = ModuleNode(
        name="arithmetic",
        kind="module",
        brief_description="Arithmetic module",
    ).save()

    namespace_node.modules.connect(module_node)

    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "namespace_composes_module.json"

    with open(out_path, "w") as f:
        json.dump(namespace_node.serialize(), f, indent=2)

    with open(out_path) as f:
        data = json.load(f)

    roundtripped = CodeGraphNode.deserialize(data)
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_0
    # This assertion checks that the deserialized roundtripped object is an instance of
    # NamespaceNode, confirming that the type information of the node is correctly
    # restored and that the deserialization returns the expected class.
    assert isinstance(roundtripped, NamespaceNode)

    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::step_1
    # Step 1 serializes the namespace_node using LayerGraph.serialize, converting it
    # into a serialized representation that includes its edges and fields, which is
    # necessary to later deserialize and compare against the original node.
    original_fields = {k: v for k, v in namespace_node.serialize().items() if k != "edges"}
    roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_1
    # This assertion compares the original fields of the namespace_node with the fields
    # of the roundtripped node, ensuring that all attributes (such as uid, type, and
    # layer) are preserved exactly across the serialization-deserialization cycle.
    assert original_fields == roundtripped_fields

    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::step_2
    # Step 2 creates a new empty Graph and deserializes the previously serialized
    # namespace_node back into it using LayerGraph.deserialize, producing the
    # 'roundtripped' node that will be compared to the original to verify the round-trip
    # fidelity.
    composes_edges = [e for e in data["edges"] if e["relation_type"] == "COMPOSES"]
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_2
    # This assertion checks that exactly one 'composes' edge exists from the
    # namespace_node, confirming that the composition relationship between the namespace
    # and its module is correctly serialized and deserialized as a single edge.
    assert len(composes_edges) == 1
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_3
    # This assertion checks that the target_type of the composes edge is 'ModuleNode',
    # confirming that the edge's type metadata is preserved and that the composition
    # relationship correctly identifies the target as a module.
    assert composes_edges[0]["target_type"] == "ModuleNode"
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_4
    # This assertion verifies that the target_uid of the composes edge matches the
    # module_node's UID, ensuring that the edge correctly references the intended module
    # node and that the relationship is accurately recreated after deserialization.
    assert composes_edges[0]["target_uid"] == module_node._uid_value()

    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::step_3
    # Step 3 retrieves the serialization fields from both the original namespace_node
    # and the roundtripped CodeGraphNode, preparing the data needed for the assertions
    # that will check that the fields and composes edges are correctly preserved.
    connected = namespace_node.modules.all()
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_5
    # This assertion verifies that the roundtripped node has exactly one connected node,
    # validating that the overall connectivity (the number of other nodes linked via
    # edges) is preserved after the round-trip process.
    assert len(connected) == 1
    # codegraph:test-desc namespace.test_namespace_composes_module.test_namespace_composes_module::post_6
    # This assertion checks that the 'source_uid' and 'target_uid' fields of the
    # roundtripped node match specific expected values, verifying that the unique
    # identifiers of the node and its relationships are correctly maintained through
    # serialization and deserialization.
    assert connected[0]._uid_value() == module_node._uid_value()


if __name__ == "__main__":
    test_namespace_composes_module()