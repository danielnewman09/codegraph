"""Test AttributeNode, MethodNode, EnumValueNode design models."""
import pytest
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode


class TestAttributeNode:
    def test_serializes_type_name_for_llm(self):
        attr = AttributeNode(
            name="count",
            qualified_name="calc::Calculator::count",
            type_signature="int",
        )
        dumped = attr.model_dump(tags={"llm"})
        assert "type_name" in dumped
        assert dumped["type_name"] == "int"
        assert "type_signature" not in dumped

    def test_serializes_type_signature_for_neo4j(self):
        attr = AttributeNode(
            name="count",
            qualified_name="calc::Calculator::count",
            type_signature="int",
        )
        dumped = attr.model_dump(tags={"neo4j"})
        assert "type_signature" in dumped
        assert dumped["type_signature"] == "int"
        assert "type_name" not in dumped

    def test_defaults(self):
        attr = AttributeNode()
        assert attr.name == ""
        assert attr.qualified_name == ""
        assert attr.kind == "attribute"
        assert attr.visibility == ""
        assert attr.type_signature == ""
        assert attr.owner == ""


class TestMethodNode:
    def test_serializes_return_type_for_llm(self):
        method = MethodNode(
            name="add",
            qualified_name="calc::Calculator::add",
            type_signature="int",
            argsstring="(int a, int b)",
        )
        dumped = method.model_dump(tags={"llm"})
        assert dumped["return_type"] == "int"
        assert "type_signature" not in dumped

    def test_defaults(self):
        method = MethodNode()
        assert method.kind == "method"
        assert method.argsstring == ""


class TestEnumValueNode:
    def test_defaults(self):
        ev = EnumValueNode()
        assert ev.kind == "enum_value"
