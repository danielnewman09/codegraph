"""Unit tests for the formatting module."""

from codegraph_requirements.formatting import (
    format_hlr_dict,
    format_llr_dict,
    format_hlrs_for_prompt,
    format_llrs_with_verifications_for_prompt,
    _format_condition_from_dict,
    _format_action_from_dict,
    _format_verification_from_dict,
)


class TestFormatHLR:
    # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_basic
    # Verifies that the formatting function for HLR dictionaries correctly includes the
    # required heading 'HLR 1:' and the phrase 'Handle errors', ensuring the output
    # matches document structure expectations.
    def test_basic(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_basic::step_0
        # Sets up the test by preparing the necessary context or data before executing
        # the formatting function, establishing the starting state for verification.
        result = format_hlr_dict({"id": 1, "description": "Handle errors"})
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_basic::post_0
        # Asserts that the formatted output begins with 'HLR 1:', confirming the heading
        # is correctly generated as per requirement structure.
        assert "HLR 1:" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_basic::post_1
        # Asserts that the formatted output contains 'Handle errors', verifying that
        # specific content from the HLR is properly included in the result.
        assert "Handle errors" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_component
    # This test verifies that the format_hlr_dict function correctly includes the
    # component name in the formatted output when a component is specified.
    def test_with_component(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_component::step_0
        # This step sets up the test environment by initializing the necessary data or
        # state required for the formatting operation.
        result = format_hlr_dict(
            {"id": 42, "description": "Log messages", "component_name": "backend"},
            include_component=True,
        )
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_component::post_0
        # This assertion verifies that the string '[Component: backend]' appears in the
        # formatted output, confirming that the format_hlr_dict function correctly
        # handles and includes component information.
        assert "[Component: backend]" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_refid
    # Verifies that the `format_hlr_dict` function includes a specific reference ID in
    # its output, ensuring the critical requirement of embedding reference identifiers
    # is met.
    def test_with_refid(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_refid::step_0
        # Sets up the test by preparing input data for the formatting function, ensuring
        # the context needed to verify correct reference ID handling is established.
        result = format_hlr_dict({"refid": "abc123", "description": "Track state"})
        # codegraph:test-desc requirements.test_formatting.TestFormatHLR.test_with_refid::post_0
        # Verifies that the formatted output contains the expected reference ID
        # 'abc123', confirming that the formatting function correctly includes required
        # reference identifiers.
        assert "abc123" in result


class TestFormatLLR:
    # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_basic
    # Verifies that the function format_llr_dict correctly formats an LLR entry with its
    # numeric identifier and a validation description.
    def test_basic(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_basic::step_0
        # Sets up the test environment or calls the function with a sample input to
        # prepare for verifying the output formatting.
        result = format_llr_dict({"id": 2, "description": "Validate input"})
        # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_basic::post_0
        # Asserts that the formatted output contains the string 'LLR 2:', confirming the
        # LLR identifier is correctly numbered and displayed.
        assert "LLR 2:" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_basic::post_1
        # Asserts that the formatted output includes 'Validate input', verifying the
        # descriptive text of the requirement is properly embedded in the result.
        assert "Validate input" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_with_refid
    # Verifies that formatting an LLR dictionary containing a reference identifier
    # (refid) correctly includes that reference in the output.
    def test_with_refid(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_with_refid::step_0
        # Sets up an LLR dictionary with a refid to test the formatting function's
        # handling of reference identifiers.
        result = format_llr_dict({"refid": "def456", "description": "Check bounds"})
        # codegraph:test-desc requirements.test_formatting.TestFormatLLR.test_with_refid::post_0
        # Asserts that the formatted output contains the expected refid 'def456',
        # confirming that the format_llr_dict function correctly preserves reference
        # identifiers in the result.
        assert "def456" in result


class TestFormatHLRsForPrompt:
    # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_single_hlr
    # Verifies that a single HLR is correctly formatted for prompt inclusion, ensuring
    # essential requirement data is presented clearly.
    def test_single_hlr(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_single_hlr::step_0
        # Sets up the test by populating the HLR list and invoking the formatting
        # function, establishing the necessary context for verifying the output.
        hlrs = [{"id": 1, "description": "Handle errors"}]
        result = format_hlrs_for_prompt(hlrs)
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_single_hlr::post_0
        # Asserts that the formatted output contains the text 'HLR 1: Handle errors',
        # confirming that the function correctly includes the identifier and description
        # of the single HLR.
        assert "HLR 1: Handle errors" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_with_llrs
    # Verifies that formatting High-Level Requirements with LLRs includes the expected
    # LLR entries in the output string, ensuring the prompt properly incorporates LLR
    # data.
    def test_with_llrs(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_with_llrs::step_0
        # Initializes the test context by calling the format_hlrs_for_prompt function
        # with HLRs that contain LLRs, setting up the result string for assertion.
        hlrs = [{"id": 1, "description": "Handle errors"}]
        llrs = [{"hlr_id": 1, "id": 10, "description": "Validate input"}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_with_llrs::post_0
        # Asserts that the formatted output contains the string '  LLR 10: Validate
        # input', confirming that LLRs are correctly included in the generated prompt.
        assert "  LLR 10: Validate input" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_unlinked_llrs
    # Verifies that when HLRs are unlinked, the function correctly includes an 'Unlinked
    # LLRs:' section in the output, ensuring the prompt accurately reflects the
    # incomplete linkage.
    def test_unlinked_llrs(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_unlinked_llrs::step_0
        # Sets up the test by preparing necessary context, such as HLRs with unlinked
        # LLRs, to initialize the state required for verifying the formatting function's
        # behavior.
        hlrs = [{"id": 1, "description": "Handle errors"}]
        llrs = [{"hlr_id": None, "id": 99, "description": "Orphan LLR"}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_unlinked_llrs::post_0
        # Asserts that the string 'Unlinked LLRs:' is present in the formatted result,
        # confirming the function correctly identifies and labels unlinked requirements.
        assert "Unlinked LLRs:" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatHLRsForPrompt.test_unlinked_llrs::post_1
        # Asserts that 'LLR 99' appears in the result, verifying that the specific
        # unlinked LLR is listed in the output for traceability.
        assert "LLR 99" in result


class TestFormatCondition:
    # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_with_operands
    # Verifies that the condition formatting function correctly handles operands by
    # producing the expected string representation of the condition.
    def test_with_operands(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_with_operands::step_0
        # Sets up the test environment and prepares the input data needed to invoke the
        # formatting logic on the test condition with its operands.
        cond = {
            "operator": "==",
            "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine.result"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "30"},
            ],
        }
        result = _format_condition_from_dict(cond)
        # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_with_operands::post_0
        # Asserts that the formatted condition string equals 'Engine.result == 30',
        # confirming that the operand values and the relational operator are correctly
        # represented in the output.
        assert "Engine.result == 30" == result

    # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_no_operands
    # Verifies that the format_condition_from_dict function produces the string ' !='
    # when given a condition with no operands, which is important to ensure the function
    # handles valid but minimal input consistently.
    def test_no_operands(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_no_operands::step_0
        # Sets up the test by calling _format_condition_from_dict with an empty operands
        # list, establishing the minimal input state required for the subsequent
        # assertion.
        cond = {"operator": "!=", "edges": []}
        result = _format_condition_from_dict(cond)
        # codegraph:test-desc requirements.test_formatting.TestFormatCondition.test_no_operands::post_0
        # Checks that the formatted result contains the string ' !=', confirming that
        # the function correctly represents a condition with no comparison operands
        # using the inequality operator.
        assert " !=" in result


class TestFormatAction:
    # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_with_callee_and_caller
    # Verifies that the `_format_action_from_dict` function correctly formats actions
    # that include both a callee and a caller, ensuring the output string contains the
    # expected caller and callee references.
    def test_with_callee_and_caller(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_with_callee_and_caller::step_0
        # Sets up the test by preparing the input dictionary and calling
        # `_format_action_from_dict`, which produces the result to be checked by the
        # subsequent assertions.
        action = {
            "description": "Set target value",
            "edges": [
                {"relation_type": "CALLEE", "target_uid": "Engine::set_target"},
                {"relation_type": "CALLER", "target_uid": "TestNode"},
            ],
        }
        result = _format_action_from_dict(action)
        # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_with_callee_and_caller::post_0
        # Verifies that the formatted action includes a caller-callee relationship
        # string 'TestNode → Engine::set_target', ensuring the function accurately
        # represents both the source and target of the action.
        assert "TestNode → Engine::set_target" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_with_callee_and_caller::post_1
        # Checks that the formatted action includes the literal string 'Set target
        # value', confirming that the action's description is correctly incorporated
        # into the output.
        assert "Set target value" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_callee_only
    # Verifies that `_format_action_from_dict` correctly extracts only the callee
    # function name from an action dictionary, ensuring that formatted output focuses on
    # the called method without extraneous details.
    def test_callee_only(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_callee_only::step_0
        # Sets up the test by preparing a minimal action dictionary or mock context,
        # establishing the necessary input conditions for the formatting logic to
        # process.
        action = {
            "description": "",
            "edges": [{"relation_type": "CALLEE", "target_uid": "Engine::compute"}],
        }
        result = _format_action_from_dict(action)
        # codegraph:test-desc requirements.test_formatting.TestFormatAction.test_callee_only::post_0
        # Confirms that the formatted result contains the exact callee string
        # `Engine::compute`, validating that the function isolates the target method
        # name correctly from the action data.
        assert "Engine::compute" in result


class TestFormatVerification:
    # codegraph:test-desc requirements.test_formatting.TestFormatVerification.test_full
    # Verifies that the formatting function produces a correctly structured verification
    # string from a dictionary, ensuring all key fields are present and readable.
    def test_full(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatVerification.test_full::step_0
        # Sets up the test environment and input data, preparing the dictionary that
        # will be passed to the formatting function.
        v = {
            "method": "automated",
            "test_name": "test_add",
            "description": "Verify addition",
            "preconditions": [],
            "actions": [],
            "postconditions": [],
        }
        result = _format_verification_from_dict(v)
        # codegraph:test-desc requirements.test_formatting.TestFormatVerification.test_full::post_0
        # Confirms that the formatted output contains the label '[automated] test_add',
        # verifying the function properly includes the requirement name in the result.
        assert "[automated] test_add" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatVerification.test_full::post_1
        # Checks that the formatted output includes the verification description 'Verify
        # addition', confirming that the function correctly renders human-readable
        # requirement text.
        assert "Verify addition" in result
        # codegraph:test-desc requirements.test_formatting.TestFormatVerification.test_full::post_2
        # Verifies that the output includes 'Pre-conditions: (none)', ensuring that
        # empty precondition fields are handled and displayed clearly in the final
        # string.
        assert "Pre-conditions: (none)" in result


class TestFormatLLRsWithVerifications:
    # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_empty
    # Verifies that the formatting function returns an empty string when provided with
    # no requirements, ensuring the code handles empty input gracefully.
    def test_empty(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_empty::step_0
        # Calls the formatting function with an empty list of requirements to set up the
        # state for verifying the output.
        result = format_llrs_with_verifications_for_prompt([], {})
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_empty::post_0
        # Checks that the function returns an empty string, confirming that no false
        # content is generated for missing input.
        assert result == ""

    # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_no_verifications
    # Verifies that when there are no LLRs, the formatting function outputs a
    # placeholder message indicating no verification stubs found.
    def test_no_verifications(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_no_verifications::step_0
        # Sets up the test by calling the formatting function with an empty list of
        # LLRs, establishing the scenario for verifying the output when no verifications
        # exist.
        llrs = [{"id": 1, "description": "Validate input"}]
        result = format_llrs_with_verifications_for_prompt(llrs, {})
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_no_verifications::post_0
        # Checks that the formatted result contains the exact string '(No verification
        # stubs)' to confirm that the function correctly indicates the absence of
        # verification requirements.
        assert "(No verification stubs)" in result

    # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_with_verifications
    # Verifies that the formatting function includes 'Verifications:' in its output when
    # LLRs have associated verifications, ensuring that verification information is
    # properly surfaced in the prompt.
    def test_with_verifications(self):
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_with_verifications::step_0
        # Sets up the test environment or data required to call the formatting function,
        # preparing the input that will be used to generate the prompt output.
        llrs = [{"id": 1, "description": "Validate input"}]
        verifs = {1: [{"method": "automated", "preconditions": [], "actions": [], "postconditions": []}]}
        result = format_llrs_with_verifications_for_prompt(llrs, verifs)
        # codegraph:test-desc requirements.test_formatting.TestFormatLLRsWithVerifications.test_with_verifications::post_0
        # Checks that the formatted result contains the string 'Verifications:',
        # confirming that the formatting function correctly includes verification
        # metadata for LLRs that have them.
        assert "Verifications:" in result
