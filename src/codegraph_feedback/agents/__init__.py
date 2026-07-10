"""Feedback analysis agents — derive memories and requirement updates
from human feedback on design documents.

Provides:

* :func:`analyze_feedback` — analyze feedback for an HLR, deriving memory
  findings (decisions, constraints, insights, assumptions, tradeoffs,
  rationales) and requirement updates (proposed changes to HLR/LLR
  descriptions).
* :func:`analyze_and_persist` — full end-to-end: load HLR from Neo4j →
  resolve feedback file → analyze → write drafts → optionally persist.
* :class:`FeedbackAnalysisResult` — result of the analysis pipeline.
"""

from codegraph_feedback.agents.analyze_feedback import (
    analyze_feedback,
    analyze_and_persist,
    FeedbackAnalysisResult,
)

__all__ = [
    "analyze_feedback",
    "analyze_and_persist",
    "FeedbackAnalysisResult",
]
