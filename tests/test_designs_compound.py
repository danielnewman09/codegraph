"""Test compound design models — ClassNode, InterfaceNode, EnumNode."""
import pytest
from codegraph.designs.compound import (
    DiagramNode, ClassNode, InterfaceNode, EnumNode,
)
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode


class TestDiagramNode:
    def test_defaults(self):
        node = DiagramNode()
        assert node.name == ""
        assert node.qualified_name == ""
        assert node.kind == ""
        assert node.description == ""
        assert node.layer == "design"
        assert node.file_path == ""

    def test_llm_dump_excludes_neo4j_fields(self):
        node = DiagramNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            file_path="/src/calculator.h",
            line_number=42,
            is_static=False,
            is_final=True,
        )
        dumped = node.model_dump(tags={"llm"})
        assert "name" in dumped
        assert "qualified_name" in dumped
        assert "kind" in dumped
        assert "file_path" not in dumped
        assert "line_number" not in dumped
        assert "is_static" not in dumped
        assert "is_final" not in dumped


class TestClassNode:
    def test_defaults(self):
        cls = ClassNode()
        assert cls.kind == "class"
        assert cls.attributes == []
        assert cls.methods == []
        assert cls.inherits_from == []

    def test_serializes_nested_members_with_llm_tags(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            attributes=[
                AttributeNode(
                    name="count", qualified_name="calc::Calculator::count",
                    type_signature="int", owner="calc::Calculator",
                )
            ],
            methods=[
                MethodNode(
                    name="add", qualified_name="calc::Calculator::add",
                    type_signature="int", argsstring="(int a, int b)",
                    owner="calc::Calculator",
                )
            ],
        )
        dumped = cls.model_dump(tags={"llm"})
        assert dumped["name"] == "Calculator"
        assert len(dumped["attributes"]) == 1
        assert dumped["attributes"][0]["type_name"] == "int"
        assert "owner" not in dumped["attributes"][0]
        assert len(dumped["methods"]) == 1
        assert dumped["methods"][0]["return_type"] == "int"
        assert "owner" not in dumped["methods"][0]
