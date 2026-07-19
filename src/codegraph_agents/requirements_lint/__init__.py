"""Requirements lint agent — pre-design requirements quality check.

Evaluates whether HLR + LLR requirements are sufficiently constrained
to produce a deterministic design.  Run this BEFORE the DesignAgent
to catch underspecified requirements.

Usage::

    from codegraph_agents.requirements_lint import (
        RequirementsLintAgent,
        LintReport,
        LintFinding,
    )
    from codegraph_agents.config import AgentConfig

    agent = RequirementsLintAgent(AgentConfig(hlr_uid="abc123"))
    report = agent.run()

    if report.overall_score == "fail":
        for f in report.findings:
            print(f"[{f.severity}] {f.category}: {f.detail}")
        raise SystemExit("Fix requirements before designing")
"""

from codegraph_agents.requirements_lint.agent import (
    RequirementsLintAgent,
    LintReport,
    LintFinding,
)

__all__ = [
    "RequirementsLintAgent",
    "LintReport",
    "LintFinding",
]
