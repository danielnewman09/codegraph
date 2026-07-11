"""Feedback analysis dispatcher — extends DesignDiscoveryDispatcher with
feedback-specific tools for parsing feedback docs, proposing memory
findings, and drafting requirement updates.

Three dispatcher classes:

- :class:`FeedbackDispatcher` — extends DesignDiscoveryDispatcher (which
  itself extends CodeGraphDispatcher) with feedback analysis tools. The
  agent tool loop uses this dispatcher to handle exploration tools
  (inherited from codegraph + discovery) and feedback tools.

The dispatcher holds mutable state for the active analysis session:
feedback file path, parsed LLR feedback, draft findings, and output
path.
"""

from __future__ import annotations

from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher


class FeedbackDispatcher(DesignDiscoveryDispatcher):
    """Dispatcher for feedback analysis tools.

    Inherits all tools from :class:`DesignDiscoveryDispatcher` (27 tools:
    22 codegraph query/lookup/discovery + 5 requirements discovery +
    workflow tools) and adds feedback-specific tools on top.

    Holds mutable context for the active analysis session.

    Usage::

        d = FeedbackDispatcher(
            hlr_name="Architecture Diagram Generator — Unified Module View",
            hlr_uid="2c3463b2…",
            feedback_file_path="codegraph/requirements/generated/feedback_docs/01_unified_module_view.md",
            component_name="architecture-diagram-generator",
        )

        # Agent calls exploration tools + feedback tools
        schemas = d.all_tool_schemas
        result = d.dispatch("parse_feedback", {})
        result = d.dispatch("propose_feedback_findings", {...})
    """

    def __init__(
        self,
        repo=None,
        *,
        hlr_name: str = "",
        hlr_uid: str = "",
        feedback_file_path: str = "",
        component_name: str = "",
        **kwargs,
    ):
        super().__init__(repo=repo, **kwargs)

        # ── Session state ──
        self.hlr_name: str = hlr_name
        self.hlr_uid: str = hlr_uid
        self.feedback_file_path: str = feedback_file_path
        self.component_name: str = component_name

        # ── Parsed feedback (populated by parse_feedback) ──
        self.llr_feedback: dict[str, dict] = {}

        # ── Draft state (populated by propose_feedback_findings) ──
        self.draft_memory_findings: list[dict] | None = None
        self.draft_requirement_updates: list[dict] | None = None
        self.draft_output_path: str = ""

        # Register feedback tools on top of discovery tools
        from codegraph_feedback.tools.feedback_tools import register_all as _reg
        _reg(self)
