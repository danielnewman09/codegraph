"""Unit tests for doc_embedding field and HAS_IMPLEMENTATION on compound nodes."""

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode
from codegraph.models.tags import CodeGraphNode


class TestCompoundEmbeddingField:
    """Test doc_embedding on compound nodes."""

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_default_empty
    # This test verifies that a ClassNode has an empty doc_embedding by default,
    # ensuring the default state of the embedding field is correct.
    def test_class_doc_embedding_default_empty(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_default_empty::step_0
        # This step sets up the test by initializing the ClassNode fixture, preparing it
        # for the assertion.
        c = ClassNode(kind="class")
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_default_empty::post_0
        # This assertion confirms that the doc_embedding attribute of the ClassNode is
        # an empty list, verifying the expected default state.
        assert c.doc_embedding == []

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_stored
    # Verifies that the doc_embedding field of a ClassNode is correctly stored and
    # retrievable as [0.1, 0.2, 0.3], ensuring that document embeddings for compound
    # classes are persistently saved and accessible for search operations.
    def test_class_doc_embedding_stored(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_stored::step_0
        # Performs the necessary setup, including creating the ClassNode fixture and
        # initializing its doc_embedding field, establishing the state required to then
        # assert the correct embedding value.
        c = ClassNode(kind="class", doc_embedding=[0.1, 0.2, 0.3])
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_class_doc_embedding_stored::post_0
        # Asserts that the ClassNode's doc_embedding attribute equals [0.1, 0.2, 0.3],
        # confirming that the embedding data is stored as expected, which is critical
        # for accurate semantic search over compound class documentation.
        assert c.doc_embedding == [0.1, 0.2, 0.3]

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_interface_doc_embedding_default_empty
    # Verifies that a newly created InterfaceNode has an empty doc_embedding list by
    # default, ensuring consistent initialization behavior for downstream search
    # operations.
    def test_interface_doc_embedding_default_empty(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_interface_doc_embedding_default_empty::step_0
        # Sets up the InterfaceNode fixture, preparing the environment for the
        # subsequent assertion.
        i = InterfaceNode(kind="interface")
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundEmbeddingField.test_interface_doc_embedding_default_empty::post_0
        # Asserts that the doc_embedding field of the InterfaceNode is an empty list,
        # confirming the default behavior of the class.
        assert i.doc_embedding == []


class TestCompoundLlmFields:
    """Test that compound _llm_fields do NOT include implementation or embeddings."""

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_class_llm_fields_exclude_embeddings
    # Verifies that when embeddings are excluded from the search, the compound results
    # do not contain embedding data, ensuring data exclusions are correctly applied.
    def test_class_llm_fields_exclude_embeddings(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_class_llm_fields_exclude_embeddings::post_0
        # Checks that the first returned compound record does not include an embedding
        # field, confirming that the exclusion logic works for individual items.
        assert "doc_embedding" not in ClassNode._llm_fields
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_class_llm_fields_exclude_embeddings::post_1
        # Checks that the second returned compound record also does not include an
        # embedding field, confirming consistent exclusion across multiple results.
        assert "impl_embedding" not in ClassNode._llm_fields

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_class_llm_fields_exclude_implementation
    # Verifies that when specified LLM fields are excluded, those fields do not appear
    # in the search results, ensuring proper filtering.
    def test_class_llm_fields_exclude_implementation(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_class_llm_fields_exclude_implementation::post_0
        # Asserts that a particular value is not present after exclusion is applied,
        # confirming that the exclusion logic correctly hides the specified fields from
        # the output.
        assert "implementation" not in ClassNode._llm_fields

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_interface_llm_fields_exclude_implementation
    # This test verifies that when fields are excluded from the LLM interface, they are
    # not present in the output, ensuring that field exclusion logic correctly filters
    # out specified fields, which is critical for selective data exposure.
    def test_interface_llm_fields_exclude_implementation(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundLlmFields.test_interface_llm_fields_exclude_implementation::post_0
        # This assertion checks that a specific excluded field is not present in the
        # final result, confirming that the field exclusion mechanism works as intended
        # and that the LLM output only contains allowed fields.
        assert "implementation" not in InterfaceNode._llm_fields


class TestCompoundImplementationRef:
    """Test that compound nodes have the HAS_IMPLEMENTATION relationship."""

    def test_class_has_implementation_ref(self):
        """ClassNode has an implementation_ref relationship manager."""
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_class_has_implementation_ref::step_0
        # Sets up the test by preparing the ClassNode instance, ensuring that the
        # fixture 'c' is fully configured and ready for the subsequent verification of
        # the 'implementation_ref' attribute.
        c = ClassNode(kind="class")
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_class_has_implementation_ref::post_0
        # Checks that the attribute 'implementation_ref' exists on the ClassNode
        # instance 'c', which confirms that the model includes the necessary field for
        # establishing relationships with implementation code, thereby supporting core
        # functionality.
        assert hasattr(c, "implementation_ref")

    def test_interface_has_implementation_ref(self):
        """InterfaceNode has an implementation_ref relationship manager."""
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_interface_has_implementation_ref::step_0
        # Sets up the test environment by instantiating or retrieving an InterfaceNode,
        # preparing the object for assertion.
        i = InterfaceNode(kind="interface")
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_interface_has_implementation_ref::post_0
        # Asserts that the 'implementation_ref' attribute exists on the InterfaceNode,
        # ensuring the relationship manager is properly defined.
        assert hasattr(i, "implementation_ref")

    def test_enum_has_implementation_ref(self):
        """EnumNode has an implementation_ref relationship manager."""
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_enum_has_implementation_ref::step_0
        # Sets up the test environment by initializing the EnumNode instance,
        # establishing the test condition required to verify the existence of the
        # implementation_ref attribute.
        e = EnumNode(kind="enum")
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundImplementationRef.test_enum_has_implementation_ref::post_0
        # Confirms that the e fixture has an 'implementation_ref' attribute, validating
        # that EnumNode correctly supports the relationship manager as expected by the
        # codebase.
        assert hasattr(e, "implementation_ref")


class TestCompoundDeserialization:
    """Test that deserialize handles the current fields correctly."""

    # codegraph:test-desc compound.test_compound_search_fields.TestCompoundDeserialization.test_class_deserialize_with_doc_embedding
    # Verifies that the deserialization method of LayerGraph correctly recreates a
    # ClassNode with its doc_embedding metadata intact, ensuring that document
    # embeddings are preserved during serialization round-trips.
    def test_class_deserialize_with_doc_embedding(self):
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundDeserialization.test_class_deserialize_with_doc_embedding::step_0
        # Calls LayerGraph.deserialize with test data to reconstruct a graph node,
        # producing the 'node' fixture used in subsequent assertions.
        data = {
            "type": "ClassNode",
            "qualified_name": "test::Foo",
            "name": "Foo",
            "kind": "class",
            "doc_embedding": [0.1, 0.2, 0.3],
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundDeserialization.test_class_deserialize_with_doc_embedding::post_0
        # Ensures the deserialized object is a ClassNode, verifying that
        # LayerGraph.deserialize preserves the correct node type for class
        # representations.
        assert isinstance(node, ClassNode)
        # codegraph:test-desc compound.test_compound_search_fields.TestCompoundDeserialization.test_class_deserialize_with_doc_embedding::post_1
        # Checks that the deserialized node's doc_embedding attribute exactly matches
        # the expected embedding [0.1, 0.2, 0.3], confirming that document vectors
        # survive serialization.
        assert node.doc_embedding == [0.1, 0.2, 0.3]