"""Pipeline test: RequirementsLintAgent pre-check.

Runs the requirements-lint agent against the Database Migration
Manager requirements to verify they are sufficiently constrained
before passing them to the DesignAgent.

Requires: Neo4j running, LLM_API_KEY set in .env.
Skip with: ``pytest -m "not slow"``
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

import pytest

# Load .env from project root
_roots = [Path(__file__).resolve().parents[2]]
for root in _roots:
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        break


def _requires_openai():
    """Skip if no LLM API key is configured."""
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.integration
class TestRequirementsLint:
    """Pipeline test: RequirementsLintAgent pre-check."""

    def test_requirements_ingested(
        self, ingest_requirements: str,
    ) -> None:
        """Requirements fixture loaded and HLR uid returned."""
        assert len(ingest_requirements) > 0

    @pytest.mark.slow
    def test_requirements_pass_lint(
        self, ingest_requirements: str,
    ) -> None:
        """Requirements-lint agent produces a valid, consistent report.

        Verifies the agent's output structure and that it consistently
        detects the known issue categories in the current requirements.
        This tests agent *consistency* — not that the requirements are
        perfect (they have known gaps).

        When requirements are fixed, update the expected categories
        and score assertions below.
        """
        log = logging.getLogger(__name__)

        _requires_openai()

        from codegraph_agents.requirements_lint import (
            LintFinding,
            LintReport,
            RequirementsLintAgent,
        )
        from codegraph_agents.config import AgentConfig

        agent = RequirementsLintAgent(AgentConfig(
            hlr_uid=ingest_requirements,
            log_dir="codegraph/logs",
        ))

        report = agent.run()
        log.info(
            "Lint report: score=%s readiness=%s findings=%d",
            report.overall_score,
            report.readiness,
            len(report.findings),
        )

        # ── Structural assertions ────────────────────────────
        self._assert_report_structure(report)

        # ── Consistency assertions ───────────────────────────
        self._assert_expected_categories(report, log)

        # ── Log all findings for diagnostic visibility ───────
        sev_order = {"blocking": 0, "warning": 1, "info": 2}
        for f in sorted(
            report.findings,
            key=lambda f: sev_order.get(f.severity, 99),
        ):
            log.warning(
                "Lint [%s] %s: %s → %s",
                f.severity,
                f.category,
                f.detail[:120],
                f.recommendation[:120],
            )

    # ── Assertion helpers ────────────────────────────────────

    def _assert_report_structure(
        self, report: "LintReport",
    ) -> None:
        """Verify the lint report has valid field values."""
        assert report.overall_score in {"pass", "warn", "fail"}, (
            f"Invalid overall_score: '{report.overall_score}'"
        )
        assert report.readiness in {
            "ready", "needs_review", "not_ready",
        }, f"Invalid readiness: '{report.readiness}'"
        assert len(report.summary) > 20, (
            f"Summary too short ({len(report.summary)} chars)"
        )
        assert len(report.findings) >= 6, (
            f"Expected >= 6 findings, got {len(report.findings)}"
        )

        # No finding should have unknown/missing fields
        valid_sev = {"blocking", "warning", "info"}
        for i, f in enumerate(report.findings):
            assert f.severity in valid_sev, (
                f"Finding[{i}] has invalid severity: {f.severity}"
            )
            assert f.category, (
                f"Finding[{i}] has empty category"
            )
            assert len(f.detail) > 10, (
                f"Finding[{i}] detail too short"
            )
            assert len(f.recommendation) > 10, (
                f"Finding[{i}] recommendation too short"
            )

    def _assert_expected_categories(
        self,
        report: "LintReport",
        log: logging.Logger,
    ) -> None:
        """Verify the agent consistently detects the expected issue
        categories present in the current requirements.

        These are the stable categories observed across 4+ independent
        runs.  When the requirements are improved, update these sets.
        """
        categories = {f.category for f in report.findings}

        # Categories that MUST be detected (stable across all runs)
        required_categories = {
            "dangling_type",
            "unnamed_entity",
            "missing_attributes",
            "missing_edge_case",
        }
        missing = required_categories - categories
        assert not missing, (
            f"Lint agent missed expected categories: {sorted(missing)}. "
            f"All categories found: {sorted(categories)}"
        )

        # At least one finding (any severity) about the core
        # structural issues: dangling types AND unnamed entities.
        # These are the two most stable issue families across all
        # runs — if either goes missing, the agent has regressed.
        assert categories & {"dangling_type", "unnamed_entity"} == {
            "dangling_type", "unnamed_entity"
        }, (
            "Expected BOTH dangling_type and unnamed_entity "
            f"categories. Found: {sorted(categories)}"
        )

        # With current (incomplete) requirements, score should be
        # "fail" — not "warn" or "pass".  Across 4 independent runs
        # the agent consistently scored "fail" with 8-11 findings
        # and 4-5 blocking issues.
        assert report.overall_score == "fail", (
            f"Expected score 'fail' (current requirements have "
            f"known gaps), got '{report.overall_score}'. "
            f"If requirements were improved, update this assertion."
        )
        assert report.readiness == "not_ready", (
            f"Expected readiness 'not_ready', got "
            f"'{report.readiness}'"
        )

        # Minimum findings counts (lower bounds from observed runs)
        blocking_count = sum(
            1 for f in report.findings
            if f.severity == "blocking"
        )
        warn_count = sum(
            1 for f in report.findings
            if f.severity == "warning"
        )

        # Minimum findings counts (lower bounds from observed runs).
        # Total findings is stable (8-11). Blocking count varies 2-5
        # across runs because severity calibration drifts — the same
        # issues are found, just rated differently.
        assert len(report.findings) >= 8, (
            f"Expected >= 8 findings (observed 8-11), "
            f"got {len(report.findings)}"
        )
        assert blocking_count >= 2, (
            f"Expected >= 2 blocking findings (observed 2-5), "
            f"got {blocking_count}"
        )
        assert blocking_count + warn_count >= 6, (
            f"Expected >= 6 blocking+warnings combined "
            f"(observed 6-9), got {blocking_count + warn_count}"
        )

        log.info(
            "Categories detected: %s (required: %s)",
            sorted(categories),
            sorted(required_categories),
        )
        log.info(
            "Severity breakdown: blocking=%d warning=%d info=%d",
            sum(1 for f in report.findings if f.severity == "blocking"),
            sum(1 for f in report.findings if f.severity == "warning"),
            sum(1 for f in report.findings if f.severity == "info"),
        )
