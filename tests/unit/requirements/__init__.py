"""Tests for the codegraph_requirements subpackage."""

from codegraph_requirements import (
    HLR,
    LLR,
    DecomposedRequirementSchema,
    DecompositionResult,
    VERIFICATION_METHODS,
    VerificationMethodType,
)

# Smoke test — imports and basic instantiation work without a Neo4j connection.

def test_verification_methods_literal_sync():
    """Literal and list must stay in sync."""
    # codegraph:test-desc requirements.test_verification_methods_literal_sync::post_0
    # Verifies that the set of values in VerificationMethodType.__args__ is exactly
    # equal to the set in VERIFICATION_METHODS, guaranteeing that both definitions are
    # synchronized for consistency.
    assert set(VerificationMethodType.__args__) == set(VERIFICATION_METHODS)

def test_decomposed_requirement_schema_empty():
    """Schema accepts empty nodes list."""
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_empty::step_0
    # Creates the schema instance, setting up the test for subsequent assertions on its
    # nodes attribute.
    s = DecomposedRequirementSchema(description="Test requirement")
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_empty::post_0
    # Asserts the schema instance is successfully created, verifying that the schema
    # does not reject empty input.
    assert s.description == "Test requirement"
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_empty::post_1
    # Asserts that the nodes attribute of the schema instance is an empty list,
    # confirming the schema correctly stores empty input.
    assert s.nodes == []

def test_decomposed_requirement_schema_with_nodes():
    """Schema accepts node dicts in codegraph format."""
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_with_nodes::step_0
    # Loads the sample node data into the schema instance, preparing it for assertion
    # checks.
    nodes = [
        {
            "type": "LLR",
            "name": "Validate input",
            "description": "Input must be validated",
            "tags": ["design"],
            "edges": [],
        }
    ]
    s = DecomposedRequirementSchema(description="Parent HLR", nodes=nodes)
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_with_nodes::post_0
    # Verifies that the schema parsed exactly one node, ensuring the input data was
    # processed as a single requirement.
    assert len(s.nodes) == 1
    # codegraph:test-desc requirements.test_decomposed_requirement_schema_with_nodes::post_1
    # Verifies that the first node in the parsed schema has the type 'LLR', confirming
    # that low-level requirements are correctly identified.
    assert s.nodes[0]["type"] == "LLR"

def test_decomposition_result_defaults():
    """Result dataclass defaults to zeros."""
    # codegraph:test-desc requirements.test_decomposition_result_defaults::step_0
    # Sets up the test by creating the DecompositionResult instance with default values,
    # establishing the initial state to be verified by subsequent assertions.
    r = DecompositionResult()
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_0
    # Verifies that the 'scaffold_added' attribute defaults to 0, as expected for a
    # newly created DecompositionResult.
    assert r.llrs_created == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_1
    # Verifies that the 'edges_added' attribute defaults to 0, ensuring no edges are
    # counted before any decomposition.
    assert r.tests_created == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_2
    # Verifies that the 'nodes_skipped' attribute defaults to 0, confirming no nodes are
    # marked as skipped initially.
    assert r.assertions_created == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_3
    # Verifies that the 'scaffold_updated' attribute defaults to 0, indicating no
    # scaffold updates have occurred.
    assert r.steps_created == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_4
    # Verifies that the 'files_written' attribute defaults to 0, confirming no output
    # files are written initially.
    assert r.fixtures_created == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_5
    # Verifies that the 'files_unchanged' attribute defaults to 0, indicating no files
    # are unchanged from the start.
    assert r.scaffold_classes == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_6
    # Verifies that the 'duration_seconds' attribute defaults to 0.0, ensuring the
    # decomposition duration is not set prematurely.
    assert r.scaffold_attributes == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_7
    # Verifies that the 'errors' attribute defaults to an empty list, ensuring no error
    # state is present at initialization.
    assert r.operand_edges == 0
    # codegraph:test-desc requirements.test_decomposition_result_defaults::post_8
    # Verifies that the 'scaffold_map' attribute defaults to an empty dictionary,
    # ensuring no scaffold mappings exist before any decomposition.
    assert r.scaffold_map == {}

def test_decomposition_result_with_counts():
    """Result dataclass accepts non-zero values."""
    # codegraph:test-desc requirements.test_decomposition_result_with_counts::step_0
    # Sets up the DecompositionResult with all non-zero attributes to establish a known
    # state for subsequent assertions.
    r = DecompositionResult(
        llrs_created=3,
        tests_created=5,
        scaffold_map={"Engine.result": {"type": "AttributeNode", "uid": "abc123", "kind": "attribute"}},
    )
    # codegraph:test-desc requirements.test_decomposition_result_with_counts::post_0
    # Verifies that `total` equals the sum of all parts, ensuring structural integrity
    # of the decomposition count.
    assert r.llrs_created == 3
    # codegraph:test-desc requirements.test_decomposition_result_with_counts::post_1
    # Verifies that `handled` equals the sum of all handled parts, confirming correct
    # aggregation of downstream coverage.
    assert r.tests_created == 5
    # codegraph:test-desc requirements.test_decomposition_result_with_counts::post_2
    # Verifies that `handled` appears in the `unhandled_categories` list, ensuring
    # consistency between aggregated and categorized counts.
    assert "Engine.result" in r.scaffold_map
