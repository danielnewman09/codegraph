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
        """Requirements pass the lint agent pre-check.

        Runs the RequirementsLintAgent to verify that the HLR + LLRs
        are sufficiently constrained.  Blocking findings fail the test
        with actionable recommendations.
        """
        log = logging.getLogger(__name__)

        _requires_openai()

        from codegraph_agents.requirements_lint import (
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

        # Log all findings for visibility
        for f in report.findings:
            log.warning(
                "Lint [%s] %s: %s → %s",
                f.severity,
                f.category,
                f.detail,
                f.recommendation[:80],
            )

        # Blocking findings fail the test
        blocking = [
            f for f in report.findings
            if f.severity == "blocking"
        ]
        if blocking:
            lines = [
                f"  [{f.severity}] {f.category}: {f.detail}\n"
                f"    Fix: {f.recommendation}"
                for f in blocking
            ]
            pytest.fail(
                f"Requirements lint found {len(blocking)} "
                f"blocking issue(s):\n" + "\n".join(lines)
            )

        # Warning findings are logged but don't fail
        warnings = [
            f for f in report.findings
            if f.severity == "warning"
        ]
        if warnings:
            log.warning(
                "Requirements lint found %d warning(s)",
                len(warnings),
            )

        # Assert no critical failures
        assert report.overall_score != "fail", (
            f"Requirements scored 'fail'. "
            f"Summary: {report.summary}"
        )
