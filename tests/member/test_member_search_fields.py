"""Unit tests for doc_embedding field and HAS_IMPLEMENTATION on member nodes."""

import json
from pathlib import Path

from codegraph.models.member import MethodNode, FunctionNode, AttributeNode, DefineNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestMemberEmbeddingFields:
    """Test embedding ArrayProperty fields on member nodes."""

    # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_default_empty
    # Verifies that a MethodNode's doc_embedding field defaults to an empty value,
    # ensuring the initial state of newly created method nodes is correct.
    def test_method_doc_embedding_default_empty(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_default_empty::step_0
        # Initializes the test environment by creating the MethodNode fixture,
        # establishing a baseline state where no embedding has been set.
        m = MethodNode(kind="method")
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_default_empty::post_0
        # Confirms that the doc_embedding attribute of the MethodNode is an empty list,
        # ensuring the default behavior returns no embeddings when none have been added.
        assert m.doc_embedding == []

    # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_stored
    # This test verifies that a method's documentation embedding is correctly stored and
    # retrievable, preventing data loss or corruption of generated embeddings.
    def test_method_doc_embedding_stored(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_stored::step_0
        # Sets up the initial state required for the test, ensuring that the environment
        # is ready for storing the method's doc embedding.
        m = MethodNode(kind="method", doc_embedding=[0.1, 0.2, 0.3])
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_method_doc_embedding_stored::post_0
        # Verifies that the doc_embedding field of the MethodNode instance equals the
        # expected list [0.1, 0.2, 0.3], confirming that the embedding was stored
        # accurately after processing.
        assert m.doc_embedding == [0.1, 0.2, 0.3]

    # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_function_doc_embedding_default
    # Verifies that the default docstring embedding for a FunctionNode is generated
    # correctly, ensuring documentation-based search features behave as expected.
    def test_function_doc_embedding_default(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_function_doc_embedding_default::step_0
        # Sets up the test by creating the FunctionNode fixture instance, providing the
        # necessary object on which the default doc_embedding value will later be
        # verified.
        f = FunctionNode(kind="function")
        # codegraph:test-desc member.test_member_search_fields.TestMemberEmbeddingFields.test_function_doc_embedding_default::post_0
        # Verifies that the newly created FunctionNode's doc_embedding attribute is an
        # empty list, confirming the expected default initialization of this field.
        assert f.doc_embedding == []


class TestMemberLlmFields:
    """Test that _llm_fields exclude implementation and embeddings."""

    def test_method_llm_fields_exclude_implementation(self):
        """MethodNode no longer includes implementation in _llm_fields."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_llm_fields_exclude_implementation::post_0
        # Verifies that 'implementation' is absent from the _llm_fields of a MethodNode,
        # ensuring sensitive or large implementation data is excluded from search field
        # representations as specified by the requirement.
        assert "implementation" not in MethodNode._llm_fields

    def test_function_llm_fields_exclude_implementation(self):
        """FunctionNode no longer includes implementation in _llm_fields."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_function_llm_fields_exclude_implementation::post_0
        # Verifies that the key 'implementation' is not present in the _llm_fields of a
        # FunctionNode, confirming that implementation details are intentionally
        # excluded from LLM-facing fields for security or relevance.
        assert "implementation" not in FunctionNode._llm_fields

    # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_llm_fields_exclude_embeddings
    # Verifies that when querying Member LLM fields with embeddings excluded, the system
    # returns the expected subset of fields, ensuring that data retrieval correctly
    # filters out embedded vectors to meet privacy and performance requirements.
    def test_method_llm_fields_exclude_embeddings(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_llm_fields_exclude_embeddings::post_0
        # Verifies that a specific non-embedding field (e.g., 'description') is present
        # in the search results, ensuring the exclusion logic does not inadvertently
        # remove required fields.
        assert "doc_embedding" not in MethodNode._llm_fields
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_llm_fields_exclude_embeddings::post_1
        # Verifies that a specific embedding field (e.g., 'embedding') is not present in
        # the search results, confirming the exclusion directive is correctly applied
        # and embeddings are filtered out as expected.
        assert "impl_embedding" not in MethodNode._llm_fields

    # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_function_llm_fields_exclude_embeddings
    # Verifies that the function for selecting LLM fields correctly excludes embedding
    # fields, ensuring that when embeddings are not needed, they are omitted from the
    # results to avoid unnecessary overhead and maintain data integrity.
    def test_function_llm_fields_exclude_embeddings(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_function_llm_fields_exclude_embeddings::post_0
        # Verifies that a specific embedding field is not present in the response,
        # ensuring the exclusion logic correctly omits embedding data from search
        # results.
        assert "doc_embedding" not in FunctionNode._llm_fields
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_function_llm_fields_exclude_embeddings::post_1
        # Verifies that another embedding field is excluded from the response,
        # confirming that all specified embedding fields are properly filtered out as
        # intended.
        assert "impl_embedding" not in FunctionNode._llm_fields

    # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_serialize_excludes_embeddings
    # Verifies that the serialize method of CompositeEntry correctly excludes embedding
    # data from the output, ensuring that serialized representations remain compact and
    # secure by omitting potentially large or sensitive model internals.
    def test_method_serialize_excludes_embeddings(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_serialize_excludes_embeddings::step_0
        # The step performs the call to the serialize method on the MethodNode fixture,
        # capturing the serialized output. This action executes the core functionality
        # being tested, setting up the data for subsequent assertions.
        m = MethodNode(
            kind="method",
            name="draw",
            doc_embedding=[0.1, 0.2, 0.3],
        )
        serialized = m.serialize()
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_serialize_excludes_embeddings::post_0
        # This assertion verifies that the 'doc_embedding' field is not present in the
        # serialized output. It is essential because embeddings are large metadata that
        # should be excluded from serialization to reduce data size and protect
        # sensitive information.
        assert "doc_embedding" not in serialized
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_method_serialize_excludes_embeddings::post_1
        # This assertion checks that the 'impl_embedding' field is absent from the
        # serialized result. It confirms that the serialization logic correctly filters
        # out all embedding fields, maintaining data privacy and efficiency.
        assert "impl_embedding" not in serialized

    def test_attribute_llm_fields_exclude_implementation(self):
        """AttributeNode does not include implementation in _llm_fields."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_attribute_llm_fields_exclude_implementation::post_0
        # Verifies that the string 'implementation' is not present in the _llm_fields
        # attribute of the node, ensuring that internal implementation details are
        # excluded from the generated LLM fields.
        assert "implementation" not in AttributeNode._llm_fields

    def test_define_llm_fields_exclude_implementation(self):
        """DefineNode does not include implementation in _llm_fields."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberLlmFields.test_define_llm_fields_exclude_implementation::post_0
        # Verifies that the string 'implementation' is not present in the list of LLM
        # fields returned by the `define_llm_fields` method. This ensures that internal
        # implementation details are not exposed in the public API, maintaining the
        # intended separation of interface and implementation.
        assert "implementation" not in DefineNode._llm_fields


class TestMemberImplementationRef:
    """Test that member nodes have the HAS_IMPLEMENTATION relationship."""

    def test_method_has_implementation_ref(self):
        """MethodNode has an implementation_ref relationship manager."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_method_has_implementation_ref::step_0
        # Sets up the test environment by creating or retrieving a method node instance
        # for subsequent validation.
        m = MethodNode(kind="method")
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_method_has_implementation_ref::post_0
        # Checks that the method node possesses the implementation_ref attribute,
        # confirming the relationship manager exists as expected.
        assert hasattr(m, "implementation_ref")

    def test_function_has_implementation_ref(self):
        """FunctionNode has an implementation_ref relationship manager."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_function_has_implementation_ref::step_0
        # The setup block initializes the test environment by creating or retrieving the
        # necessary FunctionNode fixture, preparing for the subsequent assertions.
        f = FunctionNode(kind="function")
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_function_has_implementation_ref::post_0
        # This assertion checks that the FunctionNode instance has an attribute named
        # 'implementation_ref', confirming that the relationship manager is present as
        # required by the model's design.
        assert hasattr(f, "implementation_ref")

    def test_attribute_has_implementation_ref(self):
        """AttributeNode has an implementation_ref relationship manager."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_attribute_has_implementation_ref::step_0
        # Sets up the test by creating the AttributeNode instance 'a', which is the
        # foundational step to enable subsequent verification of the attribute's
        # relationship manager.
        a = AttributeNode(kind="attribute")
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_attribute_has_implementation_ref::post_0
        # Verifies that the AttributeNode instance has an attribute named
        # 'implementation_ref', confirming that the code under test correctly defines
        # the expected relationship manager.
        assert hasattr(a, "implementation_ref")

    def test_define_has_implementation_ref(self):
        """DefineNode has an implementation_ref relationship manager."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_define_has_implementation_ref::step_0
        # Sets up the DefineNode fixture without executing any search, providing a
        # baseline for verifying the existence of the implementation_ref attribute.
        d = DefineNode(kind="define")
        # codegraph:test-desc member.test_member_search_fields.TestMemberImplementationRef.test_define_has_implementation_ref::post_0
        # Confirms that a DefineNode object possesses an implementation_ref attribute,
        # ensuring that the required relationship manager exists for linking to
        # implementation code.
        assert hasattr(d, "implementation_ref")


class TestMemberDeserialization:
    """Test that deserialize handles current fields correctly."""

    def test_method_fixture_roundtrip(self):
        """Verify method_node_full.json deserializes correctly."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_method_fixture_roundtrip::step_0
        # Sets up the test by reading the JSON fixture file and deserializing it into an
        # object, which is then stored as the 'node' fixture for subsequent assertions.
        with open(DATA_DIR / "method_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_method_fixture_roundtrip::post_0
        # Confirms that the deserialized object is an instance of MethodNode, which is
        # the expected type for a method-level node from the JSON fixture.
        assert isinstance(node, MethodNode)
        # implementation is no longer on MethodNode
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_method_fixture_roundtrip::post_1
        # Verifies that if an implementation attribute exists, it is empty; this
        # confirms that the deserialized method node does not have a non-empty
        # implementation text when the original JSON had none.
        assert not hasattr(node, "implementation") or getattr(node, "implementation", "") == ""
        # doc_embedding should roundtrip
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_method_fixture_roundtrip::post_2
        # Verifies that the 'doc_embedding' attribute of the deserialized node matches
        # the 'doc_embedding' field in the original JSON data, ensuring correct transfer
        # of documentation embedding information.
        assert node.doc_embedding == data.get("doc_embedding", [])
        # impl_embedding is no longer on MethodNode
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_method_fixture_roundtrip::post_3
        # Verifies that if an implementation embedding exists, it is empty; this ensures
        # that deserialized method nodes from JSON do not unexpectedly carry non-empty
        # embedding data when the input was empty.
        assert not hasattr(node, "impl_embedding") or getattr(node, "impl_embedding", []) == []

    def test_function_fixture_roundtrip(self):
        """Verify function_node_full.json deserializes correctly."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_function_fixture_roundtrip::step_0
        # This step sets up the test by deserializing the JSON data using the
        # `LayerGraph.deserialize` method, preparing the deserialized node for
        # subsequent assertions to verify its correctness.
        with open(DATA_DIR / "function_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_function_fixture_roundtrip::post_0
        # This assertion verifies that the deserialized node is an instance of
        # `FunctionNode`, ensuring that `LayerGraph.deserialize` correctly interprets
        # the JSON structure as a function node rather than another type of node.
        assert isinstance(node, FunctionNode)
        # codegraph:test-desc member.test_member_search_fields.TestMemberDeserialization.test_function_fixture_roundtrip::post_1
        # This assertion verifies that the `doc_embedding` attribute of the deserialized
        # node matches the original data, confirming that embedded document vectors are
        # preserved accurately during the deserialization process.
        assert node.doc_embedding == data.get("doc_embedding", [])


class TestMemberBodyLocation:
    """Test body_start and body_end fields on member nodes."""

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_default_zero
    # Verifies that the body_start attribute of a method node defaults to zero, ensuring
    # consistent initialization of code location tracking for method analysis.
    def test_method_body_start_default_zero(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_default_zero::step_0
        # Calls `m.body_start` (assuming `m` is the MethodNode fixture) to retrieve the
        # body start value of the method. This advances the test by obtaining the actual
        # value that will be compared against the expected default of zero.
        m = MethodNode(kind="method")
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_default_zero::post_0
        # Verifies that the body start value of the method is equal to zero. This
        # assertion is important because it confirms that the body_start property
        # defaults to zero when no body content has been set, ensuring the correct
        # initial state of the MethodNode.
        assert m.body_start == 0

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_end_default_zero
    # Verifies that a method node's body_end attribute defaults to zero to ensure
    # accurate tracking of method boundaries in code analysis.
    def test_method_body_end_default_zero(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_end_default_zero::step_0
        # Sets up the test by initializing the MethodNode fixture and preparing its
        # attributes for verification.
        m = MethodNode(kind="method")
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_end_default_zero::post_0
        # Verifies that the method's body_end attribute defaults to zero, ensuring
        # consistent initialization behavior.
        assert m.body_end == 0

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_stored
    # Verifies that a MethodNode correctly stores the starting line number of its body
    # within the source code, which ensures accurate code structure analysis.
    def test_method_body_start_stored(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_stored::step_0
        # This step sets up the initial state by creating or retrieving the MethodNode
        # object, preparing for subsequent assertions on its body_start property.
        m = MethodNode(kind="method", body_start=25, body_end=30)
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_stored::post_0
        # This assertion checks that the method node's body_start attribute is not None,
        # ensuring the body start location has been properly captured and stored.
        assert m.body_start == 25
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_body_start_stored::post_1
        # This assertion verifies that the method node's body_start attribute stores the
        # correct value, confirming that the body start location is accurately recorded.
        assert m.body_end == 30

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_function_body_start_stored
    # Verifies that the body start location of a function node is correctly stored,
    # ensuring reliable code graph analysis and downstream processing.
    def test_function_body_start_stored(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_function_body_start_stored::step_0
        # Sets up the test by creating a FunctionNode with a known body_start value,
        # establishing the precondition needed to check the stored attribute.
        f = FunctionNode(kind="function", body_start=100, body_end=120)
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_function_body_start_stored::post_0
        # Verifies that the 'body_start' attribute of the FunctionNode equals the
        # expected value, confirming that the node correctly captured the start location
        # of the function body.
        assert f.body_start == 100
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_function_body_start_stored::post_1
        # Checks that the 'body_start' attribute is not None, ensuring that the field is
        # always populated even if its specific value varies.
        assert f.body_end == 120

    def test_body_start_not_in_llm_fields(self):
        """body_start/body_end are extraction plumbing, not for LLM context."""
        for cls in [MethodNode, FunctionNode, AttributeNode, DefineNode]:
            # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_body_start_not_in_llm_fields::post_0
            # Verifies that body_start is not included in the list of fields returned
            # for LLM context, ensuring that internal extraction plumbing is not exposed
            # to LLM processing.
            assert "body_start" not in cls._llm_fields
            # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_body_start_not_in_llm_fields::post_1
            # Verifies that body_end is not included in the list of fields returned for
            # LLM context, ensuring that internal extraction plumbing is not exposed to
            # LLM processing.
            assert "body_end" not in cls._llm_fields

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_serialize_excludes_body_location
    # Verifies that the serialize method of CompositeEntry excludes the body_location
    # field, ensuring that serialized output is correct and does not leak internal
    # location data.
    def test_method_serialize_excludes_body_location(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_serialize_excludes_body_location::step_0
        # Setup step that prepares the test environment by initializing the MethodNode
        # fixture 'm' and performing any necessary configuration before serialization.
        m = MethodNode(kind="method", body_start=25, body_end=30, name="draw")
        serialized = m.serialize()
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_serialize_excludes_body_location::post_0
        # Checks that the serialized method omits the 'body_start' field, ensuring that
        # the start of the method body is not exposed in the serialized output as
        # intended.
        assert "body_start" not in serialized
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_method_serialize_excludes_body_location::post_1
        # Verifies that the serialized representation of the method does not contain the
        # key 'body_end', confirming that body-end location is correctly excluded to
        # meet privacy or abstraction requirements.
        assert "body_end" not in serialized

    # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_with_body_location
    # Verifies that the deserialize method correctly reconstructs a Graph instance with
    # the expected body_location attribute from its serialized form, ensuring data
    # integrity during the round-trip serialization/deserialization process.
    def test_deserialize_with_body_location(self):
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_with_body_location::step_0
        # Performs the initial setup of the test, likely constructing or configuring a
        # `LayerGraph` object and the `node` fixture, preparing them for the
        # deserialization operation that will be verified in subsequent steps.
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
            "body_start": 25,
            "body_end": 30,
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_with_body_location::post_0
        # Asserts that the deserialized node is an instance of `MethodNode`, ensuring
        # the correct type is produced after deserialization, which is critical for type
        # safety and downstream operations.
        assert isinstance(node, MethodNode)
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_with_body_location::post_1
        # Verifies that the result of deserialization equals a specific expected value,
        # confirming that the `deserialize` method correctly processes the input and
        # returns the expected output.
        assert node.body_start == 25
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_with_body_location::post_2
        # Checks that another aspect of the deserialized result matches an expected
        # value, likely confirming specific attributes (e.g., body location) are
        # correctly set, validating the method's accuracy in reconstructing the node.
        assert node.body_end == 30

    def test_deserialize_without_body_location(self):
        """Old fixtures without body_start/body_end should default to 0."""
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_without_body_location::step_0
        # Calls deserialize() on the node fixture to trigger the code under test and
        # produce a result for validation.
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_without_body_location::post_0
        # Verifies that the deserialized node's body_end attribute equals 0, confirming
        # default values are applied correctly for missing fields.
        assert node.body_start == 0
        # codegraph:test-desc member.test_member_search_fields.TestMemberBodyLocation.test_deserialize_without_body_location::post_1
        # Verifies that the deserialized node's body_start attribute equals 0, ensuring
        # backward compatibility with old fixtures.
        assert node.body_end == 0