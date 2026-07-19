"""Pipeline test: RequirementsLintAgent against improved v2 requirements.

Runs the lint agent against a version of the Database Migration
Manager requirements that has been fixed based on the lint agent's
own recommendations.  The improved requirements should score "pass"
or "warn" (no blocking findings).

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


# ── Fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ingest_requirements_v2():
    """Import the improved v2 requirements markdown.

    Returns the HLR uid.
    """
    import logging
    from tests.pipelines.conftest import PIPELINE_DATA_DIR

    log = logging.getLogger(__name__)

    md_path = PIPELINE_DATA_DIR / "migration_manager_requirements_v2.md"
    if not md_path.exists():
        pytest.skip(f"v2 requirements fixture not found: {md_path}")

    from codegraph.export.markdown import MarkdownImporter

    log.info("Ingesting v2 requirements fixture: %s", md_path)
    text = md_path.read_text(encoding="utf-8")
    importer = MarkdownImporter(
        tags=frozenset({"design"}), strict=False,
    )
    graph = importer.import_markdown(text)

    entries = list(graph._all_entries())
    log.info("Parsed %d entries from v2 requirements markdown", len(entries))

    graph.to_neo4j()
    log.info("Persisted %d entries to Neo4j (design)", len(entries))

    # Find the Database Migration Manager HLR
    from codegraph_requirements.models import HLR

    hlrs = list(HLR.nodes.filter(name="Database Migration Manager"))
    assert len(hlrs) == 1, (
        f"Expected 1 HLR named 'Database Migration Manager', "
        f"got {len(hlrs)}: {[h.name for h in HLR.nodes.all()]}"
    )
    hlr_uid = hlrs[0].uid
    log.info("HLR uid v2: %s (name: %s)", hlr_uid[:16], hlrs[0].name)
    return hlr_uid


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.integration
class TestRequirementsLintV2:
    """Pipeline test: RequirementsLintAgent against improved requirements.

    The v2 requirements apply fixes suggested by the lint agent:
    - Explicit MigrationManager class name
    - Defined Migration base class interface (version, up, down)
    - MigrationResult and MigrationErrorCode for error signaling
    - SchemaMismatch and MismatchKind for verification results
    - SchemaVerificationResult as verify() return type
    - Specified checksum algorithm and schema_versions lifecycle
    - Specified rollback edge cases
    - Removed uncovered DataAccessObject promise
    """

    def test_v2_requirements_ingested(
        self, ingest_requirements_v2: str,
    ) -> None:
        """V2 requirements fixture loaded and HLR uid returned."""
        assert len(ingest_requirements_v2) > 0

    @pytest.mark.slow
    def test_v2_requirements_pass_lint(
        self, ingest_requirements_v2: str,
    ) -> None:
        """Improved v2 requirements should score 'pass' or 'warn'.

        The fixes applied to v2 address all blocking issues from v1.
        The agent should find zero blocking findings.
        """
        log = logging.getLogger(__name__)

        _requires_openai()

        from codegraph_agents.requirements_lint import (
            RequirementsLintAgent,
        )
        from codegraph_agents.config import AgentConfig

        agent = RequirementsLintAgent(AgentConfig(
            hlr_uid=ingest_requirements_v2,
            log_dir="codegraph/logs",
        ))

        report = agent.run()
        log.info(
            "Lint v2 report: score=%s readiness=%s findings=%d",
            report.overall_score,
            report.readiness,
            len(report.findings),
        )

        # Log all findings for visibility
        sev_order = {"blocking": 0, "warning": 1, "info": 2}
        for f in sorted(
            report.findings,
            key=lambda f: sev_order.get(f.severity, 99),
        ):
            log.warning(
                "Lint v2 [%s] %s: %s → %s",
                f.severity,
                f.category,
                f.detail[:120],
                f.recommendation[:120],
            )

        # ── V2 assertions: improved requirements should have ──
        #     no blocking findings and score pass or warn.

        blocking = [
            f for f in report.findings
            if f.severity == "blocking"
        ]

        if blocking:
            # Log the blockers for diagnostic visibility before
            # failing — they indicate the v2 fixes are incomplete
            # or the agent is being overly aggressive.
            lines = [
                f"  [{f.severity}] {f.category}: {f.detail}\n"
                f"    Fix: {f.recommendation}"
                for f in blocking
            ]
            pytest.fail(
                f"V2 requirements should have zero blocking findings, "
                f"but found {len(blocking)}:\n" + "\n".join(lines)
            )

        assert report.overall_score in {"pass", "warn"}, (
            f"V2 requirements should score 'pass' or 'warn', "
            f"got '{report.overall_score}'. "
            f"Summary: {report.summary[:200]}"
        )
        assert report.readiness in {"ready", "needs_review"}, (
            f"V2 readiness should be 'ready' or 'needs_review', "
            f"got '{report.readiness}'"
        )

        log.info("V2 lint passed: %s / %s", report.overall_score, report.readiness)
