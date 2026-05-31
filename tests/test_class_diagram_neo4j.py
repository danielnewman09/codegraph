"""Tests for ClassDiagram dataclass container."""
import pytest

from codegraph.diagram import ClassDiagram
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode


class TestClassDiagram:
    def test_init_with_empty_lists(self):
        diagram = ClassDiagram()
        assert diagram.module_names == []
        assert diagram.classes == []
        assert diagram.interfaces == []
        assert diagram.enums == []

    def test_init_populates_entity_index(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class", name="Calc")
        iface = InterfaceNode(qualified_name="io::IPrintable", kind="interface", name="IP")
        enum = EnumNode(qualified_name="color::Color", kind="enum", name="Color")

        diagram = ClassDiagram(
            classes=[c], interfaces=[iface], enums=[enum],
        )
        assert diagram.get_entity("calc::Calculator") is c
        assert diagram.get_entity("io::IPrintable") is iface
        assert diagram.get_entity("color::Color") is enum
        assert diagram.get_entity("nonexistent") is None

    def test_to_summary_counts(self):
        c1 = ClassNode(qualified_name="a::A", kind="class")
        c2 = ClassNode(qualified_name="b::B", kind="class")
        iface = InterfaceNode(qualified_name="c::C", kind="interface")
        enum = EnumNode(qualified_name="d::D", kind="enum")

        diagram = ClassDiagram(
            classes=[c1, c2], interfaces=[iface], enums=[enum],
        )
        summary = diagram.to_summary()
        assert summary["classes"] == 2
        assert summary["interfaces"] == 1
        assert summary["enums"] == 1

    def test_to_class_lookup(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class", name="Calculator")
        diagram = ClassDiagram(classes=[c])
        lookup = diagram.to_class_lookup()
        assert lookup == {"Calculator": "calc::Calculator"}

    def test_classes_in_module(self):
        c1 = ClassNode(qualified_name="calc::Calc", kind="class", module="calc")
        c2 = ClassNode(qualified_name="calc::Adder", kind="class", module="calc")
        c3 = ClassNode(qualified_name="io::Printer", kind="class", module="io")

        diagram = ClassDiagram(classes=[c1, c2, c3])
        calc_classes = diagram.classes_in_module("calc")
        assert len(calc_classes) == 2
        assert c3 not in calc_classes

    def test_from_layer_returns_classdiagram(self):
        """Smoke test: from_layer returns a ClassDiagram."""
        diagram = ClassDiagram.from_layer("design")
        assert isinstance(diagram, ClassDiagram)
        assert hasattr(diagram, "classes")
        assert hasattr(diagram, "interfaces")
        assert hasattr(diagram, "enums")

    def test_from_layer_derives_module_names(self):
        """module_names is derived from qualified names in from_layer()."""
        ClassNode(qualified_name="calc::Calculator", kind="class", name="Calculator").save()
        InterfaceNode(qualified_name="io::IPrintable", kind="interface", name="IPrintable").save()

        diagram = ClassDiagram.from_layer("design")
        assert "calc" in diagram.module_names
        assert "io" in diagram.module_names
