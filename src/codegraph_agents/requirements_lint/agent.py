"""RequirementsLintAgent — pre-design requirements quality check.

Evaluates whether HLR + LLR requirements are sufficiently constrained
to produce a deterministic design.  Run this BEFORE the DesignAgent
to catch underspecified requirements that cause non-deterministic output.

Usage::

    from codegraph_agents.requirements_lint import RequirementsLintAgent
    from codegraph_agents.config import AgentConfig

    agent = RequirementsLintAgent(AgentConfig(
        hlr_uid="abc123def456",
        log_dir="codegraph/logs",
    ))
    result = agent.run()  # → LintReport(score="pass", findings=[...])
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from codegraph_agents.base import BaseAgent
from codegraph_agents.config import AgentConfig
from codegraph_agents.state import AgentState

log = logging.getLogger("codegraph_agents.requirements_lint")


# ── Result dataclass ─────────────────────────────────────────────


@dataclass
class LintFinding:
    """A single finding from the requirements lint analysis."""

    severity: str  # blocking, warning, info
    category: str  # unnamed_entity, missing_attributes, etc.
    location: str  # Which LLR/HLR section
    detail: str    # What is missing
    recommendation: str  # How to fix


@dataclass
class LintReport:
    """Output of :meth:`RequirementsLintAgent.run`."""

    overall_score: str = "warn"
    """pass, warn, or fail."""

    summary: str = ""
    """One-paragraph summary of the assessment."""

    findings: list[LintFinding] = field(default_factory=list)
    """Individual findings."""

    readiness: str = "needs_review"
    """ready, needs_review, or not_ready."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors encountered during the run."""


# ── Minimal dispatcher — just the produce_lint_report tool ───────


class _LintDispatcher:
    """Minimal dispatcher with a single tool: ``produce_lint_report``.

    Unlike the design agent which has a complex composite dispatcher,
    the lint agent only needs one tool to receive the structured report.
    """

    def __init__(self) -> None:
        self._report: dict[str, Any] | None = None

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "produce_lint_report":
            return self._handle_produce_lint_report(tool_input)
        return json.dumps({
            "error": f"Unknown tool: {tool_name}",
            "available": ["produce_lint_report"],
        })

    def _handle_produce_lint_report(
        self, tool_input: dict
    ) -> str:
        # Validate required fields
        required = {"overall_score", "summary", "findings", "readiness"}
        missing = required - set(tool_input.keys())
        if missing:
            return json.dumps({
                "valid": False,
                "error": f"Missing required fields: {sorted(missing)}",
                "required_fields": sorted(required),
            })

        # Validate score
        if tool_input["overall_score"] not in ("pass", "warn", "fail"):
            return json.dumps({
                "valid": False,
                "error": (
                    f"Invalid overall_score: "
                    f"'{tool_input['overall_score']}'. "
                    f"Must be pass, warn, or fail."
                ),
            })

        # Validate findings structure
        findings = tool_input.get("findings", [])
        if not isinstance(findings, list):
            return json.dumps({
                "valid": False,
                "error": "findings must be a list",
            })

        valid_severities = {"blocking", "warning", "info"}
        valid_categories = {
            "unnamed_entity",
            "missing_attributes",
            "dangling_type",
            "naming_inconsistency",
            "missing_dependency",
            "missing_edge_case",
            "incomplete_coverage",
        }
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                return json.dumps({
                    "valid": False,
                    "error": f"findings[{i}] is not an object",
                })
            sev = f.get("severity", "")
            if sev not in valid_severities:
                return json.dumps({
                    "valid": False,
                    "error": (
                        f"findings[{i}].severity '{sev}' invalid. "
                        f"Must be one of {sorted(valid_severities)}"
                    ),
                })
            cat = f.get("category", "")
            if cat not in valid_categories:
                return json.dumps({
                    "valid": False,
                    "error": (
                        f"findings[{i}].category '{cat}' invalid. "
                        f"Must be one of {sorted(valid_categories)}"
                    ),
                })

        self._report = tool_input
        return json.dumps({
            "valid": True,
            "findings_count": len(findings),
            "blocking": sum(
                1 for f in findings if f.get("severity") == "blocking"
            ),
            "warnings": sum(
                1 for f in findings if f.get("severity") == "warning"
            ),
            "info": sum(
                1 for f in findings if f.get("severity") == "info"
            ),
        })

    @property
    def all_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "produce_lint_report",
                "description": (
                    "Submit the requirements lint report. "
                    "Call this when your analysis is complete."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "overall_score": {
                            "type": "string",
                            "enum": ["pass", "warn", "fail"],
                            "description": "Overall quality score",
                        },
                        "summary": {
                            "type": "string",
                            "description": "One-paragraph summary",
                        },
                        "findings": {
                            "type": "array",
                            "description": "List of findings",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "severity": {
                                        "type": "string",
                                        "enum": [
                                            "blocking",
                                            "warning",
                                            "info",
                                        ],
                                    },
                                    "category": {
                                        "type": "string",
                                        "enum": [
                                            "unnamed_entity",
                                            "missing_attributes",
                                            "dangling_type",
                                            "naming_inconsistency",
                                            "missing_dependency",
                                            "missing_edge_case",
                                            "incomplete_coverage",
                                        ],
                                    },
                                    "location": {
                                        "type": "string",
                                        "description": (
                                            "Which LLR or HLR section"
                                        ),
                                    },
                                    "detail": {"type": "string"},
                                    "recommendation": {"type": "string"},
                                },
                                "required": [
                                    "severity",
                                    "category",
                                    "location",
                                    "detail",
                                    "recommendation",
                                ],
                            },
                        },
                        "readiness": {
                            "type": "string",
                            "enum": ["ready", "needs_review", "not_ready"],
                            "description": "Whether to proceed to design",
                        },
                    },
                    "required": [
                        "overall_score",
                        "summary",
                        "findings",
                        "readiness",
                    ],
                },
            },
        ]


# ── RequirementsLintAgent ────────────────────────────────────────


def _import_system_prompt():
    from codegraph_agents.requirements_lint.prompts import (
        SYSTEM_PROMPT_TEMPLATE,
    )
    return SYSTEM_PROMPT_TEMPLATE


class RequirementsLintAgent(BaseAgent):
    """Pre-design requirements quality check.

    Loads the HLR subtree (HLR → LLRs → tests) and evaluates whether
    the requirements are sufficiently constrained to produce a
    deterministic design.

    Lifecycle::

        agent = RequirementsLintAgent(AgentConfig(hlr_uid="abc123"))
        report = agent.run()
        # → LintReport(score="warn", findings=[...])

    If ``report.overall_score == "fail"``, fix the requirements before
    running the DesignAgent.
    """

    name: ClassVar[str] = "requirements_lint"

    system_prompt = _import_system_prompt()

    context_needs: ClassVar[set[str]] = {"hlr_subtree"}

    final_tool_name: ClassVar[str] = "produce_lint_report"

    # ── Dispatch ─────────────────────────────────────────────────

    def _create_dispatcher(self) -> _LintDispatcher:
        return _LintDispatcher()

    # ── Context loading ──────────────────────────────────────────

    def load_context(self) -> dict[str, Any]:
        """Load the HLR subtree context."""
        return super().load_context()

    # ── Initial messages ─────────────────────────────────────────

    def build_initial_messages(
        self, context: dict[str, Any]
    ) -> list[BaseMessage]:
        """Build the initial message with the full requirements text.

        Formats the HLR and all LLRs (with their tests and
        assertions) into a single human-readable prompt so the
        LLM can analyze everything in one pass.
        """
        hlr_tree = context.get("hlr_subtree", {})
        hlr = hlr_tree.get("hlr")
        llrs = hlr_tree.get("llrs", [])
        notional = hlr_tree.get("notional_verifications", [])
        design_compounds = hlr_tree.get("design_compounds", [])

        # Index notional verifications by test_uid for filtering
        tests_by_uid: dict[str, dict] = {
            nv["test_uid"]: nv for nv in notional
        }

        parts: list[str] = []

        # ── HLR ──
        if hlr is not None:
            hlr_name = getattr(hlr, "name", "") or "Unnamed HLR"
            hlr_desc = getattr(hlr, "description", "") or ""
            hlr_qn = getattr(hlr, "qualified_name", "") or ""
            parts.append(f"## HLR: {hlr_name}")
            if hlr_qn:
                parts.append(f"  qualified_name: {hlr_qn}")
            if hlr_desc:
                parts.append(f"\n{hlr_desc}\n")

        # ── LLRs ──
        if llrs:
            parts.append(f"## LLRs ({len(llrs)} total)\n")
            for llr in llrs:
                llr_name = (
                    getattr(llr, "name", "") or "Unnamed LLR"
                )
                llr_desc = getattr(llr, "description", "") or ""
                llr_uid = getattr(llr, "uid", "") or ""
                parts.append(f"### LLR: {llr_name}")
                if llr_uid:
                    parts.append(f"  uid: {llr_uid[:8]}")
                if llr_desc:
                    parts.append(f"\n{llr_desc}\n")

                # Tests for this LLR — traverse verification_methods
                verif_methods = (
                    list(llr.verification_methods.all())
                    if hasattr(llr, "verification_methods")
                    else []
                )
                if verif_methods:
                    parts.append(
                        f"  Tests ({len(verif_methods)}):"
                    )
                    for test in verif_methods:
                        test_name = (
                            getattr(test, "test_name", "")
                            or getattr(test, "name", "")
                            or ""
                        )
                        test_desc = (
                            getattr(test, "description", "")
                            or ""
                        )
                        parts.append(f"    - {test_name}")
                        if test_desc:
                            parts.append(f"      {test_desc}")

                        # Steps
                        steps = (
                            list(test.steps.all())
                            if hasattr(test, "steps")
                            else []
                        )
                        if steps:
                            parts.append(
                                f"      Steps ({len(steps)}):"
                            )
                            for s in steps:
                                step_desc = (
                                    getattr(s, "description", "")
                                    or ""
                                )
                                callee = (
                                    getattr(
                                        s,
                                        "callee_qualified_name",
                                        "",
                                    )
                                    or ""
                                )
                                line = f"        - {step_desc}"
                                if callee:
                                    line += f" → {callee}"
                                parts.append(line)

                        # Assertions
                        assertions = (
                            list(test.assertions.all())
                            if hasattr(test, "assertions")
                            else []
                        )
                        if assertions:
                            parts.append(
                                f"      Assertions "
                                f"({len(assertions)}):"
                            )
                            for a in assertions:
                                subj = (
                                    getattr(
                                        a,
                                        "subject_qualified_name",
                                        "",
                                    )
                                    or ""
                                )
                                oper = (
                                    getattr(a, "operator", "")
                                    or "=="
                                )
                                exp = (
                                    getattr(
                                        a, "expected_value", ""
                                    )
                                    or ""
                                )
                                parts.append(
                                    f"        - {subj} "
                                    f"{oper} {exp}"
                                )
                parts.append("")

        # ── Existing design compounds ──
        if design_compounds:
            parts.append(
                f"## Existing design compounds "
                f"({len(design_compounds)})\n"
            )
            for dc in design_compounds:
                qn = dc.get("qualified_name", "")
                name = dc.get("name", "")
                kind = dc.get("kind", "class")
                parts.append(f"  - {kind}: {name} ({qn})")

        # ── Instruction ──
        parts.append(
            "\nAnalyze these requirements for completeness "
            "and specificity.  Identify gaps that would force "
            "a downstream design agent to invent details.  "
            "When your analysis is complete, call "
            "`produce_lint_report` with your findings."
        )

        return [HumanMessage(content="\n".join(parts))]

    # ── Result extraction ────────────────────────────────────────

    def build_result(self, state: AgentState) -> LintReport:
        """Extract the lint report from the produce_lint_report output."""
        result_data = self._extract_final_tool_output(
            state, "produce_lint_report"
        )
        errors: list[str] = []

        if result_data is None:
            return LintReport(
                overall_score="fail",
                summary="Agent did not produce a lint report.",
                readiness="not_ready",
                errors=[
                    "No produce_lint_report output found in message history"
                ],
            )

        findings = []
        for f in result_data.get("findings", []):
            findings.append(LintFinding(
                severity=f.get("severity", "warning"),
                category=f.get("category", "unknown"),
                location=f.get("location", ""),
                detail=f.get("detail", ""),
                recommendation=f.get("recommendation", ""),
            ))

        return LintReport(
            overall_score=result_data.get("overall_score", "warn"),
            summary=result_data.get("summary", ""),
            findings=findings,
            readiness=result_data.get("readiness", "needs_review"),
            errors=errors,
        )
