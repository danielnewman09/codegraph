"""Pipeline test: RequirementsLintAgent across v1/v2/v3 requirements.

Parametrized test that runs the lint agent against three versions of
the Database Migration Manager requirements with different contracts:

- v1: original requirements, no contract → expect "fail" (known gaps)
- v2: improved requirements, partial contract → expect "fail" (still gaps)
- v3: reconciled requirements + full contract, rollback spec still contradictory → expect "fail"
- v4: v3 with rollback/apply/verify edge cases resolved → expect "pass"/"warn"

Requires: storage backend (SQLite by default), LLM_API_KEY set in .env.
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

_THIS_DIR = Path(__file__).parent / "data" / "cpp_sqlite"


def _requires_openai():
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")


# ── Parametrized fixture ────────────────────────────────────────

_LINT_VARIANTS = [
    pytest.param(
        {
            "label": "v1",
            "requirements_md": "migration_manager_requirements.md",
            "contract_md": None,
            "expected_score": "fail",
            "expected_readiness": "not_ready",
            "min_blocking": 1,
            "min_total": 6,
            "min_blocking_plus_warn": 6,
            "required_categories": {
                "dangling_type",
                "unnamed_entity",
                "missing_edge_case",
            },
            "required_both_categories": {"dangling_type", "unnamed_entity"},
        },
        id="v1_original_no_contract",
    ),
    pytest.param(
        {
            "label": "v2",
            "requirements_md": "migration_manager_requirements_v2.md",
            "contract_md": "migration_manager_api_contract.md",
            "expected_score": "fail",
            "expected_readiness": "not_ready",
            "min_blocking": 1,
            "min_total": 4,
            "min_blocking_plus_warn": 3,
            "required_categories": {"missing_dependency"},
            "required_both_categories": set(),
        },
        id="v2_improved_partial_contract",
    ),
    pytest.param(
        {
            "label": "v3",
            "requirements_md": "migration_manager_requirements_v3.md",
            "contract_md": "migration_manager_api_contract_v3.md",
            "expected_score": "fail",
            "expected_readiness": "not_ready",
            "min_blocking": 1,
            "min_total": 0,
            "min_blocking_plus_warn": 0,
            "required_categories": set(),
            "required_both_categories": set(),
        },
        id="v3_reconciled_full_contract",
    ),
    pytest.param(
        {
            "label": "v4",
            "requirements_md": "migration_manager_requirements_v4.md",
            "contract_md": "migration_manager_api_contract_v4.md",
            "expected_score": {"pass", "warn"},
            "expected_readiness": {"ready", "needs_review"},
            "min_blocking": 0,
            "min_total": 0,
            "min_blocking_plus_warn": 0,
            "required_categories": set(),
            "required_both_categories": set(),
        },
        id="v4_clean_full_contract",
    ),
]


@pytest.fixture(scope="module", params=_LINT_VARIANTS)
def lint_variant(request):
    """Ingest a requirements + contract variant and return config.

    Yields a dict with hlr_uid, contract_path, expected_score,
    min_blocking, min_total, and label.
    """
    variant = request.param
    label: str = variant["label"]
    req_file: str = variant["requirements_md"]
    contract_file: str | None = variant["contract_md"]

    log = logging.getLogger(__name__)

    # ── Clean up any previous HLR with the same name ──
    from codegraph_requirements.models import HLR

    existing = list(HLR.nodes.filter(name="Database Migration Manager"))
    if existing:
        for hlr_node in existing:
            log.info("[%s] Deleting existing HLR: %s", label, hlr_node.uid[:16])
            hlr_node.delete()

    # ── Ingest requirements ──
    md_path = _THIS_DIR / req_file
    if not md_path.exists():
        pytest.skip(f"{label}: requirements not found: {md_path}")

    from codegraph.export.markdown import MarkdownImporter

    log.info("[%s] Ingesting requirements: %s", label, md_path)
    text = md_path.read_text(encoding="utf-8")
    importer = MarkdownImporter(
        tags=frozenset({"design"}), strict=False,
    )
    graph = importer.import_markdown(text)
    entries = list(graph._all_entries())
    log.info("[%s] Parsed %d entries", label, len(entries))
    graph.to_neo4j()

    # ── Find HLR ──
    hlrs = list(HLR.nodes.filter(name="Database Migration Manager"))
    assert len(hlrs) == 1, (
        f"[{label}] Expected exactly 1 HLR named 'Database Migration Manager', "
        f"got {len(hlrs)}: {[h.name for h in HLR.nodes.all()]}"
    )
    hlr_uid = hlrs[0].uid
    log.info("[%s] HLR uid: %s (name: %s)", label, hlr_uid[:16], hlrs[-1].name)

    # ── Contract path (optional) ──
    contract_path: str = ""
    if contract_file is not None:
        contract_path = str(_THIS_DIR / contract_file)
        if not Path(contract_path).exists():
            log.warning(
                "[%s] Contract not found: %s", label, contract_path,
            )
            contract_path = ""

    return {
        "label": label,
        "hlr_uid": hlr_uid,
        "contract_path": contract_path,
        "expected_score": variant["expected_score"],
        "expected_readiness": variant["expected_readiness"],
        "min_blocking": variant["min_blocking"],
        "min_total": variant["min_total"],
        "min_blocking_plus_warn": variant["min_blocking_plus_warn"],
        "required_categories": variant["required_categories"],
        "required_both_categories": variant["required_both_categories"],
    }


# ── Tests ────────────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.integration
class TestRequirementsLint:
    """Parametrized lint agent tests across v1/v2/v3/v4."""

    def test_requirements_ingested(self, lint_variant: dict) -> None:
        """Requirements fixture loaded and HLR uid returned."""
        assert len(lint_variant["hlr_uid"]) > 0

    def test_requirements_pass_lint(self, lint_variant: dict) -> None:
        """Run the lint agent and verify score/blocking counts.

        The assertions are calibrated per variant:
        - v1: known gaps, expect fail with blocking findings
        - v2: improved but still gaps
        - v3: full contract but rollback spec still contradictory, expect fail
        - v4: v3 with rollback/apply/verify edge cases resolved, expect pass/warn with zero blockers
        """
        log = logging.getLogger(__name__)
        _requires_openai()

        from codegraph_agents.requirements_lint import (
            RequirementsLintAgent,
        )
        from codegraph_agents.config import AgentConfig

        label = lint_variant["label"]
        expected_score = lint_variant["expected_score"]
        min_blocking = lint_variant["min_blocking"]
        min_total = lint_variant["min_total"]

        agent = RequirementsLintAgent(
            AgentConfig(
                hlr_uid=lint_variant["hlr_uid"],
                log_dir="codegraph/logs",
            ),
            api_contract_path=lint_variant["contract_path"],
        )

        report = agent.run()
        log.info(
            "[%s] Lint report: score=%s readiness=%s findings=%d",
            label, report.overall_score, report.readiness,
            len(report.findings),
        )

        # Log all findings for diagnostic visibility
        sev_order = {"blocking": 0, "warning": 1, "info": 2}
        for f in sorted(
            report.findings,
            key=lambda f: sev_order.get(f.severity, 99),
        ):
            log.warning(
                "[%s] Lint [%s] %s: %s → %s",
                label, f.severity, f.category,
                f.detail[:120], f.recommendation[:120],
            )

        blocking = [
            f for f in report.findings
            if f.severity == "blocking"
        ]
        warning = [
            f for f in report.findings
            if f.severity == "warning"
        ]
        total = len(report.findings)

        # ── Structure: every finding must be well-formed ──
        for i, f in enumerate(report.findings):
            assert f.severity in {"blocking", "warning", "info"}, (
                f"[{label}] findings[{i}].severity invalid: {f.severity}"
            )
            assert f.category, (
                f"[{label}] findings[{i}].category empty"
            )
            assert len(f.detail) > 10, (
                f"[{label}] findings[{i}].detail too short: {f.detail!r}"
            )
            assert len(f.recommendation) > 10, (
                f"[{label}] findings[{i}].recommendation too short: {f.recommendation!r}"
            )

        # ── Score assertion ──
        if isinstance(expected_score, str):
            assert report.overall_score == expected_score, (
                f"[{label}] Expected score '{expected_score}', "
                f"got '{report.overall_score}'. "
                f"Summary: {report.summary[:200]}"
            )
        else:
            # set of acceptable scores (e.g. {"pass", "warn"})
            assert report.overall_score in expected_score, (
                f"[{label}] Expected score in {expected_score}, "
                f"got '{report.overall_score}'. "
                f"Summary: {report.summary[:200]}"
            )

        # ── Blocking count assertion ──
        if min_blocking == 0:
            if blocking:
                lines = [
                    f"  [{f.severity}] {f.category}: {f.detail}\n"
                    f"    Fix: {f.recommendation}"
                    for f in blocking
                ]
                pytest.fail(
                    f"[{label}] Expected zero blocking findings, "
                    f"got {len(blocking)}:\n" + "\n".join(lines)
                )
        else:
            assert len(blocking) >= min_blocking, (
                f"[{label}] Expected >= {min_blocking} blocking "
                f"findings, got {len(blocking)}"
            )

        # ── Total findings assertion ──
        if min_total > 0:
            assert total >= min_total, (
                f"[{label}] Expected >= {min_total} findings, "
                f"got {total}"
            )

        # ── Combined blocking + warning ──
        min_combined = lint_variant["min_blocking_plus_warn"]
        if min_combined > 0:
            combined = len(blocking) + len(warning)
            assert combined >= min_combined, (
                f"[{label}] Expected >= {min_combined} "
                f"blocking+warn findings, got {combined}"
            )

        # ── Readiness ──
        expected_readiness = lint_variant["expected_readiness"]
        if isinstance(expected_readiness, str):
            assert report.readiness == expected_readiness, (
                f"[{label}] Expected readiness '{expected_readiness}', "
                f"got '{report.readiness}'"
            )
        else:
            assert report.readiness in expected_readiness, (
                f"[{label}] Expected readiness in {expected_readiness}, "
                f"got '{report.readiness}'"
            )

        # ── Required categories (at any severity) ──
        required_cats = lint_variant["required_categories"]
        if required_cats:
            all_categories = {f.category for f in report.findings}
            missing_cats = required_cats - all_categories
            assert not missing_cats, (
                f"[{label}] Missing required categories: {missing_cats}. "
                f"Present: {all_categories}"
            )

        # ── Required categories (both must be present) ──
        both_cats = lint_variant["required_both_categories"]
        if both_cats:
            all_categories = {f.category for f in report.findings}
            for cat in both_cats:
                assert cat in all_categories, (
                    f"[{label}] Required category '{cat}' not found. "
                    f"Present: {all_categories}"
                )

        log.info("[%s] Lint passed", label)
