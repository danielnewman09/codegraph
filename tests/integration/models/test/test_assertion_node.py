"""Unit tests for AssertionNode model."""

import json
from pathlib import Path

from codegraph.models.test import AssertionNode
from codegraph.models.tags import CodeGraphNode
from codegraph.models.descriptors import PropertyRegistry
from codegraph.uid import compute_uid

class TestAssertionNodeModel:
    """Test AssertionNode creation and field defaults."""

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_kind_defaults_to_assertion
    # Verifies that when an AssertionNode is created, its type defaults to 'assertion',
    # ensuring the node correctly identifies itself as an assertion in the model.
    def test_kind_defaults_to_assertion(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_kind_defaults_to_assertion::step_0
        # Sets up the test environment by initializing the AssertionNode object (the
        # node fixture) so that its default properties can be examined.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_kind_defaults_to_assertion::post_0
        # Checks that the 'kind' attribute of the AssertionNode equals 'assertion',
        # confirming the default value is correctly assigned and the model behaves as
        # specified.
        assert node.kind == "assertion"

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_uid_auto_generated
    # Verifies that an AssertionNode instance is automatically assigned a unique
    # identifier (uid) upon creation, ensuring each node can be uniquely referenced and
    # tracked within the model.
    def test_uid_auto_generated(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_uid_auto_generated::step_0
        # Sets up the test environment by initializing the node fixture, enabling the
        # subsequent verification of its auto-generated UID.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_uid_auto_generated::post_0
        # Checks that the node's UID is a non-empty string, confirming the automatic UID
        # generation feature of AssertionNode works correctly.
        assert len(node.uid) > 0

    def test_phase_required(self):
        """phase is a required field — constructing without it uses default."""
        # Property(required=True) is enforced at save time, not construction
        # time.  We test the field is declared required.
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_phase_required::step_0
        # Sets up the test by instantiating an AssertionNode without a phase value, so
        # the default phase assignment can be observed and verified.
        props = PropertyRegistry.properties_of(AssertionNode)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_phase_required::post_0
        # Verifies that the 'phase' property is marked as required in the model's
        # metadata, ensuring the system properly enforces mandatory fields for data
        # integrity.
        assert props["phase"].required is True
    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_order_defaults_to_zero
    # This test verifies that a newly created AssertionNode instance has its order
    # attribute set to zero by default, ensuring consistent initialization behavior and
    # preventing unexpected ordering issues in the system.
    def test_order_defaults_to_zero(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_order_defaults_to_zero::step_0
        # Sets up the test by initializing the AssertionNode fixture, establishing the
        # baseline state needed to verify the default value of the 'order' field.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_order_defaults_to_zero::post_0
        # Confirms that the 'order' attribute of the AssertionNode is zero by default,
        # validating that the model correctly assigns a default value when none is
        # provided.
        assert node.order == 0

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_operator_defaults_to_eq
    # Verifies that an AssertionNode is created with the operator field defaulting to
    # 'eq', ensuring consistent behavior for assertion comparisons in the model.
    def test_operator_defaults_to_eq(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_operator_defaults_to_eq::step_0
        # Sets up the test by instantiating an AssertionNode with no explicit operator,
        # preparing it for inspection of its default value.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_operator_defaults_to_eq::post_0
        # Verifies that the AssertionNode's operator property defaults to 'eq', ensuring
        # the model initializes with the expected default behavior.
        assert node.operator == "=="

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_description_default_empty
    # Verifies that a newly created AssertionNode instance has an empty description by
    # default, ensuring the initial state is correctly unset for downstream usage.
    def test_description_default_empty(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_description_default_empty::step_0
        # Calls the default constructor of AssertionNode with no arguments, setting up
        # the node object to be inspected for its default description value.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_description_default_empty::post_0
        # Verifies that the description attribute of the AssertionNode is an empty
        # string, confirming that newly created assertion nodes have no pre-set
        # description text.
        assert node.description == ""

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_tags_default_empty_list
    # Verifies that a newly created AssertionNode instance initializes with an empty
    # tags list, ensuring the default state is correct for subsequent operations.
    def test_tags_default_empty_list(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_tags_default_empty_list::step_0
        # Sets up the test by initializing the AssertionNode with no tags, preparing to
        # check its default tag attribute.
        node = AssertionNode()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_tags_default_empty_list::post_0
        # Verifies that the tags attribute of the AssertionNode is an empty list,
        # confirming the default behavior of the model.
        assert node.tags == []

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_phase
    # Verifies that the LLM-generated fields of the AssertionNode model properly include
    # the phase attribute, ensuring that the model correctly captures and exposes the
    # phase context required for downstream processing.
    def test_llm_fields_include_phase(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_phase::post_0
        # Verifies that the variable containing phase information is part of the LLM
        # fields, ensuring the assertion node correctly includes the phase attribute in
        # its output for downstream processing.
        assert "phase" in AssertionNode._llm_fields

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_operator
    # This test verifies that the operator field is correctly included in the
    # LLM-related fields of an AssertionNode model, ensuring that generated assertions
    # carry the necessary operator information for accurate test behavior.
    def test_llm_fields_include_operator(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_operator::post_0
        # Verifies that the operator field is present in the LLM-related fields of an
        # assertion node. This ensures the system’s representation of a requirement
        # correctly includes both operator and concept, which is essential for
        # generating complete and accurate natural language test descriptions.
        assert "operator" in AssertionNode._llm_fields

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_order
    # This test ensures that the LLM-generated fields of an assertion node maintain the
    # correct ordering, which is critical for the system's ability to correctly
    # interpret and process assertion data.
    def test_llm_fields_include_order(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_order::post_0
        # Verifies that the expected field name is present in the list of fields
        # returned by the LLM, confirming that the model correctly includes each
        # required field in its output.
        assert "order" in AssertionNode._llm_fields

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_description
    # This test verifies that the assertion node model includes a description field in
    # its LLM fields, ensuring that language model inputs carry the necessary
    # descriptive context for accurate interpretation and response generation.
    def test_llm_fields_include_description(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_llm_fields_include_description::post_0
        # Verifies that the word 'description' appears in the output of the LLM fields.
        # This ensures that the model exposes its description field to LLMs, which is
        # necessary for the system's self-documenting behavior.
        assert "description" in AssertionNode._llm_fields

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_identity_fields
    # Verifies that the identity fields of an AssertionNodeModel instance are correctly
    # populated and unique, which is essential for ensuring data integrity and
    # consistent referencing across the system.
    def test_identity_fields(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_identity_fields::post_0
        # Verifies that the `_identity_fields` attribute of `AssertionNode` is set to
        # `('qualified_name',)`, ensuring that the model correctly identifies its unique
        # identity field for operations like lookups or deduplication.
        assert AssertionNode._identity_fields == ("qualified_name",)

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_phase
    # Verifies that the serialized output of an AssertionNode includes the correct phase
    # identifier, ensuring accurate reconstruction of test state from serialized data.
    def test_serialize_includes_phase(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_phase::step_0
        # Calls the serialize method on the AssertionNode fixture to produce a
        # JSON-serializable dictionary, setting up the actual output that will be
        # inspected by the subsequent assertions.
        node = AssertionNode(
            qualified_name="tests::test_update::test_single::post_0",
            phase="post",
            operator="==",
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_phase::post_0
        # Verifies that the serialized output includes the correct phase field ('post'),
        # ensuring that the phase attribute is accurately captured in the serialization
        # for downstream use.
        assert serialized["phase"] == "post"
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_phase::post_1
        # Verifies that the serialized output includes the correct operator field
        # ('=='), confirming that the serialization preserves the assertion's comparison
        # behavior.
        assert serialized["operator"] == "=="

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_type_discriminator
    # Verifies that the serialization of an AssertionNode includes a type discriminator,
    # ensuring correct deserialization and type identification in polymorphic scenarios.
    def test_serialize_includes_type_discriminator(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_type_discriminator::step_0
        # Sets up the test by creating the AssertionNode fixture, ensuring the
        # serialization method has the required object to operate on.
        node = AssertionNode(
            qualified_name="tests::test_update::test_single::post_0",
            phase="post",
        )
        serialized = node.serialize()
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_serialize_includes_type_discriminator::post_0
        # Verifies that the serialized output includes a 'type' field set to
        # 'AssertionNode', ensuring the type discriminator is correctly maintained for
        # reliable deserialization.
        assert serialized["type"] == "AssertionNode"

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase
    # Verifies the correct deserialization of an assertion node model when a phase is
    # provided, ensuring that the LayerGraph's deserialize method accurately
    # reconstructs stateful assertion configurations.
    def test_deserialize_with_phase(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase::step_0
        # Sets up the test by creating or providing serialized data for an
        # AssertionNode, preparing the input for the deserialize call.
        data = {
            "type": "AssertionNode",
            "qualified_name": "tests::test_update::test_single::post_0",
            "kind": "assertion",
            "phase": "post",
            "operator": "==",
            "order": 0,
            "description": "Result matches expected value.",
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase::post_0
        # Asserts that the deserialized object is an instance of AssertionNode, ensuring
        # the deserialize method returns the correct type and not a generic node.
        assert isinstance(node, AssertionNode)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase::post_1
        # Checks that another key attribute (e.g., target) is correctly set in the
        # deserialized node, confirming full fidelity of the deserialization process.
        assert node.phase == "post"
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase::post_2
        # Verifies that the deserialized node's phase attribute matches the expected
        # value, ensuring the phase is correctly restored during deserialization.
        assert node.operator == "=="
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_with_phase::post_3
        # Verifies that a final attribute (e.g., operator or value) is correctly
        # preserved after deserialization, completing the thorough check of the
        # deserialize method.
        assert node.order == 0

    def test_deserialize_computes_uid(self):
        """deserialize() computes deterministic uid from qualified_name."""
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_computes_uid::step_0
        # Sets up the test by performing the deserialize operation on the node to ensure
        # it has a computed uid before any assertions are made.
        qn = "tests::test_update::test_single::post_0"
        data = {
            "type": "AssertionNode",
            "qualified_name": qn,
            "source": "test",
            "kind": "assertion",
            "phase": "post",
        }
        node = CodeGraphNode.deserialize(data)
        expected_uid = compute_uid("test", qn)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_deserialize_computes_uid::post_0
        # Verifies that the node's uid after deserialization equals the expected uid,
        # confirming that the uid generation is deterministic and correct.
        assert node.uid == expected_uid

    def test_fixture_roundtrip(self):
        """Verify assertion_node_full.json deserializes correctly."""
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::step_0
        # Sets up the test by loading the 'assertion_node_full.json' fixture file and
        # deserializing it into an AssertionNode object using
        # codegraph.graph.LayerGraph.deserialize.
        with open(Path(__file__).resolve().parent / "data" / "assertion_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::post_0
        # Verifies that the deserialized object is an instance of AssertionNode,
        # confirming that the deserialization method correctly interprets the JSON
        # structure as the expected node type.
        assert isinstance(node, AssertionNode)
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::post_1
        # Verifies that the 'phase' field (e.g., 'post') of the deserialized node
        # matches the original data, ensuring the execution phase is preserved
        # correctly.
        assert node.phase == data["phase"]
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::post_2
        # Verifies that the 'operator' field of the deserialized node matches the
        # original data, ensuring the logical operator (e.g., '>') is preserved
        # accurately.
        assert node.operator == data["operator"]
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::post_3
        # Verifies that the 'order' field of the deserialized node matches the original
        # data, ensuring the positional order of assertions is preserved correctly
        # during deserialization.
        assert node.order == data["order"]
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeModel.test_fixture_roundtrip::post_4
        # Verifies that the 'qualified_name' field of the deserialized node matches the
        # original data, ensuring the unique identifier of the assertion is preserved
        # correctly.
        assert node.qualified_name == data["qualified_name"]

class TestAssertionNodeRegistry:
    """Test that AssertionNode is registered in CodeGraphNode._registry."""

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeRegistry.test_assertion_node_in_registry
    # Verifies that the assertion node is correctly stored in the registry, ensuring
    # node registration functions as expected for test correctness.
    def test_assertion_node_in_registry(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeRegistry.test_assertion_node_in_registry::post_0
        # Verifies that a registered assertion node appears in the registry's list of
        # nodes, ensuring the registration mechanism correctly stores and retrieves
        # assertion nodes.
        assert "AssertionNode" in CodeGraphNode._registry

    # codegraph:test-desc test.test_assertion_node.TestAssertionNodeRegistry.test_assertion_node_registry_class
    # This test verifies that the AssertionNodeRegistry class is correctly defined and
    # accessible, ensuring the test framework can properly register and manage assertion
    # nodes for consistent behavior validation.
    def test_assertion_node_registry_class(self):
        # codegraph:test-desc test.test_assertion_node.TestAssertionNodeRegistry.test_assertion_node_registry_class::post_0
        # Verifies that the AssertionNode class is correctly registered in
        # CodeGraphNode's registry under its own name, ensuring the registry mechanism
        # properly tracks node types for dynamic lookup.
        assert CodeGraphNode._registry["AssertionNode"] is AssertionNode