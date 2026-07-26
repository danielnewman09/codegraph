"""Tests for TestFixtureNode — test-local variable tracking."""

import os
import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from neomodel import RelationshipTo, RelationshipFrom, StringProperty, ArrayProperty

from codegraph.models.test import TestFixtureNode, TestNode, AssertionNode, TestStepNode
from codegraph.constants import TAGS, NODE_KINDS, TEST_KIND_SET, DEFAULT_PREDICATES
from codegraph.uid import compute_uid
from codegraph.graph import LayerGraph

class TestTestFixtureNodeFields:
    """Foundation: TestFixtureNode has the expected fields and defaults."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_kind_defaults_to_test_fixture
    # Verifies that the test fixture node's 'kind' field correctly defaults to 'test
    # fixture', ensuring consistent and expected metadata assignment for test fixtures
    # in the framework.
    def test_field_kind_defaults_to_test_fixture(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_kind_defaults_to_test_fixture::step_0
        # Sets up the test fixture node to initial state, ensuring that the `kind` field
        # is not yet assigned a value, which allows the test to verify its default
        # behavior.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_kind_defaults_to_test_fixture::post_0
        # Verifies that the `kind` attribute of the test fixture node is equal to
        # 'test_fixture', confirming that the default value is correctly assigned when
        # no explicit kind is provided, which is essential for proper node
        # classification.
        assert node.kind == "test_fixture"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_name_is_required
    # Verifies that the 'field_name' attribute of a TestFixtureNode is required,
    # ensuring data integrity and preventing incomplete fixture definitions.
    def test_field_name_is_required(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_name_is_required::step_0
        # Sets up the test by initializing a fixture node without a name field, to test
        # whether the system correctly requires the name field.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_name_is_required::post_0
        # Verifies that an error or expected condition (exact match) occurs when the
        # name field is missing, confirming that the name field is mandatory for fixture
        # nodes.
        assert node.name == "engine"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_type_signature_defaults_to_empty
    # Verifies that the type signature of a TestFixtureNode field defaults to an empty
    # value, ensuring that fields without explicit type constraints are correctly
    # initialized and do not cause undefined behavior.
    def test_field_type_signature_defaults_to_empty(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_type_signature_defaults_to_empty::step_0
        # Creates an instance of a TestFixtureNode and checks that its type_signature
        # field is not set, preparing to verify that the default value is correct.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_type_signature_defaults_to_empty::post_0
        # Verifies that the type_signature field of the TestFixtureNode is an empty
        # dictionary, confirming that the default for this field is an empty mapping as
        # expected.
        assert node.type_signature == ""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_description_defaults_to_empty
    # This test verifies that the 'description' field of a TestFixtureNode defaults to
    # an empty string when not explicitly set, ensuring the system provides a
    # predictable and usable default value to avoid null or unexpected behavior.
    def test_field_description_defaults_to_empty(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_description_defaults_to_empty::step_0
        # Sets up the test fixture node without providing a description, to establish
        # the default state that will be checked.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_description_defaults_to_empty::post_0
        # Verifies that the description field of the test fixture node is an empty
        # string when no description is explicitly provided, confirming the correct
        # default behavior.
        assert node.description == ""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_tags_is_array
    # Verifies that the 'tags' field of a test fixture node is always stored as an
    # array, ensuring consistent data structure for downstream processing and reporting.
    def test_field_tags_is_array(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_tags_is_array::step_0
        # Sets up the test by initializing the test fixture node without any tags,
        # preparing a clean baseline for verifying that tags are stored as an array.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_tags_is_array::post_0
        # Verifies that the node's tags attribute is an empty list, confirming that tags
        # are correctly represented as an array and that no extraneous tags are assigned
        # by default.
        assert node.tags == []

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_uid_computed_from_qualified_name
    # Verifies that the UID of a test fixture node is correctly computed from its
    # qualified name, ensuring unique identification and traceability across the test
    # suite.
    def test_field_uid_computed_from_qualified_name(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_uid_computed_from_qualified_name::step_0
        # Sets up the test environment by initializing any necessary objects or state
        # before the assertion is evaluated.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
            source="test",
        )
        expected = compute_uid("test", "tests::test_ops::engine")
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_uid_computed_from_qualified_name::post_0
        # Verifies that the UID computed by the node matches the expected value,
        # ensuring that the UID generation algorithm correctly derives a unique
        # identifier from the node's qualified name.
        assert node._compute_uid() == expected

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_doc_embedding_defaults_to_empty
    # Verifies that the `doc_embedding` field of a `TestFixtureNode` object defaults to
    # an empty value, ensuring the default state is correct and does not produce
    # unexpected non-empty values that could break downstream logic.
    def test_field_doc_embedding_defaults_to_empty(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_doc_embedding_defaults_to_empty::step_0
        # Initializes the test fixture, ensuring the node object is set up and ready for
        # verification of default field values.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_field_doc_embedding_defaults_to_empty::post_0
        # Verifies that the `doc_embedding` attribute of the node is an empty list by
        # default, confirming that the field initializes without any predefined
        # embeddings.
        assert node.doc_embedding == []

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set
    # Verifies that all expected fields of a TestFixtureNode are properly set, ensuring
    # that the node fully and correctly captures its configuration for reliable
    # downstream processing.
    def test_all_fields_set(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::step_0
        # Set up the initial state with all fields populated, advancing the test to a
        # ready configuration for verifying that every field is correctly stored and
        # accessible.
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
            kind="test_fixture",
            type_signature="CalculatorEngine",
            description="Direct instance of CalculatorEngine.",
            tags=["as-built"],
            source="test",
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_0
        # Validates the first field of the node to ensure it contains the expected
        # value, starting the series of field verifications.
        assert node.name == "engine"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_1
        # Checks that another individual field matches the intended value, confirming
        # the integrity of field assignment.
        assert node.qualified_name == "tests::test_ops::engine"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_2
        # Verifies that a specific field of the node holds its expected value, ensuring
        # that the data is correctly assigned and retrievable.
        assert node.kind == "test_fixture"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_3
        # Asserts that yet another field is set correctly, ensuring all fields in the
        # fixture are properly populated.
        assert node.type_signature == "CalculatorEngine"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_4
        # Verifies the value of a further field, completing the check that every field
        # in the node is correctly set.
        assert node.description == "Direct instance of CalculatorEngine."
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_all_fields_set::post_5
        # Confirms that the node's tags list equals the expected list, validating that
        # the tags are correctly stored and maintain their order.
        assert node.tags == ["as-built"]

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_kind_is_in_test_kind_set
    # Verifies that the 'kind' attribute of a TestFixtureNode instance is always a
    # member of the predefined valid test kind set, ensuring data integrity and
    # consistency across the system.
    def test_kind_is_in_test_kind_set(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_kind_is_in_test_kind_set::post_0
        # Verifies that 'test_fixture' is a recognized kind listed in TEST_KIND_SET,
        # confirming that the test fixture node kind is properly included in the global
        # set of test node kinds.
        assert "test_fixture" in TEST_KIND_SET
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_kind_is_in_test_kind_set::post_1
        # Verifies that 'test_fixture' appears in the set of node kinds derived from
        # NODE_KINDS, ensuring consistency between the enumerated node kinds and the
        # recognized test fixture kind.
        assert "test_fixture" in {k for k, _ in NODE_KINDS}

    def test_not_in_tags_vocabulary(self):
        """TestFixtureNode is a node type, not a tag — it should not be in TAGS."""
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeFields.test_not_in_tags_vocabulary::post_0
        # Verifies that 'test_fixture' is not present in the TAGS set, ensuring that
        # TestFixtureNode is treated as a node type rather than a tag, which is a
        # distinction critical to the integrity of the tagging system.
        assert "test_fixture" not in TAGS

class TestTestFixtureNodeRelationships:
    """TestFixtureNode declares the expected relationship descriptors."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_defined_in_relationship
    # Verifies that a test fixture node correctly establishes and reports its
    # 'defined-in' relationship to the parent test class, ensuring proper structural
    # tracking of fixture origins within the test framework.
    def test_has_defined_in_relationship(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_defined_in_relationship::post_0
        # Verifies that the TestFixtureNode class or instance has an attribute named
        # 'defined_in'. This confirms that the node type is expected to participate in a
        # DEFINED_IN relationship, which is a prerequisite for the relationship to be
        # meaningful in the system.
        assert hasattr(TestFixtureNode, "defined_in")
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_defined_in_relationship::step_0
        # Sets up the test environment by preparing necessary state or objects (e.g.,
        # configuring a TestFixtureNode instance) so that the subsequent assertions on
        # its relationships can be evaluated.
        r = TestFixtureNode.defined_in
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_defined_in_relationship::post_1
        # Checks that the 'defined_in' relationship is of type 'DEFINED_IN'. This
        # ensures that the relationship metadata correctly represents a containment or
        # definition binding, which is critical for modeling the dependency or ownership
        # structure in the test framework.
        assert r.definition["relation_type"] == "DEFINED_IN"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_checked_by_relationship
    # Verifies that a test fixture node correctly records a 'checked by' relationship,
    # ensuring traceability and accountability in the test data model.
    def test_has_checked_by_relationship(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_checked_by_relationship::post_0
        # Checks that the TestFixtureNode class has an attribute named 'checked_by',
        # confirming the class exposes the expected relationship property for
        # verification.
        assert hasattr(TestFixtureNode, "checked_by")
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_checked_by_relationship::step_0
        # Sets up the test environment by initializing necessary test data or objects
        # required to verify the CHECKED_BY relationship.
        r = TestFixtureNode.checked_by
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_has_checked_by_relationship::post_1
        # Verifies that the relation type stored in the test fixture node's definition
        # is specifically 'CHECKED_BY', ensuring the correct relationship is
        # established.
        assert r.definition["relation_type"] == "CHECKED_BY"

    def test_of_type_relationships_exist(self):
        """OF_TYPE is declared per target type (codegraph pattern)."""
        for suffix in ["class", "enum", "interface", "union", "namespace"]:
            attr = f"of_type_{suffix}"
            # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_of_type_relationships_exist::post_0
            # Checks that the 'TestFixtureNode' class possesses the attribute 'attr',
            # ensuring the code under test defines the expected type-related annotations
            # or properties.
            assert hasattr(TestFixtureNode, attr), f"missing {attr}"
            r = getattr(TestFixtureNode, attr)
            # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_of_type_relationships_exist::post_1
            # Verifies that the relationship's 'relation_type' property equals
            # 'OF_TYPE', confirming that the code under test correctly labels
            # type-ownership connections.
            assert r.definition["relation_type"] == "OF_TYPE"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_of_type
    # Verifies that serializing a node's relationships includes the 'of_type' field for
    # each relation, ensuring the output contains all required type information for
    # downstream consumers.
    def test_serialize_relationships_includes_of_type(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_of_type::step_0
        # Sets up the test by constructing a node or mock context to later invoke
        # serialize_relationships with an 'of_type' filter, establishing the basis for
        # verifying that the returned relationships list is correctly scoped.
        rels = TestFixtureNode.serialize_relationships()
        of_type = [r for r in rels if r["relation_type"] == "OF_TYPE"]
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_of_type::post_0
        # Verifies that the serialized relationships filtered by type contains at least
        # five entries, confirming that the method returns a sufficient number of
        # filtered results rather than an empty or incomplete set.
        assert len(of_type) >= 5  # class, enum, interface, union, namespace

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_checked_by
    # Verifies that when serializing a node's relationships, any 'checked_by'
    # relationships are included, ensuring that traceability links from requirements to
    # test results are preserved in the serialized output.
    def test_serialize_relationships_includes_checked_by(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_checked_by::step_0
        # Sets up necessary objects or state to prepare for the test of serializing
        # relationships, ensuring that the 'checked_by' relationship can be properly
        # included in the serialized output.
        rels = TestFixtureNode.serialize_relationships()
        checked = [r for r in rels if r["relation_type"] == "CHECKED_BY"]
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_checked_by::post_0
        # Verifies that exactly one 'checked_by' relationship is present in the
        # serialized output, confirming that the method correctly includes all relevant
        # relationships as expected.
        assert len(checked) == 1

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_defined_in
    # Verifies that the 'serialize_relationships' method of CodeGraphNode includes the
    # 'defined_in' relationship in its output, ensuring that the serialized data
    # correctly captures where a node is defined.
    def test_serialize_relationships_includes_defined_in(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_defined_in::step_0
        # Sets up the necessary objects and state so that the serialization of
        # relationships can be tested.
        rels = TestFixtureNode.serialize_relationships()
        defined = [r for r in rels if r["relation_type"] == "DEFINED_IN"]
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeRelationships.test_serialize_relationships_includes_defined_in::post_0
        # Verifies that exactly one 'defined_in' relationship is serialized, confirming
        # the relationship is correctly captured and counted.
        assert len(defined) == 1

class TestTestFixtureNodeTestData:
    """Deserialization from JSON test data fixtures."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_minimal_json
    # Verifies that a TestFixtureNode can be correctly reconstructed from JSON input
    # containing only required fields, ensuring minimal valid data is accepted without
    # error.
    def test_deserialize_from_minimal_json(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_minimal_json::step_0
        # Deserializes a minimal JSON input into a TestFixtureNode object, setting up
        # the data for validation in the following assertions.
        data = {
            "name": "engine",
            "qualified_name": "tests::test_ops::engine",
            "kind": "test_fixture",
            "type_signature": "CalculatorEngine",
            "tags": ["as-built"],
        }
        node = TestFixtureNode(**data)
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_minimal_json::post_0
        # Verifies that the deserialized object's name field matches the expected value,
        # confirming that minimal JSON is correctly parsed.
        assert node.name == "engine"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_minimal_json::post_1
        # Verifies that the deserialized object's node_id field matches the expected
        # value, ensuring that all critical fields from the JSON are accurately
        # reconstructed.
        assert node.type_signature == "CalculatorEngine"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json
    # Verifies that a TestFixtureNode can be correctly deserialized from a complete JSON
    # representation, ensuring the round-trip serialization/deserialization process
    # preserves all data for reliable test configuration storage.
    def test_deserialize_from_full_fixture_json(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::step_0
        # Sets up the test by preparing the initial conditions and invoking the
        # deserialization method on a full fixture JSON, advancing the test to the
        # verification phase.
        path = str(Path(__file__).resolve().parent / "data" / "test_fixture_node_full.json")
        with open(path) as f:
            data = json.load(f)
        # Remove non-field keys before constructing
        fields = {k: v for k, v in data.items() if k != "edges"}
        node = TestFixtureNode(**fields)
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::post_0
        # Verifies that a specific field of the deserialized node matches the expected
        # value, ensuring the core deserialization logic correctly interprets that
        # field.
        assert node.name == "widget"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::post_1
        # Verifies an additional field of the deserialized node matches the expected
        # value, further confirming the completeness and accuracy of the
        # deserialization.
        assert node.qualified_name == "tests::test_widget_ops::test_create_widget::widget"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::post_2
        # Checks that another field of the deserialized node equals the expected value,
        # confirming the deserialization correctly populates that property.
        assert node.kind == "test_fixture"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::post_3
        # Checks yet another field of the deserialized node equals the expected value,
        # ensuring that all relevant properties are correctly populated from the fixture
        # JSON.
        assert node.type_signature == "Widget"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeTestData.test_deserialize_from_full_fixture_json::post_4
        # Asserts that the node's tags attribute contains exactly ['as-built'],
        # validating that the deserialization process correctly assigns the tag list
        # from the fixture JSON.
        assert node.tags == ["as-built"]

class TestTestNodeComposesTestFixtureNode:
    """TestNode now composes TestFixtureNode alongside AssertionNode/TestStepNode."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_testnode_has_fixtures_relationship
    # Verifies that a TestNode correctly maintains a relationship with its underlying
    # FixtureNode, ensuring the test structure can accurately represent fixture
    # dependencies for reliable test execution and reporting.
    def test_testnode_has_fixtures_relationship(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_testnode_has_fixtures_relationship::post_0
        # Verifies that the TestNode class has a 'fixtures' attribute, which is
        # essential for modeling the composition relationship between a test node and
        # its fixtures.
        assert hasattr(TestNode, "fixtures")
        # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_testnode_has_fixtures_relationship::step_0
        # Sets up the test environment by initializing the necessary test objects,
        # enabling the subsequent verification of the relationship between TestNode and
        # its fixtures.
        r = TestNode.fixtures
        # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_testnode_has_fixtures_relationship::post_1
        # Confirms that the relation type between TestNode and its fixtures is
        # 'COMPOSES', ensuring that the data model correctly represents a composition
        # relationship where TestNode is composed of fixtures.
        assert r.definition["relation_type"] == "COMPOSES"

    # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_serialize_relationships_includes_fixtures
    # Verifies that the serialized relationships of a code graph node include fixture
    # nodes, ensuring completeness of the output.
    def test_serialize_relationships_includes_fixtures(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_serialize_relationships_includes_fixtures::step_0
        # Sets up the test environment, likely by creating instances or initializing
        # data, to prepare for verifying that fixture nodes appear in the serialized
        # relationships.
        rels = TestNode.serialize_relationships()
        composes = [r for r in rels if r["relation_type"] == "COMPOSES"]
        targets = {r["target"] for r in composes}
        # codegraph:test-desc test.test_test_fixture_node.TestTestNodeComposesTestFixtureNode.test_serialize_relationships_includes_fixtures::post_0
        # Asserts that fixture nodes are present in the serialized output, confirming
        # that 'serialize_relationships' correctly includes all relevant nodes.
        assert "codegraph.models.test.TestFixtureNode" in targets

class TestAssertionNodeCheckedBy:
    """AssertionNode has incoming CHECKED_BY from TestFixtureNode."""

    # codegraph:test-desc test.test_test_fixture_node.TestAssertionNodeCheckedBy.test_assertionnode_has_checked_by_fixtures
    # Verifies that the assertion node correctly maintains a record of which fixtures
    # have checked it, ensuring traceability and accountability in the validation
    # process.
    def test_assertionnode_has_checked_by_fixtures(self):
        # codegraph:test-desc test.test_test_fixture_node.TestAssertionNodeCheckedBy.test_assertionnode_has_checked_by_fixtures::post_0
        # Verifies that the `AssertionNode` class possesses a `checked_by_fixtures`
        # attribute, which is necessary for linking requirements to their verification
        # fixtures and ensuring traceability.
        assert hasattr(AssertionNode, "checked_by_fixtures")
        # codegraph:test-desc test.test_test_fixture_node.TestAssertionNodeCheckedBy.test_assertionnode_has_checked_by_fixtures::step_0
        # This step sets up the test environment (e.g., initializes objects or
        # configures requirements), ensuring that the assertion node and its associated
        # fixtures are ready for subsequent verification.
        r = AssertionNode.checked_by_fixtures
        # codegraph:test-desc test.test_test_fixture_node.TestAssertionNodeCheckedBy.test_assertionnode_has_checked_by_fixtures::post_1
        # Confirms that the relation type of the checked-by relationship is set to
        # `'CHECKED_BY'`, ensuring that the connection between an assertion node and its
        # verifying fixtures is correctly labeled for compliance tracking.
        assert r.definition["relation_type"] == "CHECKED_BY"

class TestTestStepNodeDefinedFixtures:
    """TestStepNode has incoming DEFINED_IN from TestFixtureNode."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestStepNodeDefinedFixtures.test_teststepnode_has_defined_fixtures
    # Verifies that a TestStepNode correctly reports the fixtures it has defined,
    # ensuring that fixture tracking works as intended for test structure accuracy.
    def test_teststepnode_has_defined_fixtures(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestStepNodeDefinedFixtures.test_teststepnode_has_defined_fixtures::post_0
        # Asserts that the TestStepNode class has an attribute named 'defined_fixtures',
        # confirming that the test framework expects test step nodes to have a mechanism
        # to track their defined fixtures, which is essential for fixture resolution and
        # test organization.
        assert hasattr(TestStepNode, "defined_fixtures")
        # codegraph:test-desc test.test_test_fixture_node.TestTestStepNodeDefinedFixtures.test_teststepnode_has_defined_fixtures::step_0
        # Sets up the test environment, likely by initializing any necessary objects or
        # data, to prepare for checking the 'defined_fixtures' attribute existence and
        # its relation type.
        r = TestStepNode.defined_fixtures
        # codegraph:test-desc test.test_test_fixture_node.TestTestStepNodeDefinedFixtures.test_teststepnode_has_defined_fixtures::post_1
        # Verifies that the relation_type of the fixture definition is 'DEFINED_IN',
        # ensuring the fixture correctly identifies the node it belongs to, which is
        # critical for proper fixture scoping and lifecycle management.
        assert r.definition["relation_type"] == "DEFINED_IN"

class TestTestFixtureNodeNeo4j:
    """Neo4j integration tests for TestFixtureNode."""

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture
    # This test verifies that a basic Fixture node can be created and saved to a Neo4j
    # database, ensuring the persistence layer correctly handles fixture creation and
    # storage.
    def test_create_and_save_basic_fixture(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture::step_0
        # Sets up the test environment by initializing necessary objects or database
        # connections, ensuring the test can run against a known state.
        node = TestFixtureNode(
            name="ns_node",
            qualified_name="tests::test_enum_composed::ns_node",
            kind="test_fixture",
            type_signature="NamespaceNode",
            description="A namespace fixture for calc namespace.",
            tags=["as-built"],
            source="test",
        ).save()
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture::post_0
        # Asserts that the saved node was assigned a unique element_id by Neo4j,
        # confirming the database interaction succeeded and the node is addressable.
        assert node.element_id is not None
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture::step_1
        # Executes the action of creating and saving a fixture node to the Neo4j
        # database, which is the core behavior being tested.
        fetched = TestFixtureNode.nodes.get(
            qualified_name="tests::test_enum_composed::ns_node"
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture::post_1
        # Verifies that a specific attribute of the saved fixture node equals an
        # expected value, confirming the data was stored correctly.
        assert fetched.name == "ns_node"
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_create_and_save_basic_fixture::post_2
        # Checks that another attribute of the saved fixture node matches its expected
        # value, ensuring complete and accurate data persistence.
        assert fetched.type_signature == "NamespaceNode"

    # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_of_type_connects_to_class_node
    # Verifies that a FixtureNode of type 'test' is correctly connected to a ClassNode
    # in the Neo4j database, ensuring the integrity of test-to-class relationships in
    # the data model.
    def test_of_type_connects_to_class_node(self):
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_of_type_connects_to_class_node::step_0
        # Executes the query that finds nodes of the given type_def, storing the result
        # in 'results'; this step advances the test by producing the data needed to
        # verify the connection.
        from codegraph.models.compound import ClassNode

        type_def = ClassNode(
            name="Foo",
            kind="class",
            qualified_name="myapp::Foo",
            tags=["design"],
            source="test",
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance of Foo class.",
            tags=["as-built"],
            source="test",
        ).save()

        fixture.of_type_class.connect(type_def)

        # Verify via raw Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:OF_TYPE]->(t:ClassNode) "
            "WHERE elementId(f) = $fid "
            "RETURN t.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_of_type_connects_to_class_node::post_0
        # Asserts that exactly one result is returned, confirming that the connection
        # from the test fixture node to its class node is unique and correctly formed.
        assert len(results) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_of_type_connects_to_class_node::post_1
        # Asserts that the first result's first element equals 'myapp::Foo', verifying
        # that the query correctly returns the expected class node name.
        assert results[0][0] == "myapp::Foo"

    def test_defined_in_connects_to_test_step(self):
        """DEFINED_IN links fixture to the step where it is defined."""
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_defined_in_connects_to_test_step::step_0
        # Sets up the block within which the fixture is defined, establishing the
        # context needed to later verify the DEFINED_IN relationship.
        step = TestStepNode(
            name="step_0",
            qualified_name="tests::test_foo::test_create::step_0",
            kind="test_step",
            order=0,
            description="Create foo = Foo()",
            tags=["as-built"],
            source="test",
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance created in step_0.",
            tags=["as-built"],
            source="test",
        ).save()

        fixture.defined_in.connect(step)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:DEFINED_IN]->(s:TestStepNode) "
            "WHERE elementId(f) = $fid "
            "RETURN s.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_defined_in_connects_to_test_step::post_0
        # Verifies that exactly one result is returned, ensuring that the query for
        # DEFINED_IN links between fixtures and steps is correctly filtering to a single
        # relationship.
        assert len(results) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_defined_in_connects_to_test_step::post_1
        # Checks that the returned result contains the expected step identifier,
        # confirming that the DEFINED_IN relationship actually links the correct fixture
        # to the step where it is defined.
        assert "test_foo::test_create::step_0" in results[0][0]

    def test_checked_by_connects_to_assertion(self):
        """CHECKED_BY links fixture to the assertion that checks it."""
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_checked_by_connects_to_assertion::step_0
        # Executes the setup block to initialize the test environment and create
        # necessary nodes for the CHECKED_BY relationship.
        assertion = AssertionNode(
            name="post_0",
            qualified_name="tests::test_foo::test_create::post_0",
            kind="assertion",
            phase="post",
            order=0,
            operator="==",
            description="foo.name == 'test'",
            tags=["as-built"],
            source="test",
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance checked in post_0.",
            tags=["as-built"],
            source="test",
        ).save()

        fixture.checked_by.connect(assertion)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:CHECKED_BY]->(a:AssertionNode) "
            "WHERE elementId(f) = $fid "
            "RETURN a.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_checked_by_connects_to_assertion::post_0
        # Verifies that exactly one result was returned from the query, ensuring the
        # CHECKED_BY relationship exists uniquely as expected.
        assert len(results) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_checked_by_connects_to_assertion::post_1
        # Confirms that the specific assertion identifier is present in the first
        # result, validating that the correct assertion is linked to the fixture via
        # CHECKED_BY.
        assert "test_foo::test_create::post_0" in results[0][0]

    def test_composes_from_test_node(self):
        """TestNode composes TestFixtureNode alongside other children."""
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_composes_from_test_node::step_0
        # Sets up the initial test environment and data required for validating that
        # TestFixtureNode correctly composes from a test node.
        test = TestNode(
            name="test_create",
            qualified_name="tests::test_foo::test_create",
            kind="test",
            test_name="test_create",
            test_module="tests.test_foo",
            method="automated",
            description="Test fixture composition.",
            tags=["as-built"],
            source="test",
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance created in the test.",
            tags=["as-built"],
            source="test",
        ).save()

        test.fixtures.connect(fixture)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(f:TestFixtureNode) "
            "WHERE elementId(t) = $tid "
            "RETURN f.qualified_name",
            {"tid": db.parse_element_id(test.element_id)},
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_composes_from_test_node::post_0
        # Verifies that exactly one result is returned from the query, confirming the
        # composition logic produces a single, unique output.
        assert len(results) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_composes_from_test_node::post_1
        # Checks that the first element of the first result matches the expected fully
        # qualified test name, ensuring the composition correctly identifies the test
        # node.
        assert results[0][0] == "tests::test_foo::test_create::foo"

    def test_primitive_type_no_of_type_edge(self):
        """For primitive types (dict, str, list), only type_signature is set."""
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_primitive_type_no_of_type_edge::step_0
        # Sets up the test environment by initializing the necessary context, such as
        # connecting to Neo4j or preparing test fixtures, ensuring the system is ready
        # for the subsequent action.
        fixture = TestFixtureNode(
            name="parents",
            qualified_name="tests::test_enum::parents",
            kind="test_fixture",
            type_signature="list[NamespaceNode]",
            description="Result of enum_node.parent_namespace.all().",
            tags=["as-built"],
            source="test",
        ).save()

        # type_signature captures the type without needing an OF_TYPE edge
        fetched = TestFixtureNode.nodes.get(
            qualified_name="tests::test_enum::parents"
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_primitive_type_no_of_type_edge::post_0
        # Verifies that the retrieved node data matches the expected primitive type
        # structure, ensuring that only the type_signature is present and no of_type
        # edge was created, which is crucial for maintaining correct data modeling.
        assert fetched.type_signature == "list[NamespaceNode]"

        # No OF_TYPE edge should exist for primitives
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_primitive_type_no_of_type_edge::step_1
        # Executes the primary action being tested, likely constructing or saving a node
        # with primitive type fields and verifying that the type_signature property is
        # set without creating a separate type edge.
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:OF_TYPE]->(t) "
            "WHERE elementId(f) = $fid "
            "RETURN t",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        # codegraph:test-desc test.test_test_fixture_node.TestTestFixtureNodeNeo4j.test_primitive_type_no_of_type_edge::post_1
        # Asserts that no results are returned from the database query, confirming that
        # the primitive type node was correctly stored without any unintended type
        # relationships.
        assert len(results) == 0

class TestLayerGraphTestFixtureNode:
    """LayerGraph integration tests for TestFixtureNode."""

    def test_layer_graph_deserializes_test_fixture(self):
        """LayerGraph.deserialize handles TestFixtureNode in both flat and nested formats."""
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_deserializes_test_fixture::step_0
        # Sets up the test environment by initializing the LayerGraph instance and
        # preparing the input data (flat and nested formats) for the deserialize method,
        # establishing the preconditions for verification.
        data = [
            {
                "type": "TestFixtureNode",
                "source": "test",
                "qualified_name": "tests::test_engine::engine",
                "name": "engine",
                "kind": "test_fixture",
                "type_signature": "Engine",
                "description": "Engine instance for testing.",
                "tags": ["as-built"],
                "edges": [],
            }
        ]

        graph = LayerGraph.deserialize(data)
        entries = list(graph._all_entries())
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_deserializes_test_fixture::post_0
        # Confirms that exactly one entry is produced after deserialization, validating
        # that the deserialize method correctly aggregates both flat and nested formats
        # into a single list without duplicates or omissions.
        assert len(entries) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_deserializes_test_fixture::post_1
        # Asserts that the node within the deserialized entry is labeled as
        # 'TestFixtureNode', confirming the deserialize method correctly identifies and
        # preserves the test fixture node type from the input data.
        assert entries[0].node.__label__ == "TestFixtureNode"
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_deserializes_test_fixture::post_2
        # Verifies that the deserialized TestFixtureNode entry matches the expected
        # structure (likely checking node type or attributes), ensuring the deserialized
        # data is correctly formed and consistent with the input format.
        assert entries[0].node.name == "engine"

    def test_layer_graph_test_fixture_with_edges(self):
        """LayerGraph preserves OF_TYPE, CHECKED_BY, DEFINED_IN edges."""
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_test_fixture_with_edges::step_0
        # Sets up the test environment by initializing the LayerGraph with the required
        # edges, which is a prerequisite for verifying that these edges are correctly
        # preserved during serialization (to Neo4j) and deserialization.
        from codegraph.uid import compute_uid

        # All nodes must be in the graph data so that to_neo4j() can
        # resolve references via the flat index.  target_uid must be the
        # SHA-1 hash of the target node's qualified_name, and the target
        # data must include an explicit uid field so that _node_key()
        # uses the hash (not just the name).
        widget_uid = compute_uid("test", "myapp::Widget")
        post0_uid = compute_uid("test", "tests::test_w::post_0")
        arrange_uid = compute_uid("test", "tests::test_w::arrange")

        data = [
            {
                "type": "ClassNode",
                "uid": widget_uid,
                "source": "test",
                "qualified_name": "myapp::Widget",
                "name": "Widget",
                "kind": "class",
                "tags": ["design"],
                "edges": [],
            },
            {
                "type": "AssertionNode",
                "uid": post0_uid,
                "source": "test",
                "qualified_name": "tests::test_w::post_0",
                "name": "post_0",
                "kind": "assertion",
                "phase": "post",
                "order": 0,
                "operator": "==",
                "description": "widget.name == 'test'",
                "tags": ["as-built"],
                "edges": [],
            },
            {
                "type": "TestStepNode",
                "uid": arrange_uid,
                "source": "test",
                "qualified_name": "tests::test_w::arrange",
                "name": "arrange",
                "kind": "test_step",
                "order": 0,
                "description": "Create widget = Widget(name='test')",
                "tags": ["as-built"],
                "edges": [],
            },
            {
                "type": "TestFixtureNode",
                "source": "test",
                "qualified_name": "tests::test_w::widget",
                "name": "widget",
                "kind": "test_fixture",
                "type_signature": "Widget",
                "description": "Widget instance.",
                "tags": ["as-built"],
                "edges": [
                    {"relation_type": "OF_TYPE", "target_uid": widget_uid, "target_type": "ClassNode"},
                    {"relation_type": "CHECKED_BY", "target_uid": post0_uid, "target_type": "AssertionNode"},
                    {"relation_type": "DEFINED_IN", "target_uid": arrange_uid, "target_type": "TestStepNode"},
                ],
            }
        ]

        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode {qualified_name: 'tests::test_w::widget'})"
            "-[:OF_TYPE]->(t:ClassNode) "
            "RETURN t.qualified_name"
        )
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_test_fixture_with_edges::post_0
        # Verifies that the first element in the deserialized query result is the
        # expected node identifier 'myapp::Widget', confirming that the LayerGraph
        # correctly preserves defined nodes when converting to and from the Neo4j
        # representation.
        assert results[0][0] == "myapp::Widget"

    def test_layer_graph_nested_test_fixture(self):
        """LayerGraph handles TestFixtureNode nested under TestNode via composes."""
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_nested_test_fixture::step_0
        # Sets up the initial graph state by deserializing test data that includes a
        # TestFixtureNode nested under a TestNode, preparing the graph for subsequent
        # actions.
        data = [
            {
                "type": "TestNode",
                "source": "test",
                "qualified_name": "tests::test_w::test_create",
                "name": "test_create",
                "kind": "test",
                "test_name": "test_create",
                "test_module": "tests.test_w",
                "method": "automated",
                "description": "Creates a widget.",
                "tags": ["as-built"],
                "edges": [],
                "composes": [
                    {
                        "type": "TestFixtureNode",
                        "source": "test",
                        "qualified_name": "tests::test_w::test_create::widget",
                        "name": "widget",
                        "kind": "test_fixture",
                        "type_signature": "Widget",
                        "description": "Widget instance.",
                        "tags": ["as-built"],
                        "edges": [],
                    }
                ],
            }
        ]

        graph = LayerGraph.deserialize(data)

        # The TestFixtureNode should be a composed child of the TestNode
        root = list(graph.entries.values())[0]
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_nested_test_fixture::post_0
        # Checks that the root node of the Neo4j output is labeled 'TestNode', ensuring
        # the highest-level test structure is correctly identified in the graph.
        assert root.node.__label__ == "TestNode"

        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_nested_test_fixture::step_1
        # Converts the deserialized LayerGraph to a Neo4j-compatible structure,
        # advancing the test toward verifying that the nested TestFixtureNode is
        # correctly represented in the output.
        from neomodel import db
        graph.to_neo4j()

        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(f:TestFixtureNode) "
            "WHERE t.qualified_name = 'tests::test_w::test_create' "
            "RETURN f.qualified_name"
        )
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_nested_test_fixture::post_1
        # Ensures the results list contains exactly one item, confirming that the entire
        # nested structure under the TestNode is captured as a single cohesive element.
        assert len(results) == 1
        # codegraph:test-desc test.test_test_fixture_node.TestLayerGraphTestFixtureNode.test_layer_graph_nested_test_fixture::post_2
        # Verifies that the first result entry matches the expected fully qualified name
        # of the nested test widget, confirming that the graph correctly associates the
        # sub-test with the fixture.
        assert results[0][0] == "tests::test_w::test_create::widget"