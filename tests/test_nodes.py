import pytest
from pydantic import ValidationError

from codegraph.nodes import CompoundNode, FileNode, NamespaceNode


class TestFileNode:
    def test_minimal_creation(self):
        f = FileNode(refid="file_abc123")
        assert f.refid == "file_abc123"
        assert f.name == ""
        assert f.path == ""
        assert f.language == ""
        assert f.source == ""

    def test_full_creation(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        )
        assert f.name == "main.cpp"
        assert f.path == "/src/main.cpp"
        assert f.language == "C++"
        assert f.source == "msd"

    def test_refid_is_required(self):
        with pytest.raises(ValidationError):
            FileNode()

    def test_extra_fields_ignored(self):
        f = FileNode(refid="file_abc123", extra_field="ignored")
        assert f.refid == "file_abc123"
        assert not hasattr(f, "extra_field")

    def test_model_dump_roundtrip(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        )
        data = f.model_dump()
        f2 = FileNode.model_validate(data)
        assert f == f2

    def test_default_values_in_dump(self):
        f = FileNode(refid="file_abc123")
        data = f.model_dump()
        assert data["name"] == ""
        assert data["path"] == ""
        assert data["language"] == ""
        assert data["source"] == ""


class TestNamespaceNode:
    def test_minimal_creation(self):
        n = NamespaceNode(qualified_name="std")
        assert n.qualified_name == "std"
        assert n.name == ""
        assert n.kind == "namespace"
        assert n.layer == "design"
        assert n.refid == ""
        assert n.description == ""
        assert n.source == ""

    def test_full_creation(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            refid="namespacestd_1_1chrono",
            description="C++ chrono library",
            source="stdlib",
        )
        assert n.qualified_name == "std::chrono"
        assert n.name == "chrono"
        assert n.kind == "namespace"
        assert n.layer == "dependency"
        assert n.refid == "namespacestd_1_1chrono"
        assert n.description == "C++ chrono library"
        assert n.source == "stdlib"

    def test_qualified_name_required(self):
        with pytest.raises(ValidationError):
            NamespaceNode()

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            NamespaceNode(qualified_name="std", kind="invalid_kind")

    def test_invalid_layer_rejected(self):
        with pytest.raises(ValidationError):
            NamespaceNode(qualified_name="std", layer="unknown_layer")

    def test_allowed_kinds(self):
        for kind in ["namespace", "package", "module"]:
            n = NamespaceNode(qualified_name="std", kind=kind)
            assert n.kind == kind

    def test_allowed_layers(self):
        for layer in ["design", "as-built", "dependency"]:
            n = NamespaceNode(qualified_name="std", layer=layer)
            assert n.layer == layer

    def test_model_dump_roundtrip(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            refid="ref123",
            description="desc",
            source="stdlib",
        )
        data = n.model_dump()
        n2 = NamespaceNode.model_validate(data)
        assert n == n2


class TestCompoundNode:
    def test_minimal_creation(self):
        c = CompoundNode(qualified_name="calc::Calculator", kind="class")
        assert c.qualified_name == "calc::Calculator"
        assert c.name == ""
        assert c.kind == "class"
        assert c.layer == "design"
        assert c.refid == ""
        assert c.description == ""
        assert c.brief_description == ""
        assert c.detailed_description == ""
        assert c.base_classes == []
        assert c.file_path == ""
        assert c.line_number is None
        assert c.source == ""
        assert c.protection == ""
        assert c.is_final is False
        assert c.is_abstract is False

    def test_full_creation(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="classcalc_1_1Calculator",
            description="A simple calculator",
            brief_description="A simple calculator class",
            detailed_description="Performs arithmetic operations with precision tracking.",
            base_classes=["BaseCalc", "IPrintable"],
            file_path="/src/calculator.h",
            line_number=42,
            source="msd",
            protection="public",
            is_final=True,
            is_abstract=False,
        )
        assert c.name == "Calculator"
        assert c.layer == "as-built"
        assert c.refid == "classcalc_1_1Calculator"
        assert c.description == "A simple calculator"
        assert c.brief_description == "A simple calculator class"
        assert c.detailed_description == "Performs arithmetic operations with precision tracking."
        assert c.base_classes == ["BaseCalc", "IPrintable"]
        assert c.file_path == "/src/calculator.h"
        assert c.line_number == 42
        assert c.source == "msd"
        assert c.protection == "public"
        assert c.is_final is True
        assert c.is_abstract is False

    def test_qualified_name_required(self):
        with pytest.raises(ValidationError):
            CompoundNode(kind="class")

    def test_kind_required(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator")

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator", kind="not_a_kind")

    def test_invalid_layer_rejected(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator", kind="class", layer="bogus")

    def test_allowed_kinds(self):
        for kind in ["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]:
            c = CompoundNode(qualified_name="calc::Foo", kind=kind)
            assert c.kind == kind

    def test_base_classes_default_empty(self):
        c = CompoundNode(qualified_name="calc::Foo", kind="class")
        assert c.base_classes == []

    def test_model_dump_roundtrip(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="ref123",
            description="desc",
            brief_description="brief",
            detailed_description="detailed",
            base_classes=["Base"],
            file_path="/src/calc.h",
            line_number=42,
            source="msd",
            protection="public",
            is_final=False,
            is_abstract=True,
        )
        data = c.model_dump()
        c2 = CompoundNode.model_validate(data)
        assert c == c2
