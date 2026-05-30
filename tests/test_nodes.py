import pytest
from pydantic import ValidationError

from codegraph.nodes import FileNode, NamespaceNode


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
