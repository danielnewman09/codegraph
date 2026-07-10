"""Agent that analyzes human feedback on design documents and derives
memory findings and requirement updates.

Uses ``llm_caller.call_tool_loop`` for multi-turn exploration of the
codegraph and memory store before committing findings.

Usage::

    from codegraph_feedback.agents.analyze_feedback import analyze_and_persist

    result = analyze_and_persist(
        hlr_refid="2c3463b2…",
        log_dir="/path/to/logs",
    )
    # → FeedbackAnalysisResult(memories_created=3, updates_drafted=2)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_caller import call_tool_loop

from codegraph_feedback.agents.prompts import SYSTEM_PROMPT
from codegraph_feedback.tools.dispatcher import FeedbackDispatcher
from codegraph_feedback.tools.feedback_tools import (
    resolve_feedback_file,
    parse_feedback_markdown,
)

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Result types
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class FeedbackAnalysisResult:
    """Result of analyzing feedback for an HLR.

    Attributes:
        hlr_name: The HLR name.
        hlr_refid: The HLR's Neo4j refid.
        feedback_file: Path to the feedback markdown file.
        memory_findings: List of memory finding proposals.
        requirement_updates: List of requirement description update proposals.
        test_updates: List of test definition update proposals.
        draft_path: Path to the written draft markdown file.
        memories_committed: Number of memory nodes persisted to Neo4j.
        errors: Non-fatal error messages during the run.
    """

    hlr_name: str = ""
    hlr_refid: str = ""
    feedback_file: str = ""
    memory_findings: list[dict[str, Any]] = field(default_factory=list)
    requirement_updates: list[dict[str, Any]] = field(default_factory=list)
    test_updates: list[dict[str, Any]] = field(default_factory=list)
    draft_path: str = ""
    memories_committed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if the analysis produced at least one finding or update."""
        return (
            len(self.memory_findings)
            + len(self.requirement_updates)
            + len(self.test_updates)
        ) > 0

    def to_dict(self) -> dict:
        return {
            "hlr_name": self.hlr_name,
            "hlr_refid": self.hlr_refid,
            "feedback_file": self.feedback_file,
            "memory_findings_count": len(self.memory_findings),
            "requirement_updates_count": len(self.requirement_updates),
            "test_updates_count": len(self.test_updates),
            "draft_path": self.draft_path,
            "memories_committed": self.memories_committed,
            "errors": self.errors,
        }


# ══════════════════════════════════════════════════════════════════════════
# Agent
# ══════════════════════════════════════════════════════════════════════════


def analyze_feedback(
    hlr_name: str,
    hlr_refid: str,
    feedback_file_path: str,
    *,
    component_name: str = "",
    model: str = "",
    max_tokens: int = 32768,
    max_turns: int = 15,
    log_dir: str | None = None,
) -> FeedbackAnalysisResult:
    """Run the feedback analysis agent for a single HLR.

    The agent uses a multi-turn tool loop to:
    1. Parse the feedback file to extract human comments
    2. Explore the codegraph and memory store for context
    3. Propose memory findings and requirement updates
    4. Commit memory findings to Neo4j

    Args:
        hlr_name: The HLR name (used for feedback file resolution).
        hlr_refid: The HLR's uid in Neo4j.
        feedback_file_path: Path to the feedback markdown file.
        component_name: Optional component name for context.
        model: LLM model override.
        max_tokens: Maximum response tokens.
        max_turns: Maximum tool loop turns.
        log_dir: Optional directory for prompt trace logs.

    Returns:
        A :class:`FeedbackAnalysisResult`.
    """
    result = FeedbackAnalysisResult(
        hlr_name=hlr_name,
        hlr_refid=hlr_refid,
        feedback_file=feedback_file_path,
    )

    # ── Validate feedback file ──────────────────────────────────
    if not feedback_file_path or not os.path.exists(feedback_file_path):
        # Try to resolve
        resolved = resolve_feedback_file(hlr_name)
        if resolved:
            feedback_file_path = resolved
            result.feedback_file = resolved
        else:
            result.errors.append(
                f"No feedback file found for HLR '{hlr_name}'"
            )
            return result

    # Parse feedback to verify it has content
    parsed = parse_feedback_markdown(feedback_file_path)
    if parsed.get("error"):
        result.errors.append(parsed["error"])
        return result

    llrs_with_feedback = [
        llr for llr in parsed.get("llrs", []) if llr.get("has_feedback")
    ]
    if not llrs_with_feedback:
        result.errors.append(
            f"No LLRs with substantive feedback found in {feedback_file_path}.  "
            f"All feedback sections are empty."
        )
        return result

    # ── Build dispatcher ─────────────────────────────────────────
    dispatcher = FeedbackDispatcher(
        hlr_name=hlr_name,
        hlr_refid=hlr_refid,
        feedback_file_path=feedback_file_path,
        component_name=component_name,
    )

    # ── Build initial message ───────────────────────────────────
    feedback_summary = _format_feedback_summary(parsed, llrs_with_feedback)
    initial_message = _build_initial_message(
        hlr_name=hlr_name,
        hlr_refid=hlr_refid,
        feedback_file_path=feedback_file_path,
        hlr_description=parsed.get("hlr_description", ""),
        feedback_summary=feedback_summary,
        llrs_with_feedback=llrs_with_feedback,
    )

    # ── Collect tool schemas ────────────────────────────────────
    # All tools from the dispatcher (codegraph + discovery + feedback)
    all_tool_schemas = dispatcher.all_tool_schemas

    # Terminal tool name for the tool loop
    final_tool_name = "commit_feedback_analysis"

    # ── Prompt log file ─────────────────────────────────────────
    prompt_log_file = ""
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        safe_name = hlr_name.replace(" ", "_").replace("—", "-")[:60]
        prompt_log_file = str(
            log_path / f"feedback_analyze_{safe_name}_{ts}.md"
        )

    # ── Call the agent ──────────────────────────────────────────
    log.info(
        "Starting feedback analysis for HLR '%s' (%d LLRs with feedback, %d tools)",
        hlr_name, len(llrs_with_feedback), len(all_tool_schemas),
    )

    try:
        tool_result = call_tool_loop(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": initial_message}],
            tools=all_tool_schemas,
            final_tool_name=final_tool_name,
            tool_dispatcher=lambda name, inp: dispatcher.dispatch(name, inp),
            model=model,
            max_tokens=max_tokens,
            max_turns=max_turns,
            prompt_log_file=prompt_log_file,
        )
    except Exception as exc:
        result.errors.append(f"Agent tool loop failed: {exc}")
        log.exception("Feedback analysis tool loop failed")
        return result

    # ── Extract results from dispatcher state ───────────────────
    result.memory_findings = dispatcher.draft_memory_findings or []
    result.requirement_updates = dispatcher.draft_requirement_updates or []
    result.test_updates = getattr(dispatcher, "draft_test_updates", None) or []
    result.draft_path = dispatcher.draft_output_path

    # Count committed memories (commit happens in the tool loop)
    try:
        if isinstance(tool_result, dict):
            result.memories_committed = tool_result.get("committed", 0)
    except Exception:
        pass

    return result


def analyze_and_persist(
    hlr_refid: str,
    *,
    feedback_file_path: str = "",
    model: str = "",
    max_tokens: int = 32768,
    max_turns: int = 15,
    log_dir: str | None = None,
) -> FeedbackAnalysisResult:
    """Full end-to-end: load HLR from Neo4j → resolve feedback file → analyze.

    Args:
        hlr_refid: The HLR's uid in Neo4j.
        feedback_file_path: Optional path to the feedback markdown file.
            If omitted, the file is resolved automatically from the HLR name.
        model: LLM model override.
        max_tokens: Maximum response tokens.
        max_turns: Maximum tool loop turns.
        log_dir: Optional directory for prompt trace logs.

    Returns:
        A :class:`FeedbackAnalysisResult`.
    """
    # ── Load HLR from Neo4j ─────────────────────────────────────
    from neomodel import db

    try:
        results, _ = db.cypher_query(
            "MATCH (hlr:HLR) WHERE hlr.uid = $refid "
            "RETURN hlr.name AS name, hlr.description AS description, "
            "hlr.uid AS uid",
            {"refid": hlr_refid},
        )
        if not results:
            return FeedbackAnalysisResult(
                hlr_refid=hlr_refid,
                errors=[f"HLR not found with refid: {hlr_refid}"],
            )
        row = results[0]
        hlr_name = row[0] or ""
        hlr_description = row[1] or ""
    except Exception as exc:
        return FeedbackAnalysisResult(
            hlr_refid=hlr_refid,
            errors=[f"Failed to load HLR from Neo4j: {exc}"],
        )

    # ── Resolve component name ──────────────────────────────────
    component_name = ""
    try:
        comp_results, _ = db.cypher_query(
            "MATCH (c)-[:COMPOSES]->(hlr:HLR) WHERE hlr.uid = $refid "
            "RETURN c.name AS name LIMIT 1",
            {"refid": hlr_refid},
        )
        if comp_results:
            component_name = comp_results[0][0] or ""
    except Exception:
        pass

    # ── Resolve feedback file ───────────────────────────────────
    if not feedback_file_path:
        feedback_file_path = resolve_feedback_file(hlr_name) or ""
        if not feedback_file_path:
            return FeedbackAnalysisResult(
                hlr_name=hlr_name,
                hlr_refid=hlr_refid,
                errors=[
                    f"Could not resolve feedback file for HLR '{hlr_name}'.  "
                    f"Provide feedback_file_path explicitly or ensure the file "
                    f"exists under codegraph/requirements/generated/feedback_docs/ "
                    f"or codegraph/requirements/<component-slug>/."
                ],
            )

    return analyze_feedback(
        hlr_name=hlr_name,
        hlr_refid=hlr_refid,
        feedback_file_path=feedback_file_path,
        component_name=component_name,
        model=model,
        max_tokens=max_tokens,
        max_turns=max_turns,
        log_dir=log_dir,
    )


# ══════════════════════════════════════════════════════════════════════════
# Prompt building
# ══════════════════════════════════════════════════════════════════════════


def _format_feedback_summary(
    parsed: dict[str, Any],
    llrs_with_feedback: list[dict[str, Any]],
) -> str:
    """Format the parsed feedback into a compact summary for the prompt."""
    lines = []
    for llr in llrs_with_feedback:
        lines.append(f"### {llr['name']}")
        if llr.get("description"):
            lines.append(f"Description: {llr['description'][:200]}")
        lines.append(f"Feedback: {llr['feedback'][:500]}")
        lines.append("")
    return "\n".join(lines)


def _build_initial_message(
    hlr_name: str,
    hlr_refid: str,
    feedback_file_path: str,
    hlr_description: str,
    feedback_summary: str,
    llrs_with_feedback: list[dict[str, Any]],
) -> str:
    """Build the initial user message for the feedback analysis agent."""
    lines = [
        "# Feedback Analysis Task",
        "",
        f"**HLR**: {hlr_name}",
        f"**Refid**: {hlr_refid}",
        f"**Feedback file**: {feedback_file_path}",
        "",
    ]

    if hlr_description:
        lines.append("## HLR Description")
        lines.append("")
        lines.append(hlr_description)
        lines.append("")

    lines.append(f"## LLRs with Feedback ({len(llrs_with_feedback)})")
    lines.append("")
    lines.append(feedback_summary)

    lines.append("## Instructions")
    lines.append("")
    lines.append(
        "1. Call `parse_feedback` to read the full feedback file and get "
        "structured data."
    )
    lines.append(
        "2. Use the codegraph exploration tools to understand the code "
        "structure affected by this feedback.  Search for symbols, browse "
        "namespaces, and examine the HLR's subtree."
    )
    lines.append(
        "3. Use `memory_context` and `search_memory` to check for existing "
        "design memory that may conflict with or be refined by the feedback."
    )
    lines.append(
        "4. Call `propose_feedback_findings` with your derived memory "
        "findings and requirement updates.  This writes a draft for review."
    )
    lines.append(
        "5. After proposing, call `commit_feedback_analysis` to persist "
        "the memory findings to Neo4j."
    )
    lines.append("")

    return "\n".join(lines)
