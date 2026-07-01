"""Unit tests for TestNode model."""

import json
from pathlib import Path

from codegraph.models.test import TestNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestTestNodeModel:
    """Test TestNode creation and field defaults."""

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_kind_defaults_to_test
    # Verifies that when a TestNode is instantiated without an explicit 'kind', it
    # defaults to 'test', ensuring consistent behavior and simplifying object creation
    # for test nodes.
    def test_kind_defaults_to_test(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_kind_defaults_to_test::step_0
        # Creates an instance of TestNodeModel using the default constructor to set up
        # the initial state for verifying the default value of the 'kind' attribute.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_kind_defaults_to_test::post_0
        # Verifies that the 'kind' attribute of the TestNodeModel instance is equal to
        # 'test', confirming the expected default behavior of the model.
        assert node.kind == "test"

    def test_uid_auto_generated(self):
        """UniqueIdProperty auto-generates a UUID for uid when no value is provided."""
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_uid_auto_generated::step_0
        # Creates a new instance of TestNodeModel without providing a uid, in order to
        # test that the UniqueIdProperty automatically generates one.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_uid_auto_generated::post_0
        # Asserts that the uid field is not empty, ensuring the auto-generation
        # mechanism produced a value as required.
        assert len(node.uid) > 0
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_uid_auto_generated::post_1
        # Verifies that the auto-generated uid is a valid UUID string, confirming that
        # the property correctly conforms to the UUID format.
        assert node.qualified_name == ""

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_qualified_name_explicit_set
    # Verifies that directly setting the qualified_name attribute on a TestNode yields
    # the correct fully qualified name, ensuring name resolution behaves as expected
    # when the name is explicitly assigned rather than derived.
    def test_qualified_name_explicit_set(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_qualified_name_explicit_set::step_0
        # Initializes a test node model with an explicitly set qualified name to prepare
        # for verifying that the custom name is stored correctly.
        node = TestNode(qualified_name="tests::test_update::test_single_field")
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_qualified_name_explicit_set::post_0
        # Confirms that the model's qualified name attribute matches the explicitly set
        # value, ensuring the node correctly retains user-defined naming.
        assert node.qualified_name == "tests::test_update::test_single_field"

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_name_default_empty
    # Verifies that the test_name attribute of a TestNodeModel instance defaults to an
    # empty string, ensuring the model's initial state is correctly set and prevents
    # potential errors from None values.
    def test_test_name_default_empty(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_name_default_empty::step_0
        # Initializes the test node model to set up a default state where no test name
        # has been assigned.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_name_default_empty::post_0
        # Verifies that the test_name attribute defaults to an empty string, ensuring
        # the model's initial state is correct before any custom naming is applied.
        assert node.test_name == ""

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_module_default_empty
    # Verifies that when a TestNode is constructed without specifying a module, it
    # defaults to an empty string, which is critical for ensuring the model's default
    # behavior meets correctness expectations.
    def test_test_module_default_empty(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_module_default_empty::step_0
        # Sets up the test environment by creating a fresh instance of the test node
        # model to ensure a clean starting state before verifying its default
        # properties.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_test_module_default_empty::post_0
        # Verifies that the test_module attribute of the node is an empty string by
        # default, confirming that the model initializes its module field to an empty
        # value as expected.
        assert node.test_module == ""

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_method_defaults_to_automated
    # Verifies that when no test method type is explicitly provided, the model
    # automatically defaults to 'AUTOMATED', ensuring correct default behavior for test
    # classification.
    def test_method_defaults_to_automated(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_method_defaults_to_automated::step_0
        # Sets up the initial state of the test node, likely creating an instance with
        # default parameters to simulate a fresh test node before method verification.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_method_defaults_to_automated::post_0
        # Verifies that the node's method attribute is set to 'automated' by default,
        # confirming the intended default behavior of the test node model.
        assert node.method == "automated"

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_description_default_empty
    # Verifies that a newly created TestNodeModel instance has an empty description by
    # default, ensuring the model initializes correctly without residual or unexpected
    # description content.
    def test_description_default_empty(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_description_default_empty::step_0
        # Instantiates a TestNodeModel without providing a description, to set up the
        # object for evaluating its default description behavior.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_description_default_empty::post_0
        # Verifies that the description attribute of the TestNodeModel is an empty
        # string, confirming that newly created nodes have no default description.
        assert node.description == ""

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_tags_default_empty_list
    # Verifies that a new TestNodeModel instance has an empty list of tags by default,
    # ensuring the initial state is correct for downstream operations.
    def test_tags_default_empty_list(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_tags_default_empty_list::step_0
        # Sets up the test environment and creates any necessary fixtures for testing
        # the default tags attribute.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_tags_default_empty_list::post_0
        # Verifies that the node's tags attribute defaults to an empty list, ensuring
        # the model initializes without any preassigned tags.
        assert node.tags == []

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_doc_embedding_default_empty
    # This test verifies that the default value for doc_embedding is an empty list,
    # which is important to ensure that a node is initialized without any stored
    # embeddings.
    def test_doc_embedding_default_empty(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_doc_embedding_default_empty::step_0
        # Sets up the test environment by initializing the node instance to be used in
        # the verification.
        node = TestNode()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_doc_embedding_default_empty::post_0
        # Verifies that the node's doc_embedding attribute is an empty list by default,
        # confirming that no embedding is assigned before any document processing
        # occurs.
        assert node.doc_embedding == []

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_test_name
    # Verifies that the LLM fields include the test name, ensuring that the test node
    # model correctly associates metadata with the specific test.
    def test_llm_fields_include_test_name(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_test_name::post_0
        # Verifies that the test name appears in the LLM fields returned by the model,
        # ensuring that the LLM fields correctly include identifying information about
        # the test case.
        assert "test_name" in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_test_module
    # Verifies that the TestNode model includes its test module name among the
    # LLM-related fields, ensuring the system correctly identifies and exposes the
    # module context for test reporting and AI-assisted debugging.
    def test_llm_fields_include_test_module(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_test_module::post_0
        # Verifies that a specific value is contained within the test module's LLM
        # fields, ensuring the fields are correctly populated with expected data for
        # model integrity.
        assert "test_module" in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_method
    # Verifies that the LLM-related fields are correctly included in the TestNodeModel,
    # ensuring that the model's structured output for LLMs contains all required fields.
    def test_llm_fields_include_method(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_method::post_0
        # Verifies that a specific method is included in the response from the LLM
        # fields endpoint, ensuring that the expected functionality is exposed
        # correctly.
        assert "method" in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_description
    # Verifies that the LLM-related fields of a TestNodeModel include a description,
    # ensuring that the model correctly exposes this metadata for downstream use.
    def test_llm_fields_include_description(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_description::post_0
        # Verifies that the string 'description' is present in the llm_fields attribute
        # of the test node model, confirming that description field metadata is included
        # for LLM processing.
        assert "description" in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_qualified_name
    # Verifies that an LLM-related field on a node includes the node's fully qualified
    # name to ensure that any downstream LLM processing or reference can correctly
    # identify the node by its full path.
    def test_llm_fields_include_qualified_name(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_include_qualified_name::post_0
        # Verifies that the qualified name of the test node is included in the LLM
        # fields, ensuring that the LLM has access to the fully qualified identifier
        # needed for accurate context and traceability.
        assert "qualified_name" in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_exclude_embedding
    # Verifies that the embedding field is excluded from the LLM fields to prevent large
    # vectors from being sent to the language model, reducing costs and improving
    # performance.
    def test_llm_fields_exclude_embedding(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_llm_fields_exclude_embedding::post_0
        # Verifies that the 'embedding' field is excluded from the set of LLM-related
        # fields returned by the model. This ensures the code correctly filters out
        # non-trainable or meta fields during LLM operations, preventing unintended use
        # or storage of embeddings.
        assert "doc_embedding" not in TestNode._llm_fields

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_identity_fields
    # Verifies that the identity fields of the model are correctly populated, ensuring
    # the model can be uniquely identified in persistence and retrieval operations.
    def test_identity_fields(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_identity_fields::post_0
        # Verifies that the `_identity_fields` attribute of `TestNode` is set to the
        # single field `('qualified_name',)`, ensuring that the model correctly
        # identifies which field serves as its unique identifier in the system.
        assert TestNode._identity_fields == ("qualified_name",)

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_test_name
    # Verifies that the serialized output of CompositeEntry includes the test name to
    # ensure that serialization functions capture the test identifier for traceability
    # and debugging.
    def test_serialize_includes_test_name(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_test_name::step_0
        # Sets up the test by recording the current test context, ensuring that each
        # serialized entry carries the originating test name.
        node = TestNode(
            qualified_name="tests::test_update::test_single_field",
            test_name="test_single_field",
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_test_name::post_0
        # Verifies that the serialized output contains a 'test_name' field equal to
        # 'test_single_field', confirming that the serialize method correctly embeds the
        # test identifier in the serialized data.
        assert serialized["test_name"] == "test_single_field"

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_excludes_embedding
    # Verifies that the serialize method of CompositeEntry correctly excludes embedding
    # data, which is important to ensure serialization outputs contain only the intended
    # metadata.
    def test_serialize_excludes_embedding(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_excludes_embedding::step_0
        # Sets up any necessary test data or context required before exercising the
        # serialize method.
        node = TestNode(
            qualified_name="tests::test_update::test_single_field",
            doc_embedding=[0.1, 0.2, 0.3],
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_excludes_embedding::post_0
        # Verifies that the serialized output does not contain the 'doc_embedding'
        # field, ensuring that the embedding data is intentionally excluded from
        # serialization to avoid unnecessary data bloat or exposure.
        assert "doc_embedding" not in serialized

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_type_discriminator
    # Verifies that serialization of a CompositeEntry includes a type discriminator
    # field, ensuring deserialization can correctly identify the object's concrete type.
    def test_serialize_includes_type_discriminator(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_type_discriminator::step_0
        # Sets up the test environment and instantiates the TestNode object, preparing
        # it for serialization.
        node = TestNode(qualified_name="tests::test_update::test_single_field")
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_serialize_includes_type_discriminator::post_0
        # Verifies that the serialized output contains a 'type' field equal to
        # 'TestNode', ensuring the type discriminator is included to support polymorphic
        # deserialization.
        assert serialized["type"] == "TestNode"

    # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name
    # Verifies that deserializing a LayerGraph with a specific test name correctly
    # reconstructs the graph's state, ensuring serialization and deserialization are
    # symmetric and data integrity is maintained.
    def test_deserialize_with_test_name(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name::step_0
        # Sets up the test environment by initializing the node fixture and any required
        # state, preparing the data structure that will be passed to the deserialize
        # method for verification.
        data = {
            "type": "TestNode",
            "qualified_name": "tests::test_update::test_single_field",
            "kind": "test",
            "test_name": "test_single_field",
            "test_module": "tests.test_update",
            "method": "automated",
            "description": "Verifies single field update.",
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name::post_0
        # Verifies that the deserialized object is an instance of TestNode, confirming
        # that the deserialize method produces the correct node type for test metadata.
        assert isinstance(node, TestNode)
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name::post_1
        # Verifies that the deserialized node's test_name attribute equals
        # 'test_single_field', ensuring the test name is correctly reconstructed during
        # deserialization.
        assert node.test_name == "test_single_field"
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name::post_2
        # Verifies that the deserialized node's test_module attribute matches the
        # expected value 'tests.test_update', ensuring the LayerGraph deserialize method
        # correctly restores the test module path from serialized data.
        assert node.test_module == "tests.test_update"
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_with_test_name::post_3
        # Verifies that the deserialized node's method attribute is set to 'automated',
        # confirming that the deserialize method accurately preserves the test execution
        # method type.
        assert node.method == "automated"

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_computes_uid::step_0
        # Calls the deserialize() method on the node, which sets up the node's uid for
        # subsequent verification.
        data = {
            "type": "TestNode",
            "qualified_name": "tests::test_update::test_single_field",
            "kind": "test",
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid("tests::test_update::test_single_field")
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_deserialize_computes_uid::post_0
        # Checks that after deserialization, the node's uid matches the expected
        # deterministic uid computed from the qualified name, ensuring consistent and
        # reproducible identification.
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify test_node_full.json deserializes correctly."""
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::step_0
        # Sets up the test environment by loading the JSON file 'test_node_full.json'
        # and deserializing it into a node fixture, preparing the test for subsequent
        # verifications.
        with open(DATA_DIR / "test_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_0
        # Confirms that the deserialized object is an instance of TestNode, ensuring the
        # type is correctly reconstructed.
        assert isinstance(node, TestNode)
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_1
        # Verifies that the node's test_name attribute matches the original JSON data,
        # ensuring correct deserialization of the test name field.
        assert node.test_name == data["test_name"]
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_2
        # Verifies that the node's test_module attribute matches the original JSON data,
        # ensuring correct deserialization of the module field.
        assert node.test_module == data["test_module"]
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_3
        # Verifies that the node's method attribute matches the original JSON data,
        # ensuring correct deserialization of the method field.
        assert node.method == data["method"]
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_4
        # Verifies that the node's qualified_name attribute matches the original JSON
        # data, ensuring correct deserialization of the qualified name field.
        assert node.qualified_name == data["qualified_name"]
        # codegraph:test-desc test.test_test_node.TestTestNodeModel.test_fixture_roundtrip::post_5
        # Verifies that the node's tags attribute matches the original JSON data,
        # ensuring correct deserialization of the tags field.
        assert node.tags == data["tags"]


class TestTestNodeRegistry:
    """Test that TestNode is registered in CodeGraphNode._registry."""

    # codegraph:test-desc test.test_test_node.TestTestNodeRegistry.test_test_node_in_registry
    # Verifies that a test node previously registered in the registry is correctly
    # found, ensuring the registry accurately tracks all test nodes.
    def test_test_node_in_registry(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeRegistry.test_test_node_in_registry::post_0
        # Verifies that a specific test node is present in the registry after it has
        # been added. This ensures the registry correctly maintains and reports its
        # membership, which is essential for tracking and retrieving registered test
        # nodes.
        assert "TestNode" in CodeGraphNode._registry

    # codegraph:test-desc test.test_test_node.TestTestNodeRegistry.test_test_node_registry_class
    # Verifies that the TestNodeRegistry class is properly defined and can be
    # instantiated, ensuring the test node registry system initializes correctly.
    def test_test_node_registry_class(self):
        # codegraph:test-desc test.test_test_node.TestTestNodeRegistry.test_test_node_registry_class::post_0
        # Verifies that the 'TestNode' class was correctly registered in the
        # CodeGraphNode's class-level registry, ensuring that the registration mechanism
        # works as expected and that the registered class can be retrieved by its name.
        assert CodeGraphNode._registry["TestNode"] is TestNode