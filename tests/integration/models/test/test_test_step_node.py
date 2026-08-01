"""Unit tests for TestStepNode model."""

import json
from pathlib import Path

from codegraph.models.test import TestStepNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid

class TestTestStepNodeModel:
    """Test TestStepNode creation and field defaults."""

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_kind_defaults_to_test_step
    # Verifies that the 'kind' attribute of a TestStepNodeModel defaults to 'test_step',
    # ensuring consistent behavior before any explicit assignment.
    def test_kind_defaults_to_test_step(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_kind_defaults_to_test_step::step_0
        # Sets up the test by creating a TestStepNode model instance without specifying
        # a kind, so that its default value can later be checked.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_kind_defaults_to_test_step::post_0
        # Verifies that the 'kind' attribute of the TestStepNode model defaults to
        # 'test_step', ensuring the model correctly assigns a default type when none is
        # provided.
        assert node.kind == "test_step"

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_uid_auto_generated
    # Verifies that a new TestStepNode automatically receives a unique identifier upon
    # creation, ensuring each node can be reliably distinguished and referenced in test
    # workflows.
    def test_uid_auto_generated(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_uid_auto_generated::step_0
        # Sets up the test environment by initializing the node object (likely a
        # TestStepNode model instance) to ensure it is ready for verification of
        # automatic UUID generation.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_uid_auto_generated::post_0
        # Checks that the node's unique identifier (uid) is a non-empty string,
        # confirming that the system automatically generates a valid UUID when a new
        # node is created.
        assert len(node.uid) > 0

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_order_defaults_to_zero
    # This test verifies that the default value of the 'order' attribute in a
    # TestStepNodeModel is zero, ensuring that test steps are correctly initialized
    # without an explicit order.
    def test_order_defaults_to_zero(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_order_defaults_to_zero::step_0
        # Sets up the initial test context before verification, typically by
        # instantiating the test node or preparing its state to ensure that the system
        # under test is in a known baseline condition.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_order_defaults_to_zero::post_0
        # Verifies that the `order` attribute of the test step node defaults to zero,
        # which is important because it ensures that step ordering begins from a
        # predictable and consistent starting point in the absence of an explicit
        # assignment.
        assert node.order == 0

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_description_default_empty
    # Verifies that a TestStepNode instance initially has an empty description, ensuring
    # that the default state is properly initialized for subsequent usage.
    def test_description_default_empty(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_description_default_empty::step_0
        # Initializes the test by setting up the TestStepNodeModel instance without
        # providing a description, preparing to check its default state.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_description_default_empty::post_0
        # Verifies that the description attribute of the TestStepNodeModel is an empty
        # string, ensuring that when no description is provided, the model defaults to
        # an empty value.
        assert node.description == ""

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_defaults_to_zero
    # Verifies that the body_start attribute defaults to zero in a newly created
    # TestStepNodeModel, ensuring that an uninitialized step has a valid starting point
    # for body offset calculations.
    def test_body_start_defaults_to_zero(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_defaults_to_zero::step_0
        # Creates or configures a TestStepNodeModel instance without specifying a
        # body_start value, establishing the default state to be tested.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_defaults_to_zero::post_0
        # Verifies that the body_start attribute of the TestStepNodeModel is equal to
        # zero, confirming that the default value is correctly initialized as expected.
        assert node.body_start == 0

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_end_defaults_to_zero
    # This test verifies that the body_end attribute of a TestStepNode defaults to 0,
    # ensuring that a newly created test step node correctly initializes without an
    # explicit end boundary.
    def test_body_end_defaults_to_zero(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_end_defaults_to_zero::step_0
        # Sets up the initial state of the test step node model, ensuring it is ready
        # for the subsequent verification of default behavior.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_end_defaults_to_zero::post_0
        # Verifies that the body_end property defaults to zero, confirming that the test
        # step node model initializes with the expected default value.
        assert node.body_end == 0

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_can_be_set
    # Verifies that the body_start attribute of a TestStepNodeModel can be set
    # correctly, ensuring the model accurately captures the start of a step body for
    # test execution flow.
    def test_body_start_can_be_set(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_can_be_set::step_0
        # Sets up the initial state required for the test, ensuring that the test
        # environment is properly configured before executing the body_start assignment.
        node = TestStepNode(body_start=45, body_end=48)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_can_be_set::post_0
        # Verifies that the body_start property has been set to the expected value,
        # confirming that the assignment operation succeeded as intended.
        assert node.body_start == 45
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_body_start_can_be_set::post_1
        # Confirms that no unintended side effects occurred on related state, ensuring
        # the body_start setting did not corrupt other parts of the model.
        assert node.body_end == 48

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_tags_default_empty_list
    # Verifies that the tags attribute of a new TestStepNode model instance defaults to
    # an empty list, ensuring that tags are only added when explicitly set.
    def test_tags_default_empty_list(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_tags_default_empty_list::step_0
        # Sets up the test by creating the 'node' object that will be used in the test,
        # ensuring that it is initialized for subsequent assertions.
        node = TestStepNode()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_tags_default_empty_list::post_0
        # Verifies that the node's 'tags' attribute is an empty list by default,
        # confirming that no tags are automatically assigned upon node creation, which
        # is important for ensuring the system's default behavior aligns with
        # requirements.
        assert node.tags == []

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_llm_fields_include_order
    # Verifies that the TestStepNode model includes an 'order' field in its LLM-exposed
    # fields, ensuring that step sequencing information is available to the language
    # model for correct test execution ordering.
    def test_llm_fields_include_order(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_llm_fields_include_order::post_0
        # This assertion verifies that the first entry of the 'order' field is present
        # in the list of fields from the LLM response. It ensures that the order field
        # is correctly included in the LLM-generated data, which is critical for
        # maintaining proper sequencing of test steps.
        assert "order" in TestStepNode._llm_fields

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_llm_fields_include_description
    # Verifies that the LLM fields of a test step node include a description field,
    # ensuring that AI-generated step descriptions are properly captured and available
    # for downstream processing.
    def test_llm_fields_include_description(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_llm_fields_include_description::post_0
        # Asserts that the string 'description' is among the LLM-relevant fields
        # returned by the test step node model, ensuring the model exposes a
        # 'description' attribute for LLM consumption.
        assert "description" in TestStepNode._llm_fields

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_identity_fields
    # Verifies that the identity fields of a test step node model are correctly set and
    # maintained, ensuring data integrity and consistent identification within the test
    # framework.
    def test_identity_fields(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_identity_fields::post_0
        # Verifies that the `_identity_fields` attribute of the `TestStepNode` class
        # always contains exactly the tuple `('qualified_name',)`. This ensures that the
        # model consistently identifies nodes by their qualified name, which is critical
        # for correct referencing and deduplication in test step graphs.
        assert TestStepNode._identity_fields == ("qualified_name",)

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_description
    # Verifies that the serialize method of CompositeEntry includes the description
    # field in its output, ensuring that descriptive metadata is preserved for
    # downstream consumers.
    def test_serialize_includes_description(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_description::step_0
        # Sets up the test by preparing the serialization context and invoking the
        # serialize method on the CompositeEntry, ensuring the test has a baseline for
        # verification.
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            description="Call engine.set_target(30)",
            order=0,
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_description::post_0
        # Verifies that the serialized output correctly retains the step's description
        # text, confirming that the serialize method preserves meaningful human-readable
        # metadata.
        assert serialized["description"] == "Call engine.set_target(30)"
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_description::post_1
        # Validates that the serialized output preserves the step's execution order,
        # which is critical for maintaining the correct sequence of operations in the
        # composite entry.
        assert serialized["order"] == 0

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_type_discriminator
    # Verifies that the serialize method of CompositeEntry includes a type discriminator
    # in its output, ensuring that deserialization can correctly identify the object
    # type.
    def test_serialize_includes_type_discriminator(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_type_discriminator::step_0
        # Prepares the test environment by setting up the necessary context or objects
        # required for serialization, ensuring that the subsequent test steps have the
        # correct starting state.
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_includes_type_discriminator::post_0
        # Verifies that the serialized output contains a 'type' field set to
        # 'TestStepNode', confirming that the serialization process correctly includes
        # the type discriminator, which is essential for distinguishing node types
        # during deserialization.
        assert serialized["type"] == "TestStepNode"

    def test_serialize_excludes_body_start_end(self):
        """body_start/body_end are not in _llm_fields, excluded from llm serialization."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_excludes_body_start_end::step_0
        # Sets up the test by creating an instance of TestStepNodeModel, ensuring the
        # test environment is ready for serialization.
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            body_start=45,
            body_end=48,
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_excludes_body_start_end::post_0
        # Verifies that 'body_start' is not included in the serialized output,
        # confirming it is not part of LLM fields and thus correctly excluded from
        # serialization.
        assert "body_start" not in serialized
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_excludes_body_start_end::post_1
        # Verifies that 'body_end' is not included in the serialized output, ensuring
        # the serialization logic correctly excludes non-LLM fields as intended.
        assert "body_end" not in serialized

    def test_serialize_all_includes_body_start_end(self):
        """body_start/body_end included when fields='all'."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_all_includes_body_start_end::step_0
        # Arranges the test environment and initializes the necessary data structures,
        # ensuring the test starts from a clean and known state before executing the
        # serialization logic.
        node = TestStepNode(
            qualified_name="tests::test_update::test_single::step_0",
            body_start=45,
            body_end=48,
        )
        serialized = node.serialize(fields="all")
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_all_includes_body_start_end::post_0
        # Verifies that when serializing with fields set to 'all', the body_start
        # attribute in the serialized output is correctly set to 45, confirming that the
        # serialization includes the expected start position.
        assert serialized["body_start"] == 45
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_serialize_all_includes_body_start_end::post_1
        # Verifies that when serializing with fields set to 'all', the body_end
        # attribute in the serialized output is correctly set to 48, confirming that the
        # serialization includes the expected end position.
        assert serialized["body_end"] == 48

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_description
    # Verifies that deserializing a LayerGraph correctly restores a step node's
    # description, ensuring round-trip serialization preserves metadata for
    # traceability.
    def test_deserialize_with_description(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_description::step_0
        # Prepare the test environment by setting up the node fixture and invoking the
        # deserialize method on the code under test, advancing the test to produce the
        # result that will be verified.
        data = {
            "type": "TestStepNode",
            "qualified_name": "tests::test_update::test_single::step_0",
            "kind": "test_step",
            "order": 1,
            "description": "Assert result is 30.",
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_description::post_0
        # Check that the result of deserialization is an instance of TestStepNode,
        # confirming the method returns the expected type and not a generic or incorrect
        # node.
        assert isinstance(node, TestStepNode)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_description::post_1
        # Verify that a specific attribute of the deserialized node equals an expected
        # value, ensuring the deserialization correctly restores that attribute from the
        # serialized data.
        assert node.order == 1
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_description::post_2
        # Verify that another attribute of the deserialized node matches the expected
        # value, confirming that all relevant details are correctly reconstructed during
        # deserialization.
        assert node.description == "Assert result is 30."

    def test_deserialize_with_body_range(self):
        """TestStepNode deserializes body_start/body_end."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_body_range::step_0
        # Calls LayerGraph.deserialize with the node fixture to trigger the
        # deserialization logic and produce the actual TestStepNode result.
        data = {
            "type": "TestStepNode",
            "qualified_name": "tests::test_update::test_single::step_0",
            "kind": "test_step",
            "order": 0,
            "body_start": 45,
            "body_end": 48,
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_body_range::post_0
        # Checks that the result of deserialization is an instance of TestStepNode,
        # confirming the method returns the correct type of node.
        assert isinstance(node, TestStepNode)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_body_range::post_1
        # Verifies that the first body range attribute of the deserialized node matches
        # the expected integer, ensuring the deserialize method properly populates the
        # body_start attribute.
        assert node.body_start == 45
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_with_body_range::post_2
        # Verifies that the deserialized TestStepNode's second body range attribute
        # matches the expected value, ensuring the deserialization correctly sets all
        # body range fields.
        assert node.body_end == 48

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_computes_uid::step_0
        # Sets up the test environment by obtaining a node instance through the test
        # fixture, establishing the subject under test before the deserialization
        # verification.
        qn = "tests::test_update::test_single::step_0"
        data = {
            "type": "TestStepNode",
            "qualified_name": qn,
            "source": "test",
            "kind": "test_step",
            "order": 0,
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid("test", qn)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_deserialize_computes_uid::post_0
        # Confirms that the node's UID matches the expected UID, verifying that the
        # deterministic UID computation (compute_uid) is correctly integrated during
        # deserialization.
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify test_step_node_full.json deserializes correctly."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::step_0
        # Setup: calls LayerGraph.deserialize with the test_step_node_full.json data to
        # create the node fixture, preparing for subsequent field-by-field verification.
        with open(Path(__file__).resolve().parent / "data" / "test_step_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_0
        # Verifies that the deserialized object is an instance of TestStepNode,
        # confirming that the correct node type is created from the JSON data.
        assert isinstance(node, TestStepNode)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_1
        # Verifies that the deserialized node's order attribute matches the original
        # JSON value, confirming that the step's sequence position within the test is
        # preserved.
        assert node.order == data["order"]
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_2
        # Verifies that the deserialized node's description matches the original JSON
        # value, ensuring human-readable documentation is preserved through
        # deserialization.
        assert node.description == data["description"]
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_3
        # Verifies that the deserialized node's qualified_name matches the original JSON
        # value, confirming that identity and hierarchical naming are preserved during
        # deserialization.
        assert node.qualified_name == data["qualified_name"]
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_4
        # Verifies that the deserialized node's body_start matches the original JSON
        # value, confirming that the start boundary of the step's code body is correctly
        # restored.
        assert node.body_start == data["body_start"]
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeModel.test_fixture_roundtrip::post_5
        # Verifies that the deserialized node's body_end matches the original JSON
        # value, confirming that the end boundary of the step's code body is correctly
        # restored.
        assert node.body_end == data["body_end"]

class TestTestStepNodeRegistry:
    """Test that TestStepNode is registered in CodeGraphNode._registry."""

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeRegistry.test_test_step_node_in_registry
    # This test verifies that a test step node is correctly registered in the test step
    # node registry; ensuring that the registry functions properly is critical for
    # maintaining accurate tracking and retrieval of test step nodes within the system.
    def test_test_step_node_in_registry(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeRegistry.test_test_step_node_in_registry::post_0
        # Verifies that the test step node is present in the registry after
        # registration, ensuring the registry correctly tracks all registered nodes.
        assert "TestStepNode" in CodeGraphNode._registry

    # codegraph:test-desc test.test_test_step_node.TestTestStepNodeRegistry.test_test_step_node_registry_class
    # This test verifies that the TestStepNodeRegistry class is correctly defined and
    # registered, ensuring the test infrastructure can properly discover and manage step
    # nodes.
    def test_test_step_node_registry_class(self):
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeRegistry.test_test_step_node_registry_class::post_0
        # Verifies that 'TestStepNode' has been successfully registered in the
        # CodeGraphNode registry, confirming that the registry correctly maps the class
        # name to the actual class object, which is essential for dynamic class
        # resolution.
        assert CodeGraphNode._registry["TestStepNode"] is TestStepNode

class TestTestStepNodeImplementation:
    """Test HAS_IMPLEMENTATION relationship on TestStepNode."""

    def test_has_implementation_ref_relationship(self):
        """TestStepNode should have implementation_ref RelationshipTo ImplementationNode."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_has_implementation_ref_relationship::step_0
        # Initializes the test environment by setting up a TestStepNode instance,
        # enabling subsequent verification of its implementation reference.
        from codegraph.models.descriptors import Relationship as CGRelationship

        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_has_implementation_ref_relationship::post_0
        # Confirms that the TestStepNode has an 'implementation_ref' attribute, ensuring
        # the node is structured to hold a reference to its related implementation.
        assert hasattr(TestStepNode, "implementation_ref")
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_has_implementation_ref_relationship::post_1
        # Verifies that the 'implementation_ref' attribute is a relationship descriptor
        # (``Relationship``) linking to
        # ImplementationNode.
        assert isinstance(TestStepNode.implementation_ref, CGRelationship)
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_has_implementation_ref_relationship::post_2
        # Checks that the relationship type is exactly 'HAS_IMPLEMENTATION', ensuring
        # the semantic meaning of the link between TestStepNode and its implementation
        # is correct.
        assert (
            TestStepNode.implementation_ref.definition["relation_type"]
            == "HAS_IMPLEMENTATION"
        )

    def test_serialize_relationships_includes_implementation(self):
        """serialize_relationships() should list the HAS_IMPLEMENTATION edge."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_serialize_relationships_includes_implementation::step_0
        # Sets up the test environment, including creating a CodeGraphNode with a tag
        # and an attached Implementation, so that the serialize_relationships method can
        # be invoked with a known state.
        rels = TestStepNode.serialize_relationships()
        impl_rels = [r for r in rels if r["relation_type"] == "HAS_IMPLEMENTATION"]
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_serialize_relationships_includes_implementation::post_0
        # Checks that exactly one relationship is returned, ensuring the
        # HAS_IMPLEMENTATION edge is present and no extra or missing edges exist.
        assert len(impl_rels) == 1
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_serialize_relationships_includes_implementation::post_1
        # Verifies that the first (and only) relationship entry contains an 'attr' field
        # equal to 'implementation_ref', confirming the relationship correctly
        # references the implementation attribute.
        assert impl_rels[0]["attr"] == "implementation_ref"
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_serialize_relationships_includes_implementation::post_2
        # Validates that the relationship direction is 'OUTGOING', confirming the graph
        # edge points from the test step node to its implementation, as required by the
        # data model.
        assert impl_rels[0]["direction"] == "OUTGOING"

    def test_implementation_ref_not_in_llm_fields(self):
        """implementation_ref is a relationship, not a property field."""
        # codegraph:test-desc test.test_test_step_node.TestTestStepNodeImplementation.test_implementation_ref_not_in_llm_fields::post_0
        # Verifies that the 'implementation_ref' field is excluded from the set of
        # Low-Level Model (LLM) property fields, ensuring it is correctly treated as a
        # relationship attribute rather than a stored property.
        assert "implementation_ref" not in TestStepNode._llm_fields