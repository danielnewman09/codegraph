"""Tests for feedback_tools — parse_feedback, propose, commit."""

from __future__ import annotations

import json
import os
import pytest

from codegraph_feedback.tools.feedback_tools import (
    resolve_feedback_file,
    parse_feedback_markdown,
    write_draft,
)
from codegraph_feedback.tools.dispatcher import FeedbackDispatcher


# ══════════════════════════════════════════════════════════════════════════
# resolve_feedback_file
# ══════════════════════════════════════════════════════════════════════════

class TestResolveFeedbackFile:
    """Feedback file resolution."""

    def test_resolve_by_known_slug(self, temp_requirements_dir):
        """HLR name with a known slug mapping."""
        result = resolve_feedback_file(
            "Architecture Diagram Generator — Unified Module View"
        )
        assert result is not None
        assert "01_unified_module_view.md" in result

    def test_resolve_unknown_returns_none(self, temp_requirements_dir):
        """HLR name with no mapping and no matching file."""
        result = resolve_feedback_file("Completely Unknown HLR Name")
        assert result is None

    def test_resolve_component_feedback(self, temp_requirements_dir):
        """Resolve per-component feedback.md by heading content match."""
        result = resolve_feedback_file(
            "Architecture Diagram Generator — Unified Module View"
        )
        assert result is not None
        # Both files have the same heading; the generated/feedback_docs/ one
        # is scanned first and wins.
        assert "feedback_docs" in result or "architecture-diagram-generator/feedback.md" in result


# ══════════════════════════════════════════════════════════════════════════
# parse_feedback_markdown
# ══════════════════════════════════════════════════════════════════════════

class TestParseFeedbackMarkdown:
    """Feedback markdown parsing."""

    def test_parse_extracts_hlr_name(self, temp_requirements_dir):
        result = parse_feedback_markdown(
            temp_requirements_dir["feedback_file"]
        )
        assert result["hlr_name"] == (
            "Architecture Diagram Generator — Unified Module View"
        )
        assert "PlantUML diagram" in result["hlr_description"]

    def test_parse_extracts_llrs(self, temp_requirements_dir):
        result = parse_feedback_markdown(
            temp_requirements_dir["feedback_file"]
        )
        assert "llrs" in result
        assert len(result["llrs"]) == 3

        llr1 = result["llrs"][0]
        assert llr1["name"] == "AG-LLR-01 — Fetch module subgraph via codegraph_query"
        assert llr1["has_feedback"] is True
        # Feedback text has newlines from markdown parsing
        assert "streaming" in llr1["feedback"]
        assert "modules" in llr1["feedback"]

    def test_parse_empty_feedback(self, temp_requirements_dir):
        result = parse_feedback_markdown(
            temp_requirements_dir["feedback_file"]
        )
        # AG-LLR-02 has only an HTML comment, no actual feedback
        llr2 = result["llrs"][1]
        assert llr2["name"] == "AG-LLR-02 — Concern classifier from namespace segment derivation"
        assert llr2["has_feedback"] is False
        assert llr2["feedback"] == ""

    def test_parse_nonexistent_file(self):
        result = parse_feedback_markdown("/nonexistent/path.md")
        assert "error" in result
        assert result["llrs"] == []


# ══════════════════════════════════════════════════════════════════════════
# write_draft
# ══════════════════════════════════════════════════════════════════════════

class TestWriteDraft:
    """Draft file writing."""

    def test_writes_memory_findings(self, temp_requirements_dir):
        memory_findings = [
            {
                "type": "decision",
                "qualified_name": "memory::test::use-streaming",
                "content": "We will stream modules one at a time to reduce memory.",
                "tags": ["design", "feedback"],
                "confidence": 0.85,
                "links_to": ["some::Class"],
                "rationale": "Feedback suggested streaming approach.",
                "parent_llr": "AG-LLR-01",
            },
        ]
        llr_context = {
            "AG-LLR-01": {"description": "Fetch module subgraph", "feedback": "streaming is better"},
        }
        path = write_draft(
            "architecture-diagram-generator",
            "Test HLR",
            memory_findings,
            [],
            llr_context=llr_context,
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "Feedback Analysis" in content
        assert "memory::test::use-streaming" in content
        assert "We will stream modules" in content
        assert "Type**: decision" in content
        assert "DRAFT" in content
        assert "## AG-LLR-01" in content
        assert "streaming is better" in content

    def test_writes_requirement_updates(self, temp_requirements_dir):
        requirement_updates = [
            {
                "target_name": "AG-LLR-01",
                "target_type": "LLR",
                "original_description": "Accept a namespace and query all modules.",
                "updated_description": "Accept a namespace and stream modules one at a time.",
                "rationale": "Feedback noted memory concerns with batch loading.",
            },
        ]
        llr_context = {
            "AG-LLR-01": {"description": "Fetch module subgraph", "feedback": ""},
        }
        path = write_draft(
            "architecture-diagram-generator",
            "Test HLR",
            [],
            requirement_updates,
            llr_context=llr_context,
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "## AG-LLR-01" in content
        assert "Requirement Updates" in content
        assert "stream modules" in content
        assert "**Original**" in content
        assert "**Proposed**" in content

    def test_writes_empty_draft(self, temp_requirements_dir):
        """Empty findings + empty updates should still produce a valid file."""
        path = write_draft(
            "test-component",
            "No Feedback HLR",
            [],
            [],
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "Feedback Analysis" in content
        assert "DRAFT" in content

    def test_writes_test_updates(self, temp_requirements_dir):
        """Test definition updates should appear in per-LLR sections."""
        test_updates = [
            {
                "target_name": "vm::configure::test_valid_threshold",
                "target_kind": "Test",
                "parent_llr": "AG-LLR-06",
                "change_type": "description",
                "original_text": "Invoke configure_min_entities with a non-negative integer.",
                "updated_text": "Invoke configure_min_entities with count=3 and verify the configuration is accepted.",
                "rationale": "Feedback requested more specific test descriptions.",
            },
            {
                "target_name": "cond::post::config_applied",
                "target_kind": "Assertion",
                "parent_llr": "AG-LLR-06",
                "change_type": "expected_value",
                "original_text": "config_applied is True",
                "updated_text": "min_entities equals 3",
                "rationale": "Feedback noted the assertion should check the actual value, not just a boolean.",
            },
        ]
        llr_context = {
            "AG-LLR-06": {"description": "Configure min entities", "feedback": "be more specific"},
        }
        path = write_draft(
            "architecture-diagram-generator",
            "Test HLR",
            [],
            [],
            test_updates,
            llr_context=llr_context,
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "## AG-LLR-06" in content
        assert "Test Definition Updates" in content
        assert "vm::configure::test_valid_threshold" in content
        assert "cond::post::config_applied" in content
        assert "Change type**: description" in content
        assert "Change type**: expected_value" in content
        assert "more specific test descriptions" in content


# ══════════════════════════════════════════════════════════════════════════
# handle_parse_feedback (via dispatcher)
# ══════════════════════════════════════════════════════════════════════════

class TestHandleParseFeedback:
    """Tool handler for parse_feedback."""

    def test_parse_with_explicit_path(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Test HLR",
            hlr_refid="test-refid",
            feedback_file_path=temp_requirements_dir["feedback_file"],
        )
        result = json.loads(disp.dispatch("parse_feedback", {}))
        assert result["hlr_name"] == (
            "Architecture Diagram Generator — Unified Module View"
        )
        assert len(result["llrs"]) == 3

    def test_parse_without_path_resolves(self, temp_requirements_dir):
        """When feedback_file_path is empty, it should try to resolve."""
        disp = FeedbackDispatcher(
            hlr_name="Architecture Diagram Generator — Unified Module View",
            hlr_refid="test-refid",
            feedback_file_path="",
        )
        result = json.loads(disp.dispatch("parse_feedback", {}))
        assert "error" not in result
        assert len(result["llrs"]) == 3

    def test_parse_populates_llr_feedback(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Test HLR",
            feedback_file_path=temp_requirements_dir["feedback_file"],
        )
        disp.dispatch("parse_feedback", {})
        assert len(disp.llr_feedback) == 3
        assert disp.llr_feedback["AG-LLR-01 — Fetch module subgraph via codegraph_query"]["has_feedback"] is True


# ══════════════════════════════════════════════════════════════════════════
# handle_propose_findings
# ══════════════════════════════════════════════════════════════════════════

class TestHandleProposeFindings:
    """Tool handler for propose_feedback_findings."""

    def test_propose_valid_findings(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Architecture Diagram Generator — Unified Module View",
            hlr_refid="test-refid",
            feedback_file_path=temp_requirements_dir["feedback_file"],
        )
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [
                {
                    "type": "decision",
                    "qualified_name": "memory::test::streaming",
                    "content": "Use streaming for large graphs.",
                    "tags": ["design", "feedback"],
                    "confidence": 0.9,
                    "links_to": ["some::Class"],
                },
            ],
            "requirement_updates": [],
        }))
        assert result["accepted"] is True
        assert result["memory_findings_count"] == 1
        assert "feedback_analysis.md" in result["draft_path"]

    def test_propose_invalid_memory_type(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Test HLR",
        )
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [
                {
                    "type": "invalid_type",
                    "qualified_name": "test",
                    "content": "test",
                },
            ],
            "requirement_updates": [],
        }))
        assert result["accepted"] is False
        assert len(result["errors"]) > 0

    def test_propose_missing_fields(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Test HLR",
        )
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [
                {
                    "type": "decision",
                    # missing qualified_name and content
                },
            ],
            "requirement_updates": [],
        }))
        assert result["accepted"] is False

    def test_propose_invalid_update_type(self, temp_requirements_dir):
        disp = FeedbackDispatcher(
            hlr_name="Test HLR",
        )
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [],
            "requirement_updates": [
                {
                    "target_name": "X",
                    "target_type": "INVALID",
                    "original_description": "old",
                    "updated_description": "new",
                },
            ],
        }))
        assert result["accepted"] is False

    def test_propose_valid_test_updates(self, temp_requirements_dir):
        """Test updates with valid fields should be accepted."""
        disp = FeedbackDispatcher(
            hlr_name="Architecture Diagram Generator — Unified Module View",
            hlr_refid="test-refid",
        )
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [],
            "requirement_updates": [],
            "test_updates": [
                {
                    "target_name": "vm::configure::test_valid_threshold",
                    "target_kind": "Test",
                    "parent_llr": "AG-LLR-06",
                    "change_type": "description",
                    "original_text": "old test description",
                    "updated_text": "new test description",
                    "rationale": "More specific.",
                },
            ],
        }))
        assert result["accepted"] is True
        assert result["test_updates_count"] == 1
        assert "feedback_analysis.md" in result["draft_path"]

    def test_propose_invalid_test_kind(self, temp_requirements_dir):
        """Invalid target_kind should be rejected."""
        disp = FeedbackDispatcher(hlr_name="Test HLR")
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [],
            "requirement_updates": [],
            "test_updates": [
                {
                    "target_name": "x",
                    "target_kind": "InvalidKind",
                    "change_type": "description",
                    "original_text": "old",
                    "updated_text": "new",
                },
            ],
        }))
        assert result["accepted"] is False

    def test_propose_invalid_change_type(self, temp_requirements_dir):
        """Invalid change_type should be rejected."""
        disp = FeedbackDispatcher(hlr_name="Test HLR")
        result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [],
            "requirement_updates": [],
            "test_updates": [
                {
                    "target_name": "x",
                    "target_kind": "Test",
                    "change_type": "nonexistent_field",
                    "original_text": "old",
                    "updated_text": "new",
                },
            ],
        }))
        assert result["accepted"] is False


# ══════════════════════════════════════════════════════════════════════════
# handle_commit_analysis
# ══════════════════════════════════════════════════════════════════════════

class TestHandleCommitAnalysis:
    """Terminal tool handler for commit_feedback_analysis."""

    def test_commit_no_draft(self, temp_requirements_dir):
        """Commit without a prior propose should fail."""
        disp = FeedbackDispatcher(hlr_name="Test HLR")
        result = json.loads(disp.dispatch("commit_feedback_analysis", {}))
        assert result["committed"] == 0
        assert "error" in result

    def test_commit_persists_memories(self, temp_requirements_dir):
        """Commit after propose should persist memory nodes."""
        disp = FeedbackDispatcher(
            hlr_name="Architecture Diagram Generator — Unified Module View",
            hlr_refid="test-refid",
        )

        # Propose
        prop_result = json.loads(disp.dispatch("propose_feedback_findings", {
            "memory_findings": [
                {
                    "type": "insight",
                    "qualified_name": "memory::feedback-test::dashed-edges",
                    "content": "Dashed lines are better for DEPENDS_ON per PlantUML spec.",
                    "tags": ["design", "feedback"],
                    "confidence": 0.9,
                },
            ],
            "requirement_updates": [],
        }))
        assert prop_result["accepted"] is True

        # Commit
        commit_result = json.loads(disp.dispatch("commit_feedback_analysis", {}))
        assert commit_result["committed"] == 1
        assert commit_result["total"] == 1
        assert len(commit_result["errors"]) == 0

        # Cleanup
        from codegraph_memory.models.insight import InsightNode
        try:
            node = InsightNode.nodes.get(
                qualified_name="memory::feedback-test::dashed-edges"
            )
            node.delete()
        except Exception:
            pass
