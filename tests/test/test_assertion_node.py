"""Unit tests for AssertionNode model."""

import json
from pathlib import Path

from codegraph.models.test import AssertionNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestAssertionNodeModel:
    """Test AssertionNode creation and field defaults."""

    def test_kind_defaults_to_assertion(self):
        node = AssertionNode()
        assert node.kind == "assertion"

    def test_uid_auto_generated(self):
        node = AssertionNode()
        assert len(node.uid) > 0

    def test_phase_required(self):
        """phase is a required field — constructing without it uses default."""
        # neomodel StringProperty(required=True) is enforced at save time,
        # not construction time.  We test the field is declared required.
        props = AssertionNode.defined_properties()
        assert props["phase"].required is True

    def test_order_defaults_to_zero(self):
        node = AssertionNode()
        assert node.order == 0

    def test_operator_defaults_to_eq(self):
        node = AssertionNode()
        assert node.operator == "=="

    def test_description_default_empty(self):
        node = AssertionNode()
        assert node.description == ""

    def test_tags_default_empty_list(self):
        node = AssertionNode()
        assert node.tags == []

    def test_llm_fields_include_phase(self):
        assert "phase" in AssertionNode._llm_fields

    def test_llm_fields_include_operator(self):
        assert "operator" in AssertionNode._llm_fields

    def test_llm_fields_include_order(self):
        assert "order" in AssertionNode._llm_fields

    def test_llm_fields_include_description(self):
        assert "description" in AssertionNode._llm_fields

    def test_identity_fields(self):
        assert AssertionNode._identity_fields == ("qualified_name",)

    def test_serialize_includes_phase(self):
        node = AssertionNode(
            qualified_name="tests::test_update::test_single::post_0",
            phase="post",
            operator="==",
        )
        serialized = node.serialize()
        assert serialized["phase"] == "post"
        assert serialized["operator"] == "=="

    def test_serialize_includes_type_discriminator(self):
        node = AssertionNode(
            qualified_name="tests::test_update::test_single::post_0",
            phase="post",
        )
        serialized = node.serialize()
        assert serialized["type"] == "AssertionNode"

    def test_deserialize_with_phase(self):
        data = {
            "type": "AssertionNode",
            "qualified_name": "tests::test_update::test_single::post_0",
            "kind": "assertion",
            "phase": "post",
            "operator": "==",
            "order": 0,
            "description": "Result matches expected value.",
        }
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, AssertionNode)
        assert node.phase == "post"
        assert node.operator == "=="
        assert node.order == 0

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        qn = "tests::test_update::test_single::post_0"
        data = {
            "type": "AssertionNode",
            "qualified_name": qn,
            "kind": "assertion",
            "phase": "post",
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid(qn)
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify assertion_node_full.json deserializes correctly."""
        with open(DATA_DIR / "assertion_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, AssertionNode)
        assert node.phase == data["phase"]
        assert node.operator == data["operator"]
        assert node.order == data["order"]
        assert node.qualified_name == data["qualified_name"]


class TestAssertionNodeRegistry:
    """Test that AssertionNode is registered in CodeGraphNode._registry."""

    def test_assertion_node_in_registry(self):
        assert "AssertionNode" in CodeGraphNode._registry

    def test_assertion_node_registry_class(self):
        assert CodeGraphNode._registry["AssertionNode"] is AssertionNode