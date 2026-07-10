"""Feedback analysis tools — parse feedback docs, propose memory findings,
and draft requirement updates.

These tools are registered on a :class:`FeedbackDispatcher` and called
by the feedback analysis agent during its tool loop.

Tools:
  - parse_feedback: Read the feedback markdown file for an HLR and return
    structured feedback per LLR.
  - propose_feedback_findings: Submit memory finding proposals and
    requirement update drafts.  Writes to the requirements directory.
  - commit_feedback_analysis: Terminal tool — validate and persist findings
    to Neo4j.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_feedback.tools.dispatcher import FeedbackDispatcher

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════

REQUIREMENTS_DIR = "codegraph/requirements"
FEEDBACK_DOCS_DIR = f"{REQUIREMENTS_DIR}/generated/feedback_docs"

# ── Valid memory types ────────────────────────────────────────────────
VALID_MEMORY_TYPES = {
    "decision", "constraint", "insight", "assumption", "tradeoff", "rationale",
}

# ── Required fields for memory finding proposals ──────────────────────
MEMORY_REQUIRED_FIELDS = {"type", "qualified_name", "content"}


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

PARSE_FEEDBACK_SCHEMA = {
    "name": "parse_feedback",
    "description": (
        "Read the feedback markdown file for the active HLR and return "
        "structured feedback per LLR.  Each entry includes the LLR name, "
        "its description, and the human-written feedback text (if any).  "
        "Empty feedback sections (no human comment) are included so you "
        "can see which LLRs received feedback."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


PROPOSE_FINDINGS_SCHEMA = {
    "name": "propose_feedback_findings",
    "description": (
        "Submit memory finding proposals, requirement description updates, "
        "and test definition updates.  "
        "Writes a markdown draft to codegraph/requirements/<component-slug>/ "
        "for human review before persisting to Neo4j.  "
        "memory_findings: list of {type, qualified_name, content, tags?, "
        "confidence?, links_to?, rationale?}.  "
        "requirement_updates: list of {target_name, target_type (HLR|LLR), "
        "original_description, updated_description, rationale}.  "
        "test_updates: list of {target_name, target_kind (Test|TestStep|"
        "Assertion|Fixture), parent_llr, original_text, updated_text, "
        "change_type (description|operator|expected_value|phase|method), "
        "rationale}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memory_findings": {
                "type": "array",
                "description": "Memory node proposals derived from feedback.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": list(VALID_MEMORY_TYPES),
                        },
                        "qualified_name": {
                            "type": "string",
                            "description": "Stable qualified name, e.g. 'memory::agi-feedback::use-streaming'",
                        },
                        "content": {
                            "type": "string",
                            "description": "Free-text body of the memory finding.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Provenance tags (default: ['design', 'feedback']).",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0.0–1.0 certainty (default: 0.85).",
                        },
                        "links_to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Qualified names of code/HLR/LLR nodes to link.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this finding was derived (cite the feedback).",
                        },
                        "parent_llr": {
                            "type": "string",
                            "description": "Name of the LLR this finding was derived from. Used to group findings per-LLR in the draft.",
                        },
                    },
                    "required": ["type", "qualified_name", "content"],
                },
            },
            "requirement_updates": {
                "type": "array",
                "description": "Proposed requirement description changes.",
                "items": {
                    "type": "object",
                    "properties": {
                        "target_name": {
                            "type": "string",
                            "description": "Name of the HLR or LLR to update.",
                        },
                        "target_type": {
                            "type": "string",
                            "enum": ["HLR", "LLR"],
                        },
                        "original_description": {
                            "type": "string",
                            "description": "The current description text.",
                        },
                        "updated_description": {
                            "type": "string",
                            "description": "The proposed new description text.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this change is needed (cite the feedback).",
                        },
                    },
                    "required": [
                        "target_name", "target_type",
                        "original_description", "updated_description",
                    ],
                },
            },
            "test_updates": {
                "type": "array",
                "description": "Proposed test definition changes (test nodes, steps, assertions, fixtures).",
                "items": {
                    "type": "object",
                    "properties": {
                        "target_name": {
                            "type": "string",
                            "description": "Qualified name of the test node (e.g. 'vm::configure::test_valid_threshold').",
                        },
                        "target_kind": {
                            "type": "string",
                            "enum": ["Test", "TestStep", "Assertion", "Fixture"],
                            "description": "Kind of test node being updated.",
                        },
                        "parent_llr": {
                            "type": "string",
                            "description": "Name of the parent LLR this test belongs to.",
                        },
                        "original_text": {
                            "type": "string",
                            "description": "The current text (description, operator value, etc.).",
                        },
                        "updated_text": {
                            "type": "string",
                            "description": "The proposed new text.",
                        },
                        "change_type": {
                            "type": "string",
                            "enum": [
                                "description",
                                "operator",
                                "expected_value",
                                "phase",
                                "method",
                                "test_name",
                                "precondition",
                                "action",
                                "postcondition",
                                "setup",
                                "teardown",
                            ],
                            "description": "What aspect of the test definition is changing.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this change is needed (cite the feedback).",
                        },
                    },
                    "required": [
                        "target_name", "target_kind",
                        "original_text", "updated_text", "change_type",
                    ],
                },
            },
        },
        "required": [],
    },
}


COMMIT_ANALYSIS_SCHEMA = {
    "name": "commit_feedback_analysis",
    "description": (
        "Terminal tool — validate the draft findings and persist memory "
        "nodes to Neo4j via the codegraph_memory record_memory function.  "
        "Requirement updates are written as a markdown draft for human "
        "review; they are NOT auto-applied to Neo4j (that requires a "
        "separate ingestion step).  Call this only after "
        "propose_feedback_findings has been accepted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Feedback file resolution
# ══════════════════════════════════════════════════════════════════════════


def _parse_h1_from_file(file_path: Path) -> str | None:
    """Extract the first H1 heading (# Title) from a markdown file.

    Returns the heading text (without the leading '# ') or None.
    """
    try:
        with open(file_path, "r") as f:
            for line in f:
                stripped = line.rstrip("\n")
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    return stripped[2:].strip()
    except OSError:
        pass
    return None


def resolve_feedback_file(hlr_name: str) -> str | None:
    """Find the feedback markdown file for an HLR by scanning heading content.

    Scans all ``*.md`` files under ``generated/feedback_docs/`` and all
    ``feedback.md`` files under ``requirements/*/``.  Returns the first file
    whose ``# `` heading matches *hlr_name* exactly.

    Returns the absolute path or None.
    """
    cwd = Path.cwd()
    hlr_name_normalized = hlr_name.strip()

    # 1. Scan generated/feedback_docs/*.md
    feedback_docs_dir = cwd / FEEDBACK_DOCS_DIR
    if feedback_docs_dir.is_dir():
        for md_file in sorted(feedback_docs_dir.glob("*.md")):
            heading = _parse_h1_from_file(md_file)
            if heading and heading.strip() == hlr_name_normalized:
                return str(md_file)

    # 2. Scan requirements/*/feedback.md
    req_dir = cwd / REQUIREMENTS_DIR
    if req_dir.is_dir():
        for feedback_file in sorted(req_dir.glob("*/feedback.md")):
            heading = _parse_h1_from_file(feedback_file)
            if heading and heading.strip() == hlr_name_normalized:
                return str(feedback_file)

    return None


def _derive_component_slug(hlr_name: str) -> str:
    """Derive a component directory slug from the HLR name.

    Handles common prefix patterns (e.g., 'Architecture Diagram Generator — ...').
    """
    # Try splitting on em-dash to get component prefix
    if " — " in hlr_name:
        prefix = hlr_name.split(" — ")[0]
    elif " - " in hlr_name:
        prefix = hlr_name.split(" - ")[0]
    else:
        prefix = hlr_name

    return re.sub(r"[^a-z0-9-]+", "-", prefix.lower()).strip("-")


# ══════════════════════════════════════════════════════════════════════════
# Feedback parsing
# ══════════════════════════════════════════════════════════════════════════


def parse_feedback_markdown(file_path: str) -> dict[str, Any]:
    """Parse a feedback markdown file into structured data.

    Returns:
        {
            "hlr_name": str,
            "hlr_description": str,
            "file_path": str,
            "llrs": [
                {
                    "name": str,
                    "description": str,
                    "feedback": str,
                    "has_feedback": bool,
                },
                ...
            ],
        }
    """
    if not os.path.exists(file_path):
        return {
            "error": f"Feedback file not found: {file_path}",
            "hlr_name": "",
            "hlr_description": "",
            "file_path": file_path,
            "llrs": [],
        }

    with open(file_path, "r") as f:
        content = f.read()

    lines = content.split("\n")

    # Parse H1 title (first # heading)
    hlr_name = ""
    hlr_description_lines: list[str] = []
    in_header = True
    in_description = False
    for line in lines:
        if line.startswith("# ") and not hlr_name:
            hlr_name = line[2:].strip()
            in_header = False
            in_description = True
            continue
        if in_header:
            continue
        if in_description:
            if line.startswith("## ") or line.startswith("---"):
                in_description = False
                break
            if line.startswith(">"):
                continue  # skip metadata comments
            hlr_description_lines.append(line)

    hlr_description = "\n".join(hlr_description_lines).strip()

    # Parse LLR sections (## heading → description → ### Feedback)
    llrs: list[dict[str, Any]] = []
    current_llr: dict[str, Any] | None = None
    in_feedback = False

    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            # Save previous LLR
            if current_llr is not None:
                llrs.append(current_llr)
            current_llr = {
                "name": line[3:].strip(),
                "description": "",
                "feedback": "",
                "has_feedback": False,
            }
            in_feedback = False
        elif line.startswith("### Feedback"):
            in_feedback = True
            if current_llr is not None:
                # Transition to feedback section
                pass
        elif current_llr is not None:
            stripped = line.strip()
            if in_feedback:
                # Skip HTML comments and blank lines in feedback
                if stripped.startswith("<!--") or not stripped:
                    continue
                current_llr["feedback"] += line + "\n"
                current_llr["has_feedback"] = True
            else:
                # Skip metadata comments and blank lines
                if stripped.startswith(">") or not stripped:
                    continue
                if stripped == "---":
                    continue
                current_llr["description"] += line + "\n"

    # Don't forget the last LLR
    if current_llr is not None:
        llrs.append(current_llr)

    # Clean up
    for llr in llrs:
        llr["description"] = llr["description"].strip()
        llr["feedback"] = llr["feedback"].strip()

    return {
        "hlr_name": hlr_name,
        "hlr_description": hlr_description,
        "file_path": file_path,
        "llrs": llrs,
    }


# ══════════════════════════════════════════════════════════════════════════
# Draft writing
# ══════════════════════════════════════════════════════════════════════════


def write_draft(
    component_slug: str,
    hlr_name: str,
    memory_findings: list[dict[str, Any]],
    requirement_updates: list[dict[str, Any]],
    test_updates: list[dict[str, Any]] | None = None,
    llr_context: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Write the analysis draft to the requirements directory.

    Follows the per-LLR pattern of generated/feedback_docs/*.md:
    each LLR is called out individually with its own subsections for
    memory findings, requirement updates, and test definition updates.

    Args:
        component_slug: Component directory slug.
        hlr_name: The HLR name.
        memory_findings: Memory node proposals (may have ``parent_llr``).
        requirement_updates: Requirement description changes (``target_name``
            is the HLR or LLR name).
        test_updates: Test definition changes (have ``parent_llr``).
        llr_context: Dict mapping LLR name → {description, feedback} for
            the LLRs in the feedback file.  When provided, every LLR is
            listed even if it has no findings.

    Creates:
      requirements/<component_slug>/feedback_analysis.md

    Returns the output file path.
    """
    cwd = Path.cwd()
    out_dir = cwd / REQUIREMENTS_DIR / component_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Group findings by LLR ────────────────────────────────────
    llr_context = llr_context or {}

    # memory_findings: group by parent_llr (default to HLR-level)
    mf_by_llr: dict[str, list[dict]] = {}
    hlr_level_findings: list[dict] = []
    for mf in memory_findings:
        parent = mf.get("parent_llr", "")
        if parent:
            mf_by_llr.setdefault(parent, []).append(mf)
        else:
            hlr_level_findings.append(mf)

    # requirement_updates: group by target_name when target_type == LLR
    ru_by_llr: dict[str, list[dict]] = {}
    hlr_level_updates: list[dict] = []
    for ru in requirement_updates:
        if ru.get("target_type") == "LLR":
            ru_by_llr.setdefault(ru.get("target_name", ""), []).append(ru)
        else:
            hlr_level_updates.append(ru)

    # test_updates: group by parent_llr
    tu_by_llr: dict[str, list[dict]] = {}
    for tu in (test_updates or []):
        parent = tu.get("parent_llr", "")
        tu_by_llr.setdefault(parent, []).append(tu)

    # ── Determine the set of all LLR names to render ──────────────
    # Include every LLR from the context + any LLR referenced by findings
    all_llr_names: list[str] = list(llr_context.keys())
    for name in list(mf_by_llr.keys()) + list(ru_by_llr.keys()) + list(tu_by_llr.keys()):
        if name and name not in all_llr_names:
            all_llr_names.append(name)
    # Remove empty string (HLR-level) from the LLR list
    all_llr_names = [n for n in all_llr_names if n]

    # ── Build the document ────────────────────────────────────────
    lines = [
        f"# Feedback Analysis: {hlr_name}",
        "",
        f"> **Generated**: {now}",
        "> **Source**: codegraph_feedback agent — LLM analysis of human feedback",
        "> **Status**: DRAFT — requires human review before persisting to Neo4j",
        "",
        "---",
        "",
    ]

    # ── HLR-level findings (no parent_llr) ─────────────────────────
    if hlr_level_findings or hlr_level_updates:
        lines.append("## HLR-Level Findings")
        lines.append("")
        _render_memory_findings(lines, hlr_level_findings)
        _render_requirement_updates(lines, hlr_level_updates)
        lines.append("---")
        lines.append("")

    # ── Per-LLR sections ──────────────────────────────────────────
    for llr_name in all_llr_names:
        ctx_entry = llr_context.get(llr_name, {})
        llr_desc = ctx_entry.get("description", "")
        llr_feedback = ctx_entry.get("feedback", "")

        lines.append(f"## {llr_name}")
        lines.append("")
        if llr_desc:
            lines.append(llr_desc)
            lines.append("")

        # Original feedback
        if llr_feedback:
            lines.append("### Feedback")
            lines.append("")
            lines.append(llr_feedback)
            lines.append("")

        # Memory findings for this LLR
        llr_mfs = mf_by_llr.get(llr_name, [])
        if llr_mfs:
            lines.append("### Memory Findings")
            lines.append("")
            _render_memory_findings(lines, llr_mfs)

        # Requirement updates for this LLR
        llr_rus = ru_by_llr.get(llr_name, [])
        if llr_rus:
            lines.append("### Requirement Updates")
            lines.append("")
            _render_requirement_updates(lines, llr_rus)

        # Test updates for this LLR
        llr_tus = tu_by_llr.get(llr_name, [])
        if llr_tus:
            lines.append("### Test Definition Updates")
            lines.append("")
            _render_test_updates(lines, llr_tus)

        lines.append("")

    out_path = out_dir / "feedback_analysis.md"
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    log.info("Wrote feedback analysis draft to %s", out_path)
    return str(out_path)


def _render_memory_findings(lines: list[str], findings: list[dict]) -> None:
    """Render memory findings as markdown subsections."""
    for i, mf in enumerate(findings):
        mtype = mf.get("type", "unknown")
        qname = mf.get("qualified_name", f"memory-{i}")
        content = mf.get("content", "")
        tags = mf.get("tags", ["design", "feedback"])
        confidence = mf.get("confidence", 0.85)
        links_to = mf.get("links_to", [])
        rationale = mf.get("rationale", "")

        lines.append(f"#### {qname}")
        lines.append("")
        lines.append(f"- **Type**: {mtype}")
        lines.append(f"- **Confidence**: {confidence}")
        lines.append(f"- **Tags**: {', '.join(tags)}")
        if links_to:
            lines.append(f"- **Links to**: {', '.join(links_to)}")
        lines.append("")
        lines.append(content)
        lines.append("")
        if rationale:
            lines.append(f"*Rationale*: {rationale}")
            lines.append("")


def _render_requirement_updates(lines: list[str], updates: list[dict]) -> None:
    """Render requirement updates as markdown before/after blocks."""
    for i, ru in enumerate(updates):
        target_name = ru.get("target_name", f"update-{i}")
        target_type = ru.get("target_type", "LLR")
        original = ru.get("original_description", "")
        updated = ru.get("updated_description", "")
        rationale = ru.get("rationale", "")

        lines.append(f"#### {target_type}: {target_name}")
        lines.append("")
        if rationale:
            lines.append(f"*Rationale*: {rationale}")
            lines.append("")
        lines.append("**Original**:")
        lines.append("")
        lines.append(f"> {original}")
        lines.append("")
        lines.append("**Proposed**:")
        lines.append("")
        lines.append(f"> {updated}")
        lines.append("")


def _render_test_updates(lines: list[str], updates: list[dict]) -> None:
    """Render test definition updates as markdown before/after blocks."""
    for i, tu in enumerate(updates):
        target_name = tu.get("target_name", f"test-{i}")
        target_kind = tu.get("target_kind", "Test")
        change_type = tu.get("change_type", "description")
        original = tu.get("original_text", "")
        updated = tu.get("updated_text", "")
        rationale = tu.get("rationale", "")

        lines.append(f"#### {target_kind}: {target_name}")
        lines.append("")
        lines.append(f"- **Change type**: {change_type}")
        lines.append("")
        if rationale:
            lines.append(f"*Rationale*: {rationale}")
            lines.append("")
        lines.append("**Original**:")
        lines.append("")
        lines.append(f"> {original}")
        lines.append("")
        lines.append("**Proposed**:")
        lines.append("")
        lines.append(f"> {updated}")
        lines.append("")


# ══════════════════════════════════════════════════════════════════════════
# Tool handlers
# ══════════════════════════════════════════════════════════════════════════


def handle_parse_feedback(
    ctx: FeedbackDispatcher, _tool_input: dict
) -> str:
    """Read and parse the feedback markdown file for the active HLR."""
    file_path = ctx.feedback_file_path
    hlr_name = ctx.hlr_name

    if not file_path:
        # Try to resolve
        resolved = resolve_feedback_file(hlr_name)
        if resolved:
            ctx.feedback_file_path = resolved
            file_path = resolved
        else:
            return json.dumps({
                "error": (
                    f"No feedback file found for HLR '{hlr_name}'.  "
                    f"Searched: generated/feedback_docs/, "
                    f"requirements/<component>/feedback.md"
                ),
                "hlr_name": hlr_name,
                "llrs": [],
            })

    result = parse_feedback_markdown(file_path)

    # Populate ctx.llr_feedback for use by other tools
    ctx.llr_feedback = {
        llr["name"]: llr for llr in result.get("llrs", [])
    }

    return json.dumps(result, indent=2)


def handle_propose_findings(
    ctx: FeedbackDispatcher, tool_input: dict
) -> str:
    """Validate and write draft memory findings + requirement updates + test updates."""
    memory_findings = tool_input.get("memory_findings", [])
    requirement_updates = tool_input.get("requirement_updates", [])
    test_updates = tool_input.get("test_updates", [])

    errors: list[str] = []

    # Validate memory findings
    for i, mf in enumerate(memory_findings):
        mtype = mf.get("type", "")
        if mtype not in VALID_MEMORY_TYPES:
            errors.append(
                f"memory_findings[{i}]: invalid type '{mtype}'. "
                f"Must be one of: {sorted(VALID_MEMORY_TYPES)}"
            )
        missing = MEMORY_REQUIRED_FIELDS - set(mf.keys())
        if missing:
            errors.append(
                f"memory_findings[{i}]: missing required fields: {missing}"
            )

    # Validate requirement updates
    for i, ru in enumerate(requirement_updates):
        target_type = ru.get("target_type", "")
        if target_type not in ("HLR", "LLR"):
            errors.append(
                f"requirement_updates[{i}]: target_type must be 'HLR' or 'LLR'"
            )
        if not ru.get("target_name"):
            errors.append(
                f"requirement_updates[{i}]: missing target_name"
            )
        if not ru.get("updated_description"):
            errors.append(
                f"requirement_updates[{i}]: missing updated_description"
            )

    # Validate test updates
    VALID_TEST_KINDS = {"Test", "TestStep", "Assertion", "Fixture"}
    VALID_CHANGE_TYPES = {
        "description", "operator", "expected_value", "phase",
        "method", "test_name", "precondition", "action",
        "postcondition", "setup", "teardown",
    }
    for i, tu in enumerate(test_updates):
        target_kind = tu.get("target_kind", "")
        if target_kind not in VALID_TEST_KINDS:
            errors.append(
                f"test_updates[{i}]: target_kind must be one of: "
                f"{sorted(VALID_TEST_KINDS)}"
            )
        change_type = tu.get("change_type", "")
        if change_type not in VALID_CHANGE_TYPES:
            errors.append(
                f"test_updates[{i}]: change_type must be one of: "
                f"{sorted(VALID_CHANGE_TYPES)}"
            )
        if not tu.get("target_name"):
            errors.append(f"test_updates[{i}]: missing target_name")
        if not tu.get("updated_text"):
            errors.append(f"test_updates[{i}]: missing updated_text")

    if errors:
        return json.dumps({"errors": errors, "accepted": False}, indent=2)

    # Derive component slug
    hlr_name = ctx.hlr_name
    component_slug = _derive_component_slug(hlr_name)

    # Write draft
    out_path = write_draft(
        component_slug, hlr_name,
        memory_findings, requirement_updates, test_updates,
        llr_context=ctx.llr_feedback,
    )

    # Store findings on context for commit
    ctx.draft_memory_findings = memory_findings
    ctx.draft_requirement_updates = requirement_updates
    ctx.draft_test_updates = test_updates
    ctx.draft_output_path = out_path

    return json.dumps({
        "accepted": True,
        "memory_findings_count": len(memory_findings),
        "requirement_updates_count": len(requirement_updates),
        "test_updates_count": len(test_updates),
        "draft_path": out_path,
        "message": (
            f"Draft written to {out_path}.  Review the file, then call "
            f"commit_feedback_analysis to persist memory nodes to Neo4j."
        ),
    }, indent=2)


def handle_commit_analysis(
    ctx: FeedbackDispatcher, _tool_input: dict
) -> str:
    """Persist validated memory findings to Neo4j.

    Uses codegraph_memory's record_memory for each finding.
    Requirement updates are NOT auto-applied — they require separate
    ingestion via ingest_design.
    """
    memory_findings = getattr(ctx, "draft_memory_findings", None) or []
    if not memory_findings:
        return json.dumps({
            "error": "No draft findings to commit. Call propose_feedback_findings first.",
            "committed": 0,
        })

    from codegraph_memory.tools.record import record_memory

    committed = 0
    errors: list[dict] = []

    for mf in memory_findings:
        try:
            result = record_memory(
                type=mf["type"],
                qualified_name=mf["qualified_name"],
                content=mf["content"],
                tags=mf.get("tags", ["design", "feedback"]),
                confidence=mf.get("confidence", 0.85),
                links_to=mf.get("links_to", []),
                mode="upsert",
            )
            if result.get("error") is None:
                committed += 1
            else:
                errors.append({
                    "qualified_name": mf["qualified_name"],
                    "error": result["error"],
                })
        except Exception as exc:
            errors.append({
                "qualified_name": mf.get("qualified_name", "?"),
                "error": str(exc),
            })

    # Write a provenance note in the draft file
    draft_path = getattr(ctx, "draft_output_path", "")
    if draft_path and os.path.exists(draft_path):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(draft_path, "a") as f:
            f.write(f"\n\n---\n\n> **Persisted**: {now} — {committed} memory nodes committed to Neo4j.\n")

    return json.dumps({
        "committed": committed,
        "total": len(memory_findings),
        "errors": errors,
        "requirement_updates_draft": ctx.draft_output_path,
        "message": (
            f"Committed {committed}/{len(memory_findings)} memory nodes to Neo4j.  "
            f"Requirement updates are in the draft file for separate ingestion."
        ),
    }, indent=2)


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════


def register_all(dispatcher: FeedbackDispatcher) -> None:
    """Register all feedback analysis tools on a FeedbackDispatcher."""
    disp = dispatcher
    disp.register(
        "parse_feedback", PARSE_FEEDBACK_SCHEMA,
        lambda inp: handle_parse_feedback(disp, inp),
    )
    disp.register(
        "propose_feedback_findings", PROPOSE_FINDINGS_SCHEMA,
        lambda inp: handle_propose_findings(disp, inp),
    )
    disp.register(
        "commit_feedback_analysis", COMMIT_ANALYSIS_SCHEMA,
        lambda inp: handle_commit_analysis(disp, inp),
    )
