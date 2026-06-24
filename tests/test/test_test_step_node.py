"""Unit tests for TestStepNode model."""

import json
from pathlib import Path

from codegraph.models.test import TestStepNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestTestStepNodeModel:
    """Test TestStepNode creation and field defaults."""

    def test_kind_defaults_to_test_step(self):
        node = TestStepNode()
        assert node.kind == "test_step"

    def test_uid_auto_generated(self):
        node = TestStepNode()
        assert len(node.uid) > 0

    def test_order_defaults_to_zero(self):
        node = TestStepNode()
        assert node.order == 0

    def test_description_default_empty(self):
        node = TestStepNode()
        assert node.description == ""

    def test_body_start_defaults_to_zero(self):
        node = TestStepNode()
        assert node.body_start == 0

    def test_body_end_defaults_to_zero(self):
        node = TestStepNode()
        assert node.body_end == 0

    def test_body_start_can_be_set(self):
        node = TestStepNode(body_start=45, body_end=48)
        assert node.body_start == 45
        assert node.body_end == 48

    def test_tags_default_empty_list(self):
        node = TestStepNode()
        assert node.tags == []

    def test_llm_fields_include_order(self):
        assert "order" in TestStepNode._llm_fields

    def test_llm_fields_include_description(self):
        assert "description" in TestStepNode._llm_fields

    def test_identity_fields(self):
        assert TestStepNode._identity_fields == ("qualified_name",)

    def test_serialize_includes_description(self):
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            description="Call engine.set_target(30)",
            order=0,
        )
        serialized = node.serialize()
        assert serialized["description"] == "Call engine.set_target(30)"
        assert serialized["order"] == 0

    def test_serialize_includes_type_discriminator(self):
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
        )
        serialized = node.serialize()
        assert serialized["type"] == "TestStepNode"

    def test_serialize_excludes_body_start_end(self):
        """body_start/body_end are not in _llm_fields, excluded from llm serialization."""
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            body_start=45,
            body_end=48,
        )
        serialized = node.serialize()
        assert "body_start" not in serialized
        assert "body_end" not in serialized

    def test_serialize_all_includes_body_start_end(self):
        """body_start/body_end included when fields='all'."""
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            body_start=45,
            body_end=48,
        )
        serialized = node.serialize(fields="all")
        assert serialized["body_start"] == 45
        assert serialized["body_end"] == 48

    def test_deserialize_with_description(self):
        data = {
            "type": "TestStepNode",
            "qualified_name": "tests::test_update::test_single::step_0",
            "kind": "test_step",
            "order": 1,
            "description": "Assert result is 30.",
        }
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestStepNode)
        assert node.order == 1
        assert node.description == "Assert result is 30."

    def test_deserialize_with_body_range(self):
        """TestStepNode deserializes body_start/body_end."""
        data = {
            "type": "TestStepNode",
            "qualified_name": "tests::test_update::test_single::step_0",
            "kind": "test_step",
            "order": 0,
            "body_start": 45,
            "body_end": 48,
        }
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestStepNode)
        assert node.body_start == 45
        assert node.body_end == 48

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        qn = "tests::test_update::test_single::step_0"
        data = {
            "type": "TestStepNode",
            "qualified_name": qn,
            "kind": "test_step",
            "order": 0,
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid(qn)
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify test_step_node_full.json deserializes correctly."""
        with open(DATA_DIR / "test_step_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestStepNode)
        assert node.order == data["order"]
        assert node.description == data["description"]
        assert node.qualified_name == data["qualified_name"]
        assert node.body_start == data["body_start"]
        assert node.body_end == data["body_end"]


class TestTestStepNodeRegistry:
    """Test that TestStepNode is registered in CodeGraphNode._registry."""

    def test_test_step_node_in_registry(self):
        assert "TestStepNode" in CodeGraphNode._registry

    def test_test_step_node_registry_class(self):
        assert CodeGraphNode._registry["TestStepNode"] is TestStepNode


class TestTestStepNodeImplementation:
    """Test HAS_IMPLEMENTATION relationship on TestStepNode."""

    def test_has_implementation_ref_relationship(self):
        """TestStepNode should have implementation_ref RelationshipTo ImplementationNode."""
        from neomodel import RelationshipTo

        assert hasattr(TestStepNode, "implementation_ref")
        assert isinstance(TestStepNode.implementation_ref, RelationshipTo)
        assert (
            TestStepNode.implementation_ref.definition["relation_type"]
            == "HAS_IMPLEMENTATION"
        )

    def test_serialize_relationships_includes_implementation(self):
        """serialize_relationships() should list the HAS_IMPLEMENTATION edge."""
        rels = TestStepNode.serialize_relationships()
        impl_rels = [r for r in rels if r["relation_type"] == "HAS_IMPLEMENTATION"]
        assert len(impl_rels) == 1
        assert impl_rels[0]["attr"] == "implementation_ref"
        assert impl_rels[0]["direction"] == "OUTGOING"

    def test_implementation_ref_not_in_llm_fields(self):
        """implementation_ref is a relationship, not a property field."""
        assert "implementation_ref" not in TestStepNode._llm_fields