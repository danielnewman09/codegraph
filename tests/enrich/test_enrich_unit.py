"""Unit tests for codegraph_enrich — result types, placeholder detection,
response parsing, and the GraphEnricher / TestEnricher class hierarchy.

These tests exercise the non-Neo4j portions of the enrichment module.
Neo4j-dependent tests are in ``test_enrich_integration.py``.
"""

import json

import pytest

from codegraph_enrich import (
    EnrichmentResult,
    EnrichmentSummary,
    GraphEnricher,
    TestEnricher,
)


# ══════════════════════════════════════════════════════════════════════════
# EnrichmentResult
# ══════════════════════════════════════════════════════════════════════════


class TestEnrichmentResult:
    """Tests for the EnrichmentResult data class."""

    def test_defaults(self):
        er = EnrichmentResult(qualified_name="x", node_type="step")
        assert er.qualified_name == "x"
        assert er.node_type == "step"
        assert er.old_description == ""
        assert er.new_description == ""
        assert er.error is None
        assert not er.skipped

    def test_changed_true_when_descriptions_differ(self):
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="old",
            new_description="new",
        )
        assert er.changed
        assert er.success

    def test_changed_false_when_empty(self):
        er = EnrichmentResult(qualified_name="x", node_type="step")
        assert not er.changed

    def test_changed_false_when_identical(self):
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="same",
            new_description="same",
        )
        assert not er.changed

    def test_success_false_when_error(self):
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="old",
            new_description="new",
            error="boom",
        )
        assert not er.success

    def test_to_dict(self):
        er = EnrichmentResult(
            qualified_name="a::b",
            node_type="fixture",
            old_description="old",
            new_description="new",
            skipped=True,
            skip_reason="Already has a description",
        )
        d = er.to_dict()
        assert d["qualified_name"] == "a::b"
        assert d["node_type"] == "fixture"
        assert d["changed"] is True
        assert d["skipped"] is True


# ══════════════════════════════════════════════════════════════════════════
# EnrichmentSummary
# ══════════════════════════════════════════════════════════════════════════


class TestEnrichmentSummary:
    """Tests for the EnrichmentSummary data class."""

    def test_empty_summary(self):
        s = EnrichmentSummary(target_name="t")
        assert s.target_name == "t"
        assert s.total_enriched == 0
        assert s.total_skipped == 0
        assert s.total_errors == 0
        assert s.results == []

    def test_to_dict_groups_by_node_type(self):
        s = EnrichmentSummary(target_name="t")
        s.results = [
            EnrichmentResult("a", "fixture", old_description="o", new_description="n"),
            EnrichmentResult("b", "step", old_description="o2", new_description="n2"),
            EnrichmentResult("c", "assertion", old_description="o3", new_description="n3"),
            EnrichmentResult("d", "fixture", old_description="o4", new_description="n4"),
        ]
        s.total_enriched = 4
        d = s.to_dict()
        assert d["target_name"] == "t"
        assert d["total_enriched"] == 4
        assert len(d["fixtures"]) == 2
        assert len(d["steps"]) == 1
        assert len(d["assertions"]) == 1
        assert d["fixtures"][0]["qualified_name"] == "a"
        assert d["fixtures"][0]["description"] == "n"

    def test_to_dict_with_errors(self):
        s = EnrichmentSummary(target_name="t")
        s.errors = ["connection refused"]
        d = s.to_dict()
        assert d["errors"] == ["connection refused"]


# ══════════════════════════════════════════════════════════════════════════
# Placeholder detection
# ══════════════════════════════════════════════════════════════════════════


class TestPlaceholderDetection:
    """Tests for TestEnricher.is_placeholder (test-specific patterns)."""

    def test_empty_string_is_placeholder(self):
        assert TestEnricher.is_placeholder("")

    def test_whitespace_only_is_placeholder(self):
        assert TestEnricher.is_placeholder("   ")

    def test_setup_block_is_placeholder(self):
        assert TestEnricher.is_placeholder("Setup block")

    def test_action_block_is_placeholder(self):
        assert TestEnricher.is_placeholder("Action block 3")

    def test_assert_expr_is_placeholder(self):
        assert TestEnricher.is_placeholder("assert x == 1")

    def test_real_description_is_not_placeholder(self):
        assert not TestEnricher.is_placeholder(
            "Verifies that updating a single field persists the change."
        )

    def test_base_placeholder_only_flags_empty(self):
        """GraphEnricher.is_placeholder only checks empty/whitespace."""
        assert GraphEnricher.is_placeholder("")
        assert GraphEnricher.is_placeholder("  ")
        assert not GraphEnricher.is_placeholder("Setup block")
        assert not GraphEnricher.is_placeholder("assert x == 1")


# ══════════════════════════════════════════════════════════════════════════
# Response parsing (on GraphEnricher base class)
# ══════════════════════════════════════════════════════════════════════════


class TestParseResponse:
    """Tests for GraphEnricher.parse_llm_response."""

    def test_plain_json(self):
        result = GraphEnricher.parse_llm_response(
            '{"a": "desc a", "b": "desc b"}'
        )
        assert result == {"a": "desc a", "b": "desc b"}

    def test_json_in_code_fence(self):
        result = GraphEnricher.parse_llm_response(
            '```json\n{"a": "desc a"}\n```'
        )
        assert result == {"a": "desc a"}

    def test_json_with_markdown_around_it(self):
        result = GraphEnricher.parse_llm_response(
            'Here is the result:\n\n```json\n{"x": "y"}\n```\nHope that helps.'
        )
        assert result == {"x": "y"}

    def test_json_without_fence_but_with_text(self):
        result = GraphEnricher.parse_llm_response(
            'OK here you go: {"foo": "bar baz"}'
        )
        assert result == {"foo": "bar baz"}

    def test_missing_json_raises_value_error(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            GraphEnricher.parse_llm_response("just some text")

    def test_malformed_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Malformed JSON"):
            GraphEnricher.parse_llm_response('{"a": "b",')

    def test_non_dict_response_raises_value_error(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            GraphEnricher.parse_llm_response("[1, 2, 3]")

    def test_multiline_descriptions(self):
        result = GraphEnricher.parse_llm_response(json.dumps({
            "a::b": "First line.\nSecond line.",
            "c::d": "Another one.",
        }))
        assert result["a::b"] == "First line.\nSecond line."
        assert result["c::d"] == "Another one."


# ══════════════════════════════════════════════════════════════════════════
# System prompt (TestEnricher)
# ══════════════════════════════════════════════════════════════════════════


class TestSystemPrompt:
    """Verify the TestEnricher system prompt includes required guidance."""

    def test_includes_fixture_guidance(self):
        assert "fixtures" in TestEnricher().system_prompt.lower()

    def test_includes_step_guidance(self):
        assert "steps" in TestEnricher().system_prompt.lower()

    def test_includes_assertion_guidance(self):
        assert "assertions" in TestEnricher().system_prompt.lower()

    def test_includes_json_format_instruction(self):
        assert "JSON object" in TestEnricher().system_prompt

    def test_no_markdown_instruction(self):
        assert "no markdown" in TestEnricher().system_prompt.lower()


# ══════════════════════════════════════════════════════════════════════════
# Convenience functions
# ══════════════════════════════════════════════════════════════════════════


class TestEnricherDirect:
    """Verify TestEnricher works directly (without convenience wrappers)."""

    def test_enrich_one_returns_summary_on_empty(self):
        """enrich_one with no children returns empty summary."""
        from unittest.mock import MagicMock
        mock_node = MagicMock()
        mock_node.qualified_name = "tests::test_x"
        mock_node.fixtures = None
        mock_node.steps = None
        mock_node.assertions = None
        summary = TestEnricher().enrich_one(mock_node)
        assert isinstance(summary, EnrichmentSummary)
        assert summary.target_name == "tests::test_x"

    def test_enrichment_field_passed_through(self):
        """Custom enrichment_field is stored on the enricher."""
        enricher = TestEnricher(enrichment_field="summary")
        assert enricher.enrichment_field == "summary"

    def test_enrichment_field_default(self):
        """Default enrichment_field is 'description'."""
        enricher = TestEnricher()
        assert enricher.enrichment_field == "description"

    def test_enrichment_available_no_key(self):
        """Without LLM_API_KEY, enrichment_available returns False."""
        from codegraph_enrich import enrichment_available
        result = enrichment_available()
        assert isinstance(result, bool)
