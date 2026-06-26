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
    def test_basic(self):
        result = format_hlr_dict({"id": 1, "description": "Handle errors"})
        assert "HLR 1:" in result
        assert "Handle errors" in result

    def test_with_component(self):
        result = format_hlr_dict(
            {"id": 42, "description": "Log messages", "component_name": "backend"},
            include_component=True,
        )
        assert "[Component: backend]" in result

    def test_with_refid(self):
        result = format_hlr_dict({"refid": "abc123", "description": "Track state"})
        assert "abc123" in result


class TestFormatLLR:
    def test_basic(self):
        result = format_llr_dict({"id": 2, "description": "Validate input"})
        assert "LLR 2:" in result
        assert "Validate input" in result

    def test_with_refid(self):
        result = format_llr_dict({"refid": "def456", "description": "Check bounds"})
        assert "def456" in result


class TestFormatHLRsForPrompt:
    def test_single_hlr(self):
        hlrs = [{"id": 1, "description": "Handle errors"}]
        result = format_hlrs_for_prompt(hlrs)
        assert "HLR 1: Handle errors" in result

    def test_with_llrs(self):
        hlrs = [{"id": 1, "description": "Handle errors"}]
        llrs = [{"hlr_id": 1, "id": 10, "description": "Validate input"}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        assert "  LLR 10: Validate input" in result

    def test_unlinked_llrs(self):
        hlrs = [{"id": 1, "description": "Handle errors"}]
        llrs = [{"hlr_id": None, "id": 99, "description": "Orphan LLR"}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        assert "Unlinked LLRs:" in result
        assert "LLR 99" in result


class TestFormatCondition:
    def test_with_operands(self):
        cond = {
            "operator": "==",
            "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine.result"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "30"},
            ],
        }
        result = _format_condition_from_dict(cond)
        assert "Engine.result == 30" == result

    def test_no_operands(self):
        cond = {"operator": "!=", "edges": []}
        result = _format_condition_from_dict(cond)
        assert " !=" in result


class TestFormatAction:
    def test_with_callee_and_caller(self):
        action = {
            "description": "Set target value",
            "edges": [
                {"relation_type": "CALLEE", "target_uid": "Engine::set_target"},
                {"relation_type": "CALLER", "target_uid": "TestNode"},
            ],
        }
        result = _format_action_from_dict(action)
        assert "TestNode → Engine::set_target" in result
        assert "Set target value" in result

    def test_callee_only(self):
        action = {
            "description": "",
            "edges": [{"relation_type": "CALLEE", "target_uid": "Engine::compute"}],
        }
        result = _format_action_from_dict(action)
        assert "Engine::compute" in result


class TestFormatVerification:
    def test_full(self):
        v = {
            "method": "automated",
            "test_name": "test_add",
            "description": "Verify addition",
            "preconditions": [],
            "actions": [],
            "postconditions": [],
        }
        result = _format_verification_from_dict(v)
        assert "[automated] test_add" in result
        assert "Verify addition" in result
        assert "Pre-conditions: (none)" in result


class TestFormatLLRsWithVerifications:
    def test_empty(self):
        result = format_llrs_with_verifications_for_prompt([], {})
        assert result == ""

    def test_no_verifications(self):
        llrs = [{"id": 1, "description": "Validate input"}]
        result = format_llrs_with_verifications_for_prompt(llrs, {})
        assert "(No verification stubs)" in result

    def test_with_verifications(self):
        llrs = [{"id": 1, "description": "Validate input"}]
        verifs = {1: [{"method": "automated", "preconditions": [], "actions": [], "postconditions": []}]}
        result = format_llrs_with_verifications_for_prompt(llrs, verifs)
        assert "Verifications:" in result
