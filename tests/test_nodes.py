import pytest
from pydantic import ValidationError

from codegraph.nodes import FileNode


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
