"""Unit tests for TestNode model."""

import json
from pathlib import Path

from codegraph.models.test import TestNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestTestNodeModel:
    """Test TestNode creation and field defaults."""

    def test_kind_defaults_to_test(self):
        node = TestNode()
        assert node.kind == "test"

    def test_uid_auto_generated(self):
        """UniqueIdProperty auto-generates a UUID for uid when no value is provided."""
        node = TestNode()
        assert len(node.uid) > 0
        assert node.qualified_name == ""

    def test_qualified_name_explicit_set(self):
        node = TestNode(qualified_name="tests::test_update::test_single_field")
        assert node.qualified_name == "tests::test_update::test_single_field"

    def test_test_name_default_empty(self):
        node = TestNode()
        assert node.test_name == ""

    def test_test_module_default_empty(self):
        node = TestNode()
        assert node.test_module == ""

    def test_method_defaults_to_automated(self):
        node = TestNode()
        assert node.method == "automated"

    def test_description_default_empty(self):
        node = TestNode()
        assert node.description == ""

    def test_tags_default_empty_list(self):
        node = TestNode()
        assert node.tags == []

    def test_doc_embedding_default_empty(self):
        node = TestNode()
        assert node.doc_embedding == []

    def test_llm_fields_include_test_name(self):
        assert "test_name" in TestNode._llm_fields

    def test_llm_fields_include_test_module(self):
        assert "test_module" in TestNode._llm_fields

    def test_llm_fields_include_method(self):
        assert "method" in TestNode._llm_fields

    def test_llm_fields_include_description(self):
        assert "description" in TestNode._llm_fields

    def test_llm_fields_include_qualified_name(self):
        assert "qualified_name" in TestNode._llm_fields

    def test_llm_fields_exclude_embedding(self):
        assert "doc_embedding" not in TestNode._llm_fields

    def test_identity_fields(self):
        assert TestNode._identity_fields == ("qualified_name",)

    def test_serialize_includes_test_name(self):
        node = TestNode(
            qualified_name="tests::test_update::test_single_field",
            test_name="test_single_field",
        )
        serialized = node.serialize()
        assert serialized["test_name"] == "test_single_field"

    def test_serialize_excludes_embedding(self):
        node = TestNode(
            qualified_name="tests::test_update::test_single_field",
            doc_embedding=[0.1, 0.2, 0.3],
        )
        serialized = node.serialize()
        assert "doc_embedding" not in serialized

    def test_serialize_includes_type_discriminator(self):
        node = TestNode(qualified_name="tests::test_update::test_single_field")
        serialized = node.serialize()
        assert serialized["type"] == "TestNode"

    def test_deserialize_with_test_name(self):
        data = {
            "type": "TestNode",
            "qualified_name": "tests::test_update::test_single_field",
            "kind": "test",
            "test_name": "test_single_field",
            "test_module": "tests.test_update",
            "method": "automated",
            "description": "Verifies single field update.",
        }
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestNode)
        assert node.test_name == "test_single_field"
        assert node.test_module == "tests.test_update"
        assert node.method == "automated"

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        data = {
            "type": "TestNode",
            "qualified_name": "tests::test_update::test_single_field",
            "kind": "test",
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid("tests::test_update::test_single_field")
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify test_node_full.json deserializes correctly."""
        with open(DATA_DIR / "test_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestNode)
        assert node.test_name == data["test_name"]
        assert node.test_module == data["test_module"]
        assert node.method == data["method"]
        assert node.qualified_name == data["qualified_name"]
        assert node.tags == data["tags"]


class TestTestNodeRegistry:
    """Test that TestNode is registered in CodeGraphNode._registry."""

    def test_test_node_in_registry(self):
        assert "TestNode" in CodeGraphNode._registry

    def test_test_node_registry_class(self):
        assert CodeGraphNode._registry["TestNode"] is TestNode