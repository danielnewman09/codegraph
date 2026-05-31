"""Tests for atomized neomodel models."""
import pytest
from neomodel import RequiredProperty, UniqueProperty

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode


class TestCompoundMixin:
    """Common behavior shared by all compound types."""

    def test_common_fields_present_on_class(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class")
        c.save()
        retrieved = ClassNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.name == ""
        assert retrieved.layer == "design"
        assert retrieved.brief_description == ""
        assert retrieved.detailed_description == ""
        assert retrieved.file_path == ""
        assert retrieved.line_number is None
        assert retrieved.source == ""

    def test_qualified_name_is_unique_across_kinds(self):
        ClassNode(qualified_name="calc::Foo", kind="class").save()
        with pytest.raises(UniqueProperty):
            InterfaceNode(qualified_name="calc::Foo", kind="interface").save()

    def test_kind_defaults_to_class(self):
        """ClassNode.kind defaults to 'class' — can construct without specifying."""
        c = ClassNode(qualified_name="calc::Auto").save()
        assert c.kind == "class"

    def test_serialize_filters_to_llm_fields(self):
        c = ClassNode(
            qualified_name="calc::Calc", name="Calc", kind="class",
            brief_description="A calculator", file_path="/src/calc.h",
            line_number=42, source="msd",
        )
        result = c.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "kind" in result
        assert "brief_description" in result
        assert "file_path" not in result
        assert "line_number" not in result
        assert "source" not in result

    def test_deserialize_ignores_extra_keys(self):
        data = {
            "qualified_name": "calc::Calc",
            "name": "Calc",
            "kind": "class",
            "layer": "design",
            "alien_field": "should be dropped",
        }
        node = ClassNode.deserialize(data)
        assert node.qualified_name == "calc::Calc"
        assert node.name == "Calc"
        assert node.kind == "class"
        assert not hasattr(node, "alien_field")


class TestNamespaceNode:
    def test_create_and_save(self):
        n = NamespaceNode(qualified_name="std::chrono")
        n.save()
        retrieved = NamespaceNode.nodes.get(qualified_name="std::chrono")
        assert retrieved.kind == "namespace"
        assert retrieved.layer == "design"

    def test_full_creation(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            description="C++ chrono library",
            source="stdlib",
        ).save()
        retrieved = NamespaceNode.nodes.get(qualified_name="std::chrono")
        assert retrieved.name == "chrono"
        assert retrieved.description == "C++ chrono library"


class TestFileNode:
    def test_create_and_save(self):
        f = FileNode(refid="file_abc123")
        f.save()
        retrieved = FileNode.nodes.get(refid="file_abc123")
        assert retrieved.name == ""
        assert retrieved.path == ""

    def test_full_creation(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        ).save()
        retrieved = FileNode.nodes.get(refid="file_abc123")
        assert retrieved.name == "main.cpp"
        assert retrieved.path == "/src/main.cpp"


class TestInterfaceNode:
    def test_create_and_save(self):
        iface = InterfaceNode(
            qualified_name="io::IPrintable",
            name="IPrintable",
            kind="interface",
            module="io",
            brief_description="Printable contract",
            is_abstract=True,
        )
        iface.save()
        retrieved = InterfaceNode.nodes.get(qualified_name="io::IPrintable")
        assert retrieved.kind == "interface"
        assert retrieved.name == "IPrintable"
        assert retrieved.module == "io"
        assert retrieved.is_abstract is True

    def test_has_no_attributes_relationship(self):
        """InterfaceNode should NOT have an 'attributes' descriptor."""
        iface = InterfaceNode(qualified_name="io::IFoo", kind="interface").save()
        assert not hasattr(iface, "attributes")

    def test_has_methods_relationship(self):
        """InterfaceNode has a 'methods' descriptor for MethodNodes."""
        iface = InterfaceNode(qualified_name="io::IBar", kind="interface").save()
        assert hasattr(iface, "methods")

    def test_default_module_empty(self):
        iface = InterfaceNode(qualified_name="io::IBaz", kind="interface").save()
        assert iface.module == ""

    def test_serialize_only_llm_fields(self):
        iface = InterfaceNode(
            qualified_name="io::IPrintable", name="IPrintable", kind="interface",
            brief_description="Printable", module="io", file_path="/src/io.h",
            line_number=10,
        )
        result = iface.serialize()
        assert result == {
            "qualified_name": "io::IPrintable",
            "name": "IPrintable",
            "kind": "interface",
            "brief_description": "Printable",
        }


class TestEnumNode:
    def test_create_and_save(self):
        enum = EnumNode(
            qualified_name="color::Color", name="Color", kind="enum",
            module="color", brief_description="RGB color enum",
        )
        enum.save()
        retrieved = EnumNode.nodes.get(qualified_name="color::Color")
        assert retrieved.kind == "enum"
        assert retrieved.name == "Color"
        assert retrieved.module == "color"

    def test_values_relationship(self):
        enum = EnumNode(qualified_name="color::RGB", kind="enum").save()
        assert hasattr(enum, "values")

    def test_no_methods_attributes_on_enum(self):
        enum = EnumNode(qualified_name="color::X", kind="enum").save()
        assert not hasattr(enum, "methods")
        assert not hasattr(enum, "attributes")

    def test_serialize_llm_fields(self):
        enum = EnumNode(
            qualified_name="color::Color", name="Color", kind="enum",
            brief_description="RGB", module="color", file_path="/src/color.h",
        )
        result = enum.serialize()
        assert "qualified_name" in result
        assert "brief_description" in result
        assert "file_path" not in result
        assert "module" not in result


class TestParameterNode:
    def test_create_and_save(self):
        p = ParameterNode(position=0, name="x")
        p.save()
        results = ParameterNode.nodes.filter(position=0, name="x").all()
        assert len(results) == 1
        assert results[0].type == ""

    def test_full_creation(self):
        p = ParameterNode(
            position=1,
            name="epsilon",
            type="double",
            default_value="1e-6",
            member_refid="method_ref_123",
        ).save()
        results = ParameterNode.nodes.filter(position=1, name="epsilon").all()
        assert len(results) == 1
        assert results[0].type == "double"
        assert results[0].default_value == "1e-6"
        assert results[0].member_refid == "method_ref_123"


class TestUnionNode:
    def test_create_and_save(self):
        u = UnionNode(qualified_name="data::Variant", name="Variant",
                       kind="union", module="data")
        u.save()
        retrieved = UnionNode.nodes.get(qualified_name="data::Variant")
        assert retrieved.kind == "union"
        assert retrieved.module == "data"

    def test_serialize_only_llm_fields(self):
        u = UnionNode(qualified_name="data::V", name="V", kind="union",
                       brief_description="A variant", module="data",
                       file_path="/src/data.h")
        result = u.serialize()
        assert "qualified_name" in result
        assert "brief_description" in result
        assert "file_path" not in result


class TestModuleNode:
    def test_create_and_save(self):
        m = ModuleNode(qualified_name="calc", name="calc", kind="module")
        m.save()
        retrieved = ModuleNode.nodes.get(qualified_name="calc")
        assert retrieved.kind == "module"
        assert retrieved.name == "calc"


class TestMethodNode:
    def test_create_and_save(self):
        m = MethodNode(qualified_name="calc::Calculator::add", kind="method")
        m.save()
        retrieved = MethodNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.kind == "method"
        assert retrieved.name == ""
        assert retrieved.is_static is False
        assert retrieved.is_virtual is False
        assert retrieved.is_const is False

    def test_full_creation(self):
        m = MethodNode(
            qualified_name="calc::Calculator::add", name="add", kind="method",
            type_signature="int", argsstring="(int a, int b)",
            protection="public", is_const=True, is_virtual=False,
            is_inline=True, brief_description="Adds two numbers",
            layer="as-built",
        ).save()
        retrieved = MethodNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.type_signature == "int"
        assert retrieved.argsstring == "(int a, int b)"
        assert retrieved.protection == "public"
        assert retrieved.is_const is True
        assert retrieved.is_inline is True
        assert retrieved.brief_description == "Adds two numbers"

    def test_serialize_llm_fields(self):
        m = MethodNode(
            qualified_name="calc::Calc::add", name="add", kind="method",
            type_signature="int", argsstring="(int a, int b)",
            brief_description="Adds", protection="public", file_path="/src/c.h",
        )
        result = m.serialize()
        assert "qualified_name" in result
        assert "type_signature" in result
        assert "argsstring" in result
        assert "brief_description" in result
        assert "protection" not in result
        assert "file_path" not in result

    def test_kind_defaults_to_method(self):
        """MethodNode.kind defaults to 'method' — can construct without specifying."""
        m = MethodNode(qualified_name="calc::Default::run").save()
        assert m.kind == "method"


class TestAttributeNode:
    def test_create_and_save(self):
        a = AttributeNode(qualified_name="calc::Calculator::count", kind="attribute")
        a.save()
        retrieved = AttributeNode.nodes.get(qualified_name="calc::Calculator::count")
        assert retrieved.kind == "attribute"
        assert retrieved.is_static is False

    def test_full_creation(self):
        a = AttributeNode(
            qualified_name="calc::Calculator::count", name="count",
            kind="attribute", type_signature="int", protection="private",
            is_static=True, is_const=False,
        ).save()
        retrieved = AttributeNode.nodes.get(qualified_name="calc::Calculator::count")
        assert retrieved.type_signature == "int"
        assert retrieved.protection == "private"
        assert retrieved.is_static is True

    def test_serialize_llm_fields(self):
        a = AttributeNode(
            qualified_name="calc::Calc::count", name="count", kind="attribute",
            type_signature="int", brief_description="Counter", protection="private",
        )
        result = a.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "type_signature" in result
        assert "protection" not in result
