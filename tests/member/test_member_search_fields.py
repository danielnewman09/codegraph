"""Unit tests for doc_embedding field and HAS_IMPLEMENTATION on member nodes."""

import json
from pathlib import Path

from codegraph.models.member import MethodNode, FunctionNode, AttributeNode, DefineNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestMemberEmbeddingFields:
    """Test embedding ArrayProperty fields on member nodes."""

    def test_method_doc_embedding_default_empty(self):
        m = MethodNode(kind="method")
        assert m.doc_embedding == []

    def test_method_doc_embedding_stored(self):
        m = MethodNode(kind="method", doc_embedding=[0.1, 0.2, 0.3])
        assert m.doc_embedding == [0.1, 0.2, 0.3]

    def test_function_doc_embedding_default(self):
        f = FunctionNode(kind="function")
        assert f.doc_embedding == []


class TestMemberLlmFields:
    """Test that _llm_fields exclude implementation and embeddings."""

    def test_method_llm_fields_exclude_implementation(self):
        """MethodNode no longer includes implementation in _llm_fields."""
        assert "implementation" not in MethodNode._llm_fields

    def test_function_llm_fields_exclude_implementation(self):
        """FunctionNode no longer includes implementation in _llm_fields."""
        assert "implementation" not in FunctionNode._llm_fields

    def test_method_llm_fields_exclude_embeddings(self):
        assert "doc_embedding" not in MethodNode._llm_fields
        assert "impl_embedding" not in MethodNode._llm_fields

    def test_function_llm_fields_exclude_embeddings(self):
        assert "doc_embedding" not in FunctionNode._llm_fields
        assert "impl_embedding" not in FunctionNode._llm_fields

    def test_method_serialize_excludes_embeddings(self):
        m = MethodNode(
            kind="method",
            name="draw",
            doc_embedding=[0.1, 0.2, 0.3],
        )
        serialized = m.serialize()
        assert "doc_embedding" not in serialized
        assert "impl_embedding" not in serialized

    def test_attribute_llm_fields_exclude_implementation(self):
        """AttributeNode does not include implementation in _llm_fields."""
        assert "implementation" not in AttributeNode._llm_fields

    def test_define_llm_fields_exclude_implementation(self):
        """DefineNode does not include implementation in _llm_fields."""
        assert "implementation" not in DefineNode._llm_fields


class TestMemberImplementationRef:
    """Test that member nodes have the HAS_IMPLEMENTATION relationship."""

    def test_method_has_implementation_ref(self):
        """MethodNode has an implementation_ref relationship manager."""
        m = MethodNode(kind="method")
        assert hasattr(m, "implementation_ref")

    def test_function_has_implementation_ref(self):
        """FunctionNode has an implementation_ref relationship manager."""
        f = FunctionNode(kind="function")
        assert hasattr(f, "implementation_ref")

    def test_attribute_has_implementation_ref(self):
        """AttributeNode has an implementation_ref relationship manager."""
        a = AttributeNode(kind="attribute")
        assert hasattr(a, "implementation_ref")

    def test_define_has_implementation_ref(self):
        """DefineNode has an implementation_ref relationship manager."""
        d = DefineNode(kind="define")
        assert hasattr(d, "implementation_ref")


class TestMemberDeserialization:
    """Test that deserialize handles current fields correctly."""

    def test_method_fixture_roundtrip(self):
        """Verify method_node_full.json deserializes correctly."""
        with open(DATA_DIR / "method_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, MethodNode)
        # implementation is no longer on MethodNode
        assert not hasattr(node, "implementation") or getattr(node, "implementation", "") == ""
        # doc_embedding should roundtrip
        assert node.doc_embedding == data.get("doc_embedding", [])
        # impl_embedding is no longer on MethodNode
        assert not hasattr(node, "impl_embedding") or getattr(node, "impl_embedding", []) == []

    def test_function_fixture_roundtrip(self):
        """Verify function_node_full.json deserializes correctly."""
        with open(DATA_DIR / "function_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, FunctionNode)
        assert node.doc_embedding == data.get("doc_embedding", [])