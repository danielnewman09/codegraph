"""Tests for CodeGraphNode.to_dict() and from_dict()."""

import pytest

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode, FunctionNode
from codegraph.models.file import FileNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.parameter import ParameterNode
from codegraph.models.implementation import ImplementationNode
from codegraph.models.tags import CodeGraphNode


class TestToDictAll:
    """Tests for CodeGraphNode.to_dict(fields='all')."""

    def test_includes_all_properties(self):
        node = ClassNode(
            qualified_name="ns::Widget",
            name="Widget",
            kind="class",
            layer="design",
            visibility="public",
            brief_description="A widget",
            detailed_description="A detailed description",
            component_id=42,
            source_type="doxygen",
            file_path="/src/widget.h",
            line_number=10,
            definition="class Widget",
            module="ns",
            source="myproject",
        )
        result = node.to_dict(fields="all")

        # All defined properties should be present
        assert result["type"] == "ClassNode"
        assert result["qualified_name"] == "ns::Widget"
        assert result["name"] == "Widget"
        assert result["kind"] == "class"
        assert result["layer"] == "design"
        assert result["visibility"] == "public"
        assert result["brief_description"] == "A widget"
        assert result["detailed_description"] == "A detailed description"
        assert result["component_id"] == 42
        assert result["source_type"] == "doxygen"
        assert result["file_path"] == "/src/widget.h"
        assert result["line_number"] == 10
        assert result["definition"] == "class Widget"
        assert result["module"] == "ns"
        assert result["source"] == "myproject"

    def test_includes_type_discriminator(self):
        node = ClassNode(name="X", kind="class")
        result = node.to_dict(fields="all")
        assert result["type"] == "ClassNode"

    def test_includes_uid_prop_for_compound(self):
        node = ClassNode(name="X", kind="class", qualified_name="ns::X")
        result = node.to_dict(fields="all")
        # qualified_name is a UniqueIdProperty; it should be in the result
        assert "qualified_name" in result

    def test_includes_uid_prop_for_file_node(self):
        node = FileNode(name="test.h", path="/src/test.h", refid="file-test-h")
        result = node.to_dict(fields="all")
        # refid is a UniqueIdProperty for FileNode
        assert "refid" in result
        assert result["refid"] == "file-test-h"

    def test_method_node_includes_all_fields(self):
        node = MethodNode(
            qualified_name="ns::Widget::draw",
            name="draw",
            kind="method",
            type_signature="void",
            argsstring="()",
            visibility="public",
            is_static=False,
            is_const=True,
            is_constexpr=False,
            is_virtual=False,
            is_inline=False,
            layer="as-built",
            file_path="/src/widget.cpp",
            line_number=42,
            source="myproject",
        )
        result = node.to_dict(fields="all")
        assert result["type"] == "MethodNode"
        assert result["qualified_name"] == "ns::Widget::draw"
        assert result["type_signature"] == "void"
        assert result["argsstring"] == "()"
        assert result["is_const"] is True
        assert result["layer"] == "as-built"
        assert result["file_path"] == "/src/widget.cpp"
        assert result["line_number"] == 42

    def test_namespace_node_includes_all_fields(self):
        node = NamespaceNode(
            qualified_name="ns",
            name="ns",
            kind="namespace",
            description="A namespace",
            source="myproject",
        )
        result = node.to_dict(fields="all")
        assert result["type"] == "NamespaceNode"
        assert result["description"] == "A namespace"
        assert result["source"] == "myproject"

    def test_implementation_node_includes_all_fields(self):
        node = ImplementationNode(
            qualified_name="ns::Widget::draw",
            kind="implementation",
            implementation="void Widget::draw() { }",
        )
        result = node.to_dict(fields="all")
        assert result["type"] == "ImplementationNode"
        assert result["kind"] == "implementation"
        assert result["implementation"] == "void Widget::draw() { }"

    def test_parameter_node_no_uid_prop(self):
        node = ParameterNode(name="argc", position=0, type="int")
        result = node.to_dict(fields="all")
        assert result["type"] == "ParameterNode"
        assert result["name"] == "argc"
        assert result["position"] == 0
        assert result["type"] == "ParameterNode"  # type key overwrites param type
        # ParameterNode has no UniqueIdProperty; name is the fallback

    def test_does_not_include_edges(self):
        node = ClassNode(name="X", kind="class")
        result = node.to_dict(fields="all")
        assert "edges" not in result


class TestToDictLlm:
    """Tests for CodeGraphNode.to_dict(fields='llm')."""

    def test_includes_only_llm_fields_plus_type(self):
        node = ClassNode(
            qualified_name="ns::Widget",
            name="Widget",
            kind="class",
            visibility="public",
            brief_description="A widget",
            base_classes=[],
            layer="design",
            component_id=99,
            file_path="/src/widget.h",
        )
        result = node.to_dict(fields="llm")
        # _llm_fields for ClassNode: qualified_name, name, kind, brief_description, base_classes, visibility
        assert result["type"] == "ClassNode"
        assert "qualified_name" in result
        assert "name" in result
        assert "kind" in result
        assert "brief_description" in result
        assert "base_classes" in result
        assert "visibility" in result
        # Non-LLM fields should NOT be present
        assert "layer" not in result
        assert "component_id" not in result
        assert "file_path" not in result
        assert "detailed_description" not in result

    def test_includes_uid_prop_even_when_not_in_llm_fields(self):
        node = FileNode(name="test.h", path="/src/test.h", refid="file-test-h")
        result = node.to_dict(fields="llm")
        # refid is not in FileNode._llm_fields but should still be included
        # because it's the UniqueIdProperty
        assert "refid" in result
        assert result["refid"] == "file-test-h"

    def test_method_node_llm_fields(self):
        node = MethodNode(
            qualified_name="ns::Widget::draw",
            name="draw",
            kind="method",
            type_signature="void",
            argsstring="()",
            visibility="public",
            layer="design",
            file_path="/src/widget.cpp",
        )
        result = node.to_dict(fields="llm")
        # _llm_fields for MethodNode: qualified_name, name, kind, brief_description, type_signature, argsstring, visibility
        assert "qualified_name" in result
        assert "name" in result
        assert "kind" in result
        assert "type_signature" in result
        assert "argsstring" in result
        assert "visibility" in result
        # Non-LLM fields should not be present
        assert "layer" not in result
        assert "file_path" not in result
        assert "is_const" not in result

    def test_llm_includes_type_discriminator(self):
        node = ClassNode(name="X", kind="class")
        result = node.to_dict(fields="llm")
        assert result["type"] == "ClassNode"


class TestFromDict:
    """Tests for CodeGraphNode.from_dict()."""

    def test_creates_class_node(self):
        data = {
            "type": "ClassNode",
            "qualified_name": "ns::Widget",
            "name": "Widget",
            "kind": "class",
            "visibility": "public",
        }
        node = CodeGraphNode.from_dict(data)
        assert isinstance(node, ClassNode)
        assert node.qualified_name == "ns::Widget"
        assert node.name == "Widget"
        assert node.kind == "class"

    def test_creates_method_node(self):
        data = {
            "type": "MethodNode",
            "qualified_name": "ns::Widget::draw",
            "name": "draw",
            "kind": "method",
            "type_signature": "void",
        }
        node = CodeGraphNode.from_dict(data)
        assert isinstance(node, MethodNode)
        assert node.qualified_name == "ns::Widget::draw"
        assert node.type_signature == "void"

    def test_creates_file_node(self):
        data = {
            "type": "FileNode",
            "refid": "file-test-h",
            "name": "test.h",
            "path": "/src/test.h",
        }
        node = CodeGraphNode.from_dict(data)
        assert isinstance(node, FileNode)
        assert node.name == "test.h"

    def test_roundtrip_with_to_dict_all(self):
        original = ClassNode(
            qualified_name="ns::Widget",
            name="Widget",
            kind="class",
            layer="design",
            visibility="public",
            brief_description="A widget",
            detailed_description="A detailed description",
            component_id=42,
            source_type="doxygen",
            file_path="/src/widget.h",
            line_number=10,
            definition="class Widget",
            module="ns",
            source="myproject",
        )
        data = original.to_dict(fields="all")
        restored = CodeGraphNode.from_dict(data)

        assert isinstance(restored, ClassNode)
        assert restored.qualified_name == original.qualified_name
        assert restored.name == original.name
        assert restored.kind == original.kind
        assert restored.layer == original.layer
        assert restored.visibility == original.visibility
        assert restored.brief_description == original.brief_description
        assert restored.detailed_description == original.detailed_description
        assert restored.component_id == original.component_id
        assert restored.source_type == original.source_type
        assert restored.file_path == original.file_path
        assert restored.line_number == original.line_number
        assert restored.definition == original.definition
        assert restored.module == original.module
        assert restored.source == original.source

    def test_roundtrip_with_to_dict_llm(self):
        original = ClassNode(
            qualified_name="ns::Widget",
            name="Widget",
            kind="class",
            visibility="public",
            brief_description="A widget",
            layer="design",
            component_id=42,
        )
        data = original.to_dict(fields="llm")
        restored = CodeGraphNode.from_dict(data)

        assert isinstance(restored, ClassNode)
        # LLM fields should be preserved
        assert restored.qualified_name == original.qualified_name
        assert restored.name == original.name
        assert restored.kind == original.kind
        # Non-LLM fields will have defaults
        assert restored.layer == "design"  # default value

    def test_missing_type_raises_value_error(self):
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.from_dict({"name": "orphan"})

    def test_unknown_type_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.from_dict({"type": "FakeNode", "name": "x"})

    def test_from_json_delegates_to_from_dict(self):
        data = {
            "type": "ClassNode",
            "qualified_name": "ns::Widget",
            "name": "Widget",
            "kind": "class",
        }
        from_json_result = CodeGraphNode.from_json(data)
        from_dict_result = CodeGraphNode.from_dict(data)
        assert type(from_json_result) == type(from_dict_result)
        assert from_json_result.name == from_dict_result.name
        assert from_json_result.kind == from_dict_result.kind