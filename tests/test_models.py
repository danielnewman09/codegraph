"""Tests for neomodel node models."""
import pytest
from neomodel import DoesNotExist, RequiredProperty, UniqueProperty

from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode


class TestCompoundNode:
    def test_create_and_save(self):
        c = CompoundNode(qualified_name="calc::Calculator", kind="class")
        c.save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.qualified_name == "calc::Calculator"
        assert retrieved.kind == "class"
        assert retrieved.name == ""
        assert retrieved.layer == "design"
        assert retrieved.is_final is False

    def test_unique_id_enforced(self):
        c1 = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        c2 = CompoundNode(qualified_name="calc::Calc", kind="struct")
        with pytest.raises(UniqueProperty):
            c2.save()

    def test_kind_required(self):
        with pytest.raises(RequiredProperty):
            CompoundNode().save()

    def test_full_creation(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="classcalc_1_1Calculator",
            brief_description="A simple calculator",
            detailed_description="Performs arithmetic.",
            base_classes=["BaseCalc"],
            file_path="/src/calculator.h",
            line_number=42,
            source="msd",
            is_final=True,
            is_abstract=False,
        ).save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.name == "Calculator"
        assert retrieved.brief_description == "A simple calculator"
        assert retrieved.base_classes == ["BaseCalc"]
        assert retrieved.file_path == "/src/calculator.h"
        assert retrieved.line_number == 42
        assert retrieved.is_final is True

    def test_base_classes_default(self):
        c = CompoundNode(qualified_name="calc::Foo", kind="class").save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Foo")
        assert retrieved.base_classes == []


class TestMemberNode:
    def test_create_and_save(self):
        m = MemberNode(qualified_name="calc::Calculator::add", kind="method")
        m.save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.kind == "method"
        assert retrieved.is_static is False

    def test_kind_required(self):
        with pytest.raises(RequiredProperty):
            MemberNode().save()

    def test_full_creation(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            type_signature="int",
            argsstring="(int a, int b)",
            protection="public",
            is_const=True,
            is_virtual=False,
            is_inline=True,
        ).save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.type_signature == "int"
        assert retrieved.argsstring == "(int a, int b)"
        assert retrieved.protection == "public"
        assert retrieved.is_const is True
        assert retrieved.is_inline is True

    def test_all_boolean_flags_default_false(self):
        m = MemberNode(qualified_name="calc::Foo::bar", kind="method").save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Foo::bar")
        assert retrieved.is_static is False
        assert retrieved.is_const is False
        assert retrieved.is_constexpr is False
        assert retrieved.is_virtual is False
        assert retrieved.is_inline is False
        assert retrieved.is_explicit is False


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
