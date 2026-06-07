"""Unit tests for doc_embedding field and HAS_IMPLEMENTATION on compound nodes."""

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode
from codegraph.models.tags import CodeGraphNode


class TestCompoundEmbeddingField:
    """Test doc_embedding on compound nodes."""

    def test_class_doc_embedding_default_empty(self):
        c = ClassNode(kind="class")
        assert c.doc_embedding == []

    def test_class_doc_embedding_stored(self):
        c = ClassNode(kind="class", doc_embedding=[0.1, 0.2, 0.3])
        assert c.doc_embedding == [0.1, 0.2, 0.3]

    def test_interface_doc_embedding_default_empty(self):
        i = InterfaceNode(kind="interface")
        assert i.doc_embedding == []


class TestCompoundLlmFields:
    """Test that compound _llm_fields do NOT include implementation or embeddings."""

    def test_class_llm_fields_exclude_embeddings(self):
        assert "doc_embedding" not in ClassNode._llm_fields
        assert "impl_embedding" not in ClassNode._llm_fields

    def test_class_llm_fields_exclude_implementation(self):
        assert "implementation" not in ClassNode._llm_fields

    def test_interface_llm_fields_exclude_implementation(self):
        assert "implementation" not in InterfaceNode._llm_fields


class TestCompoundImplementationRef:
    """Test that compound nodes have the HAS_IMPLEMENTATION relationship."""

    def test_class_has_implementation_ref(self):
        """ClassNode has an implementation_ref relationship manager."""
        c = ClassNode(kind="class")
        assert hasattr(c, "implementation_ref")

    def test_interface_has_implementation_ref(self):
        """InterfaceNode has an implementation_ref relationship manager."""
        i = InterfaceNode(kind="interface")
        assert hasattr(i, "implementation_ref")

    def test_enum_has_implementation_ref(self):
        """EnumNode has an implementation_ref relationship manager."""
        e = EnumNode(kind="enum")
        assert hasattr(e, "implementation_ref")


class TestCompoundDeserialization:
    """Test that from_json/deserialize handles the current fields correctly."""

    def test_class_deserialize_with_doc_embedding(self):
        data = {
            "type": "ClassNode",
            "qualified_name": "test::Foo",
            "name": "Foo",
            "kind": "class",
            "doc_embedding": [0.1, 0.2, 0.3],
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, ClassNode)
        assert node.doc_embedding == [0.1, 0.2, 0.3]