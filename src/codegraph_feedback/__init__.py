"""Codegraph-Feedback — analyze human design feedback and derive
memory findings + requirement updates.

Extends the codegraph design pipeline: after human reviewers fill in
feedback on generated feedback docs, this package analyzes those
comments and produces:

1. **Memory findings** (DecisionNodes, ConstraintNodes, InsightNodes,
   AssumptionNodes, TradeoffNodes, RationaleNodes) persisted to Neo4j
   and linked to relevant code, HLR, and LLR nodes.

2. **Requirement update drafts** written to
   ``codegraph/requirements/<component-slug>/feedback_analysis.md``
   for human review before ingestion.

Usage::

    from codegraph_feedback import analyze_feedback, analyze_and_persist

    # One-shot: load HLR, resolve feedback file, analyze
    result = analyze_and_persist(hlr_uid="2c3463b2…")

    # Or with explicit paths
    result = analyze_feedback(
        hlr_name="Architecture Diagram Generator — Unified Module View",
        hlr_uid="2c3463b2…",
        feedback_file_path="codegraph/requirements/generated/feedback_docs/01_unified_module_view.md",
    )

    print(f"Created {result.memories_committed} memory nodes")
    print(f"Drafted {len(result.requirement_updates)} requirement updates")
    print(f"Draft: {result.draft_path}")
"""

from codegraph_feedback.agents.analyze_feedback import (
    analyze_feedback,
    analyze_and_persist,
    FeedbackAnalysisResult,
)
from codegraph_feedback.tools.dispatcher import FeedbackDispatcher
from codegraph_feedback.tools.feedback_tools import (
    resolve_feedback_file,
    parse_feedback_markdown,
    write_draft,
)

__all__ = [
    "analyze_feedback",
    "analyze_and_persist",
    "FeedbackAnalysisResult",
    "FeedbackDispatcher",
    "resolve_feedback_file",
    "parse_feedback_markdown",
    "write_draft",
]
