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
    assert set(VerificationMethodType.__args__) == set(VERIFICATION_METHODS)

def test_decomposed_requirement_schema_empty():
    """Schema accepts empty nodes list."""
    s = DecomposedRequirementSchema(description="Test requirement")
    assert s.description == "Test requirement"
    assert s.nodes == []

def test_decomposed_requirement_schema_with_nodes():
    """Schema accepts node dicts in codegraph format."""
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
    assert len(s.nodes) == 1
    assert s.nodes[0]["type"] == "LLR"

def test_decomposition_result_defaults():
    """Result dataclass defaults to zeros."""
    r = DecompositionResult()
    assert r.llrs_created == 0
    assert r.tests_created == 0
    assert r.assertions_created == 0
    assert r.steps_created == 0
    assert r.fixtures_created == 0
    assert r.scaffold_classes == 0
    assert r.scaffold_attributes == 0
    assert r.operand_edges == 0
    assert r.scaffold_map == {}

def test_decomposition_result_with_counts():
    """Result dataclass accepts non-zero values."""
    r = DecompositionResult(
        llrs_created=3,
        tests_created=5,
        scaffold_map={"Engine.result": {"type": "AttributeNode", "uid": "abc123", "kind": "attribute"}},
    )
    assert r.llrs_created == 3
    assert r.tests_created == 5
    assert "Engine.result" in r.scaffold_map
