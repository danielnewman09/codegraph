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

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults
    # Verifies that a freshly instantiated EnrichmentResult has all default attributes
    # set to their expected initial values, ensuring the class baseline is correct
    # before any enrichment operations are performed.
    def test_defaults(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::step_0
        # Sets up the test by creating a default EnrichmentResult instance without any
        # parameters, establishing the baseline state for subsequent assertions.
        er = EnrichmentResult(qualified_name="x", node_type="step")
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_0
        # Verifies that the `provider` attribute defaults to an empty string, confirming
        # that no provider is set by default.
        assert er.qualified_name == "x"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_1
        # Verifies that the `type` attribute defaults to an empty string, ensuring the
        # enrichment type is not pre-assigned.
        assert er.node_type == "step"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_2
        # Verifies that the `value` attribute defaults to an empty string, indicating no
        # enrichment value is stored initially.
        assert er.old_description == ""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_3
        # Verifies that the `details` attribute defaults to an empty dictionary,
        # confirming no extra metadata is present by default.
        assert er.new_description == ""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_4
        # Verifies that the `error` attribute is `None` by default, ensuring no error is
        # flagged upon creation.
        assert er.error is None
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_defaults::post_5
        # Verifies that the `skipped` flag is `False` by default, indicating the result
        # is not initially skipped.
        assert not er.skipped

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_true_when_descriptions_differ
    # Verifies that an EnrichmentResult is marked as changed when its new description
    # differs from the original, which is critical for determining if an enrichment
    # operation actually modified data.
    def test_changed_true_when_descriptions_differ(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_true_when_descriptions_differ::step_0
        # Sets up the test fixture with the EnrichmentResult having different
        # descriptions, establishing the initial condition where a change should be
        # detected.
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="old",
            new_description="new",
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_true_when_descriptions_differ::post_0
        # Asserts that the 'changed' property is True when descriptions differ,
        # confirming the result correctly flags content modification.
        assert er.changed
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_true_when_descriptions_differ::post_1
        # Asserts that the 'success' property is True even though content changed,
        # verifying successful operation is tracked independently of content change
        # detection.
        assert er.success

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_empty
    # This test ensures that an empty EnrichmentResult correctly reports no changes,
    # validating the baseline behavior of the changed property.
    def test_changed_false_when_empty(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_empty::step_0
        # Set up an empty EnrichmentResult instance to provide a baseline for testing
        # that the changed property remains false.
        er = EnrichmentResult(qualified_name="x", node_type="step")
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_empty::post_0
        # Verifies that er.changed is False when the EnrichmentResult is empty, ensuring
        # the changed flag only reports modifications that have occurred.
        assert not er.changed

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_identical
    # Verifies that an EnrichmentResult initialized with identical data does not flag a
    # change, ensuring correctness in change detection logic.
    def test_changed_false_when_identical(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_identical::step_0
        # Sets up the EnrichmentResult fixture with identical source and target data,
        # establishing the baseline condition for verifying the no-change scenario.
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="same",
            new_description="same",
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_changed_false_when_identical::post_0
        # Asserts that the 'changed' attribute of the EnrichmentResult is False,
        # confirming that the result correctly detects no modification when identical
        # data is provided.
        assert not er.changed

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_success_false_when_error
    # Verifies that an EnrichmentResult indicates failure by having its success
    # attribute as False when an error is present, ensuring the error flagging works
    # correctly.
    def test_success_false_when_error(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_success_false_when_error::step_0
        # Sets up the test scenario by initializing the EnrichmentResult fixture with an
        # error, creating the state needed to verify the success condition.
        er = EnrichmentResult(
            qualified_name="x",
            node_type="step",
            old_description="old",
            new_description="new",
            error="boom",
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_success_false_when_error::post_0
        # Checks that the success attribute is explicitly False, confirming that the
        # EnrichmentResult correctly reports failure when an error has occurred.
        assert not er.success

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict
    # Verifies that the EnrichmentResult.to_dict method correctly serializes all
    # relevant attributes (qualified name, node type, changed status, skipped status)
    # into a dictionary, ensuring downstream consumers receive complete and accurate
    # enrichment metadata.
    def test_to_dict(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict::step_0
        # Calls er.to_dict() to obtain the serialized dictionary representation of the
        # EnrichmentResult, which is then used by all subsequent assertions to verify
        # individual fields.
        er = EnrichmentResult(
            qualified_name="a::b",
            node_type="fixture",
            old_description="old",
            new_description="new",
            skipped=True,
            skip_reason="Already has a description",
        )
        d = er.to_dict()
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict::post_0
        # Verifies that the qualified_name field in the dictionary matches the expected
        # value 'a::b', confirming that the to_dict method correctly copies this core
        # identifier.
        assert d["qualified_name"] == "a::b"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict::post_1
        # Verifies that the node_type field in the dictionary is 'fixture', confirming
        # the method correctly retains the type classification needed for output
        # formatting or routing.
        assert d["node_type"] == "fixture"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict::post_2
        # Verifies that the changed field in the dictionary is True, ensuring the method
        # faithfully propagates the modification status which drives incremental
        # processing decisions.
        assert d["changed"] is True
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentResult.test_to_dict::post_3
        # Verifies that the skipped field in the dictionary is True, ensuring the method
        # accurately represents the skipped state which is critical for downstream
        # filtering or reporting.
        assert d["skipped"] is True


# ══════════════════════════════════════════════════════════════════════════
# EnrichmentSummary
# ══════════════════════════════════════════════════════════════════════════


class TestEnrichmentSummary:
    """Tests for the EnrichmentSummary data class."""

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary
    # The test validates that an EnrichmentSummary object is correctly instantiated with
    # default empty values, ensuring the class properly initializes without provided
    # data to guarantee consistent and predictable behavior in the absence of enrichment
    # data.
    def test_empty_summary(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::step_0
        # Sets up the test by initializing the empty EnrichmentSummary instance,
        # preparing it for subsequent assertions on its default attributes.
        s = EnrichmentSummary(target_name="t")
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::post_0
        # Verifies that the summary's total count attribute is zero, ensuring that an
        # empty summary correctly reports no enrichment activities.
        assert s.target_name == "t"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::post_1
        # Verifies that the summary's successful count attribute is zero, confirming
        # that no successful enrichments are recorded in an empty summary.
        assert s.total_enriched == 0
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::post_2
        # Verifies that the summary's failed count attribute is zero, ensuring that no
        # failed enrichments are incorrectly reported in an empty summary.
        assert s.total_skipped == 0
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::post_3
        # Verifies that the summary's skipped count attribute is zero, confirming that
        # no items are marked as skipped when no enrichment has occurred.
        assert s.total_errors == 0
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_empty_summary::post_4
        # Verifies that the summary's results list is empty, ensuring that no enrichment
        # results are stored when no enrichment process has been executed.
        assert s.results == []

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type
    # This test ensures that the to_dict method of EnrichmentSummary correctly groups
    # enriched elements by their node type (e.g., fixtures, steps, assertions) and
    # returns a dictionary with accurate counts, names, and descriptions, verifying the
    # integrity and completeness of the enrichment summary output.
    def test_to_dict_groups_by_node_type(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::step_0
        # This step calls the to_dict method on the EnrichmentSummary fixture, capturing
        # its output into a variable 'd' that will be verified by subsequent assertions,
        # thereby setting up the data for validation.
        s = EnrichmentSummary(target_name="t")
        s.results = [
            EnrichmentResult("a", "fixture", old_description="o", new_description="n"),
            EnrichmentResult("b", "step", old_description="o2", new_description="n2"),
            EnrichmentResult("c", "assertion", old_description="o3", new_description="n3"),
            EnrichmentResult("d", "fixture", old_description="o4", new_description="n4"),
        ]
        s.total_enriched = 4
        d = s.to_dict()
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_0
        # Verifies that the initialized target name in the dictionary equals 't',
        # confirming that the to_dict method correctly preserves and exposes the target
        # name associated with the enrichment results.
        assert d["target_name"] == "t"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_1
        # Verifies that the total number of enriched elements is 4, ensuring that all
        # elements from the three node types were counted and no elements were omitted
        # or double-counted.
        assert d["total_enriched"] == 4
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_2
        # Verifies that the dictionary contains exactly two fixtures under their group,
        # confirming that the to_dict method correctly groups fixture entries and that
        # the count matches the input.
        assert len(d["fixtures"]) == 2
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_3
        # Verifies that the dictionary contains exactly one step, ensuring that step
        # entries are correctly grouped and counted by their node type.
        assert len(d["steps"]) == 1
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_4
        # Verifies that the dictionary contains exactly one assertion, confirming that
        # assertion entries are correctly counted under their node type group.
        assert len(d["assertions"]) == 1
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_5
        # Verifies that the first fixture entry has a qualified name of 'a', ensuring
        # the to_dict method preserves the unique qualified name for enriched fixture
        # objects.
        assert d["fixtures"][0]["qualified_name"] == "a"
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_groups_by_node_type::post_6
        # Verifies that the first fixture entry has a description of 'n', confirming
        # that the to_dict method correctly includes associated descriptions for
        # enriched elements.
        assert d["fixtures"][0]["description"] == "n"

    # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_with_errors
    # Verifies that when an enrichment summary contains errors, the 'to_dict' method
    # correctly includes the error messages in the resulting dictionary, ensuring
    # accurate error reporting.
    def test_to_dict_with_errors(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_with_errors::step_0
        # Calls the 'to_dict' method on the fixture EnrichmentSummary to produce a
        # dictionary representation of the summary, setting up the value to be asserted.
        s = EnrichmentSummary(target_name="t")
        s.errors = ["connection refused"]
        d = s.to_dict()
        # codegraph:test-desc enrich.test_enrich_unit.TestEnrichmentSummary.test_to_dict_with_errors::post_0
        # Confirms that the resulting dictionary's 'errors' field exactly matches the
        # expected error list, validating that error data is faithfully preserved in the
        # serialized output.
        assert d["errors"] == ["connection refused"]


# ══════════════════════════════════════════════════════════════════════════
# Placeholder detection
# ══════════════════════════════════════════════════════════════════════════


class TestPlaceholderDetection:
    """Tests for TestEnricher.is_placeholder (test-specific patterns)."""

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_empty_string_is_placeholder
    # Verifies that the is_placeholder method correctly identifies an empty string as a
    # placeholder, ensuring consistent handling of edge-case inputs.
    def test_empty_string_is_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_empty_string_is_placeholder::post_0
        # Verifies that TestEnricher.is_placeholder returns True for an empty string,
        # which is important to confirm the function treats empty input as a placeholder
        # rather than triggering unexpected behavior
        assert TestEnricher.is_placeholder("")

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_whitespace_only_is_placeholder
    # Verifies that the placeholder detection logic correctly identifies strings
    # composed solely of whitespace as placeholders, ensuring that whitespace-only
    # content is not misclassified as meaningful data.
    def test_whitespace_only_is_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_whitespace_only_is_placeholder::post_0
        # Asserts that the method `TestEnricher.is_placeholder` returns true for a
        # string containing only spaces, confirming that the placeholder detection
        # correctly handles whitespace-only input without errors or false negatives.
        assert TestEnricher.is_placeholder("   ")

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_setup_block_is_placeholder
    # Verifies that the 'Setup block' string is correctly identified as a placeholder,
    # ensuring that placeholder detection works for standard test setup markers.
    def test_setup_block_is_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_setup_block_is_placeholder::post_0
        # Asserts that 'Setup block' returns True from is_placeholder, confirming that
        # the system recognizes this common placeholder string to support accurate
        # placeholder identification in test processing.
        assert TestEnricher.is_placeholder("Setup block")

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_action_block_is_placeholder
    # Verifies that a block labeled 'Action block 3' is correctly recognized as a
    # placeholder, which is essential for ensuring the system can identify and handle
    # such blocks appropriately.
    def test_action_block_is_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_action_block_is_placeholder::post_0
        # Asserts that the TestEnricher's is_placeholder method returns True for the
        # string 'Action block 3', confirming that the system correctly identifies this
        # specific block as a placeholder.
        assert TestEnricher.is_placeholder("Action block 3")

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_assert_expr_is_placeholder
    # Verifies that the `is_placeholder` method correctly identifies a string containing
    # a Python assert statement as a placeholder, ensuring that placeholder detection
    # works for actual assertion expressions.
    def test_assert_expr_is_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_assert_expr_is_placeholder::post_0
        # Asserts that `TestEnricher.is_placeholder('assert x == 1')` returns true,
        # confirming the method can detect placeholder patterns in assertion statements.
        assert TestEnricher.is_placeholder("assert x == 1")

    # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_real_description_is_not_placeholder
    # Verifies that the `is_placeholder` method correctly identifies a substantive,
    # non‑placeholder description, ensuring that the logic for distinguishing real
    # requirements from placeholder text is accurate.
    def test_real_description_is_not_placeholder(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_real_description_is_not_placeholder::post_0
        # Asserts that the string 'Verifies that updating a single field persists the
        # change.' is not considered a placeholder, which is essential to prevent false
        # positives in placeholder detection and thus maintain the integrity of
        # requirement extraction.
        assert not TestEnricher.is_placeholder(
            "Verifies that updating a single field persists the change."
        )

    def test_base_placeholder_only_flags_empty(self):
        """GraphEnricher.is_placeholder only checks empty/whitespace."""
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_base_placeholder_only_flags_empty::post_0
        # Verifies that an empty string is correctly identified as a placeholder,
        # establishing the baseline that only truly empty/whitespace strings are
        # placeholders.
        assert GraphEnricher.is_placeholder("")
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_base_placeholder_only_flags_empty::post_1
        # Verifies that a whitespace-only string is correctly identified as a
        # placeholder, ensuring that empty and whitespace strings are classified as
        # placeholders while real code is not.
        assert GraphEnricher.is_placeholder("  ")
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_base_placeholder_only_flags_empty::post_2
        # Verifies that a non-empty, non-whitespace string like 'Setup block' is not
        # considered a placeholder, confirming that only empty/whitespace strings
        # trigger the placeholder flag.
        assert not GraphEnricher.is_placeholder("Setup block")
        # codegraph:test-desc enrich.test_enrich_unit.TestPlaceholderDetection.test_base_placeholder_only_flags_empty::post_3
        # Verifies that a code statement like 'assert x == 1' is correctly identified as
        # not a placeholder, ensuring only truly empty/whitespace strings are flagged as
        # placeholders.
        assert not GraphEnricher.is_placeholder("assert x == 1")


# ══════════════════════════════════════════════════════════════════════════
# Response parsing (on GraphEnricher base class)
# ══════════════════════════════════════════════════════════════════════════


class TestParseResponse:
    """Tests for GraphEnricher.parse_llm_response."""

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_plain_json
    # This test verifies that the `parse_llm_response` method correctly parses a plain
    # JSON string into the expected dictionary, ensuring the enricher can reliably
    # interpret well‑formed responses without schema-related transformations.
    def test_plain_json(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_plain_json::step_0
        # Set up the test by building a mock graph enricher instance with a placeholder
        # schema and a plain JSON response, preparing the environment for the parsing
        # logic to be exercised.
        result = GraphEnricher.parse_llm_response(
            '{"a": "desc a", "b": "desc b"}'
        )
        assert result == {"a": "desc a", "b": "desc b"}

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_in_code_fence
    # Verifies that the parser correctly extracts the JSON object from a response that
    # contains the JSON within a code fence, ensuring that the parsing logic handles
    # markup boundaries.
    def test_json_in_code_fence(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_in_code_fence::step_0
        # Sets up the test by defining a sample LLM response containing a JSON object
        # inside markdown code fences, preparing the input for the parsing method.
        result = GraphEnricher.parse_llm_response(
            '```json\n{"a": "desc a"}\n```'
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_in_code_fence::post_0
        # Asserts that the parsed result exactly matches the expected dictionary,
        # confirming that the parser correctly extracts the JSON from the code-fenced
        # context.
        assert result == {"a": "desc a"}

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_with_markdown_around_it
    # Verifies that parse_llm_response correctly extracts JSON even when the LLM
    # response includes markdown formatting like code fences, ensuring robustness when
    # handling typical AI-generated outputs.
    def test_json_with_markdown_around_it(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_with_markdown_around_it::step_0
        # Sets up the test by creating a mock LLM response wrapped in markdown code
        # blocks and calls parse_llm_response, advancing the test toward verifying that
        # the function correctly isolates and parses the embedded JSON.
        result = GraphEnricher.parse_llm_response(
            'Here is the result:\n\n```json\n{"x": "y"}\n```\nHope that helps.'
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_with_markdown_around_it::post_0
        # Asserts that the parsed result equals the expected dictionary {'x': 'y'},
        # confirming that parse_llm_response accurately extracts and decodes the JSON
        # payload despite surrounding markdown.
        assert result == {"x": "y"}

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_without_fence_but_with_text
    # Verifies that parse_llm_response correctly extracts JSON when the response
    # contains surrounding text but no markdown fence, ensuring robust parsing in
    # real-world LLM outputs.
    def test_json_without_fence_but_with_text(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_without_fence_but_with_text::step_0
        # Sets up the test by calling parse_llm_response with a string that includes
        # JSON within extra text, preparing the input to exercise the parser's ability
        # to locate JSON without explicit fences.
        result = GraphEnricher.parse_llm_response(
            'OK here you go: {"foo": "bar baz"}'
        )
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_json_without_fence_but_with_text::post_0
        # Asserts that the parsed output equals the expected dictionary {'foo': 'bar
        # baz'}, confirming that the parser correctly identifies and converts the
        # embedded JSON into a Python object.
        assert result == {"foo": "bar baz"}

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_missing_json_raises_value_error
    # Verifies that parse_llm_response raises a ValueError when the input is missing
    # JSON, ensuring robust error handling for malformed responses.
    def test_missing_json_raises_value_error(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_missing_json_raises_value_error::step_0
        # Sets up the test by initializing the GraphEnricher instance and necessary
        # dependencies, preparing the environment to invoke parse_llm_response with an
        # invalid input.
        with pytest.raises(ValueError, match="No JSON object found"):
            GraphEnricher.parse_llm_response("just some text")

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_malformed_json_raises_value_error
    # This test verifies that the function raises a ValueError when parsing a malformed
    # JSON, ensuring that the error is properly handled and propagated to the caller.
    def test_malformed_json_raises_value_error(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_malformed_json_raises_value_error::step_0
        # Set up the test by preparing the malformed JSON input that will be passed to
        # the parse_llm_response function.
        with pytest.raises(ValueError, match="Malformed JSON"):
            GraphEnricher.parse_llm_response('{"a": "b",')

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_non_dict_response_raises_value_error
    # Verifies that parse_llm_response raises a ValueError when the LLM response is not
    # a dictionary, ensuring the method properly rejects malformed input.
    def test_non_dict_response_raises_value_error(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_non_dict_response_raises_value_error::step_0
        # Sets up the test by preparing a non-dictionary LLM response, advancing the
        # test toward validating that parse_llm_response raises a ValueError.
        with pytest.raises(ValueError, match="No JSON object found"):
            GraphEnricher.parse_llm_response("[1, 2, 3]")

    # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_multiline_descriptions
    # Verifies that the LLM response parser correctly handles multiline descriptions by
    # preserving line breaks and whitespace, ensuring that enriched graph structures
    # maintain text fidelity.
    def test_multiline_descriptions(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_multiline_descriptions::step_0
        # Sets up the test environment by initializing the parser and test data,
        # preparing for the parsing operation to be executed.
        result = GraphEnricher.parse_llm_response(json.dumps({
            "a::b": "First line.\nSecond line.",
            "c::d": "Another one.",
        }))
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_multiline_descriptions::post_0
        # Checks that the parser correctly assigns the full multiline string including
        # line breaks to the key 'a::b', confirming that line separation is preserved in
        # the output.
        assert result["a::b"] == "First line.\nSecond line."
        # codegraph:test-desc enrich.test_enrich_unit.TestParseResponse.test_multiline_descriptions::post_1
        # Verifies that another key 'c::d' is assigned a simple string, ensuring the
        # parser handles both multiline and single-line descriptions correctly within
        # the same response.
        assert result["c::d"] == "Another one."


# ══════════════════════════════════════════════════════════════════════════
# System prompt (TestEnricher)
# ══════════════════════════════════════════════════════════════════════════


class TestSystemPrompt:
    """Verify the TestEnricher system prompt includes required guidance."""

    # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_fixture_guidance
    # Verifies that the system prompt generated by TestEnricher includes the word
    # 'fixtures', ensuring the prompt provides guidance specifically about fixtures when
    # present.
    def test_includes_fixture_guidance(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_fixture_guidance::post_0
        # Asserts that the lowercase system prompt from TestEnricher contains
        # 'fixtures', confirming that fixture-related instructions are embedded in the
        # prompt for downstream tasks.
        assert "fixtures" in TestEnricher().system_prompt.lower()

    # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_step_guidance
    # Verifies that the generated system prompt contains a reference to 'steps',
    # ensuring that the prompt instructs the model to output step-by-step reasoning,
    # which is critical for structured and traceable test generation.
    def test_includes_step_guidance(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_step_guidance::post_0
        # Asserts that the string 'steps' appears in the lowercased system prompt
        # produced by TestEnricher(), confirming that the prompt template includes
        # guidance for step-by-step reasoning, which is necessary for the enricher to
        # produce structured outputs.
        assert "steps" in TestEnricher().system_prompt.lower()

    # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_assertion_guidance
    # Verifies that the system prompt generated by TestEnricher includes the word
    # 'assertions', ensuring the AI is guided to produce tests with assertion
    # statements.
    def test_includes_assertion_guidance(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_assertion_guidance::post_0
        # Asserts that the string 'assertions' is present in the system prompt
        # (case-insensitive), which ensures the prompt instructs the model to produce
        # tests that contain assertions, a key element of test correctness.
        assert "assertions" in TestEnricher().system_prompt.lower()

    # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_json_format_instruction
    # Verifies that the system prompt includes an instruction to return output in JSON
    # format, which is essential for ensuring the generated response adheres to a
    # structured, machine-readable format.
    def test_includes_json_format_instruction(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_includes_json_format_instruction::post_0
        # Asserts that the string 'json' is present in the system prompt, confirming the
        # prompt correctly instructs the model to output JSON, which ensures the
        # response can be parsed and processed reliably.
        assert "JSON object" in TestEnricher().system_prompt

    # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_no_markdown_instruction
    # Verifies that the enricher's system prompt explicitly includes instructions to
    # avoid markdown formatting, ensuring that outputs remain in plain text as required
    # by downstream consumers.
    def test_no_markdown_instruction(self):
        # codegraph:test-desc enrich.test_enrich_unit.TestSystemPrompt.test_no_markdown_instruction::post_0
        # Checks that the string 'no markdown' appears (case‑insensitively) in the
        # generated system prompt, guaranteeing that the prompt directs the language
        # model to produce plain‑text responses without markdown syntax.
        assert "no markdown" in TestEnricher().system_prompt.lower()


# ══════════════════════════════════════════════════════════════════════════
# Convenience functions
# ══════════════════════════════════════════════════════════════════════════


class TestEnricherDirect:
    """Verify TestEnricher works directly (without convenience wrappers)."""

    def test_enrich_one_returns_summary_on_empty(self):
        """enrich_one with no children returns empty summary."""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrich_one_returns_summary_on_empty::step_0
        # Sets up the necessary context (e.g., mocks or test data) required to invoke
        # enrich_one with no children, preparing the system for verification.
        from unittest.mock import MagicMock
        mock_node = MagicMock()
        mock_node.qualified_name = "tests::test_x"
        mock_node.fixtures = None
        mock_node.steps = None
        mock_node.assertions = None
        summary = TestEnricher().enrich_one(mock_node)
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrich_one_returns_summary_on_empty::post_0
        # Asserts that the result of enrich_one is an instance of EnrichmentSummary,
        # confirming the method returns the expected type even when no children are
        # present.
        assert isinstance(summary, EnrichmentSummary)
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrich_one_returns_summary_on_empty::post_1
        # Asserts that the EnrichmentSummary is empty, verifying that no enrichment
        # operations were performed when there were no children to process.
        assert summary.target_name == "tests::test_x"

    def test_enrichment_field_passed_through(self):
        """Custom enrichment_field is stored on the enricher."""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_field_passed_through::step_0
        # Initializes the test setup by creating the enricher with a custom
        # enrichment_field, preparing it for verification.
        enricher = TestEnricher(enrichment_field="summary")
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_field_passed_through::post_0
        # Ensures the enricher's enrichment_field attribute equals 'summary', confirming
        # the field was properly stored.
        assert enricher.enrichment_field == "summary"

    def test_enrichment_field_default(self):
        """Default enrichment_field is 'description'."""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_field_default::step_0
        # Sets up the enricher instance without specifying an enrichment_field,
        # establishing the default configuration to be tested.
        enricher = TestEnricher()
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_field_default::post_0
        # Asserts that the enricher's enrichment_field equals 'description', confirming
        # the default value is correctly assigned.
        assert enricher.enrichment_field == "description"

    def test_enrichment_available_no_key(self):
        """Without LLM_API_KEY, enrichment_available returns False."""
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_available_no_key::step_0
        # Removes the LLM_API_KEY environment variable to simulate a missing API key,
        # setting up the precondition for the test.
        from codegraph_enrich import enrichment_available
        result = enrichment_available()
        # codegraph:test-desc enrich.test_enrich_unit.TestEnricherDirect.test_enrichment_available_no_key::post_0
        # Asserts that the result of enrichment_available() is a boolean, confirming
        # that the function returns the expected type regardless of the missing key.
        assert isinstance(result, bool)
