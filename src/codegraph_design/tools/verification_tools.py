"""Verification-resolution tools — resolve notional verification stubs to
qualified design names after the design is produced.

Ported from ticketing-system ``backend_migrated.tools.verification_tools``.
These tools belong on :class:`VerificationDispatcher` and are meant to be
used in the *same* agent loop as the design tools.

Workflow:
1. Agent designs classes using DesignToolDispatcher tools
2. Agent calls ``produce_oo_design`` (stores draft, loop continues)
3. Agent resolves notional verification stubs using these tools
4. Agent calls ``commit_design_and_verifications`` (terminal)"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import VerificationDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════

def _build_design_lookup(design_nodes: list[dict]) -> dict[str, dict]:
    """Build a flat qualified_name → info lookup from a LayerGraph design."""
    lookup: dict[str, dict] = {}

    def walk(node: dict) -> None:
        qn = node.get("qualified_name", "")
        if qn:
            lookup[qn] = {
                "qualified_name": qn,
                "name": node.get("name", ""),
                "kind": node.get("kind", ""),
                "type": node.get("type", ""),
            }
        for child in node.get("composes", []):
            walk(child)

    for node in design_nodes:
        walk(node)
    return lookup


def _qname_resolves(
    qname: str,
    has_qname,
) -> bool:
    """Check whether a qualified name exists — delegates to the
    dispatcher's unified resolution (context graph + design draft
    graph + codegraph fallback)."""
    if not qname:
        return False
    return has_qname(qname)


def _suggest_qname(
    unresolved: str,
    design_lookup: dict[str, dict],
    has_qname,
) -> str | None:
    """Find the closest matching qualified name for an unresolved reference."""
    cleaned = unresolved
    for suffix in (".output", ".result", ".return_value"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]

    bare = cleaned.rsplit("::", 1)[-1].rsplit(".", 1)[-1]

    # Search design draft first
    for qname, info in design_lookup.items():
        kind = info.get("kind", "")
        if kind in ("class", "interface", "enum"):
            class_name = qname.rsplit("::", 1)[-1]
            if class_name == bare or class_name.lower() == bare.lower():
                return qname

    for qname, info in design_lookup.items():
        kind = info.get("kind", "")
        if kind in ("method", "attribute") and qname.endswith(f"::{bare}"):
            return qname

    cleaned_lower = cleaned.lower()
    for qname in design_lookup:
        if cleaned_lower in qname.lower():
            return qname

    # Probe the codegraph directly for the bare name
    if has_qname(bare):
        return bare

    return None


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

DRAFT_VERIFICATIONS_SCHEMA = {
    "name": "draft_verifications",
    "description": (
        "Submit resolved verification procedures for LLRs. Takes a map "
        "of LLR uid to verification method lists. Each verification "
        "method includes preconditions, actions, and postconditions "
        "with qualified names referencing real design elements. "
        "Validates that all qualified names exist in the design context "
        "and returns unresolved references with suggestions. Use this "
        "iteratively to fix references before committing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR uid (string) to list of verification "
                    "methods. Keys MUST be LLR uids."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "method": {
                                "type": "string",
                                "description": "Verification method type: 'automated', 'review', 'inspection'.",
                            },
                            "test_name": {
                                "type": "string",
                                "description": "Snake_case test function name (e.g. 'test_set_target_returns_reading').",
                            },
                            "description": {
                                "type": "string",
                                "description": "Human-readable description of what this verification checks.",
                            },
                            "preconditions": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "Pre-condition assertions.",
                            },
                            "actions": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "Stimulus steps.",
                            },
                            "postconditions": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "Post-condition assertions.",
                            },
                        },
                        "required": ["method", "test_name", "description"],
                    },
                },
            },
        },
        "required": ["verifications"],
    },
}


COMMIT_SCHEMA = {
    "name": "commit_design_and_verifications",
    "description": (
        "Commit the final design and all resolved verification procedures. "
        "This terminates the agent loop. You MUST pass the design (the same "
        "list of CodeGraphNode dicts you previously submitted via "
        "produce_oo_design) and the verifications dict (the same structure "
        "you submitted via draft_verifications). Validates that all "
        "qualified names resolve and returns the combined result."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": {
                "type": "array",
                "description": (
                    "The final OO design — same list of CodeGraphNode dicts "
                    "you submitted via produce_oo_design."
                ),
            },
            "verifications": {
                "type": "object",
                "description": (
                    "The resolved verifications — same structure as submitted "
                    "via draft_verifications. Map of LLR uid to list of "
                    "verification method dicts."
                ),
            },
        },
        "required": ["design", "verifications"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════

def handle_draft_verifications(
    ctx: VerificationDispatcher, tool_input: dict,
) -> str:
    """Validate and store drafted verification procedures."""
    verifs_input = tool_input.get("verifications", {})
    if not verifs_input:
        return json.dumps({"valid": False, "errors": ["No verifications provided"]})

    design_nodes = ctx.design_draft or []
    design_lookup = _build_design_lookup(design_nodes)

    if not design_lookup:
        return json.dumps({
            "valid": False,
            "errors": [
                "No design draft exists. Call produce_oo_design first "
                "before resolving verifications."
            ],
        })

    parsed: dict[str, list[dict]] = {}
    parse_errors: list[str] = []

    for llr_uid, v_list in verifs_input.items():
        if not isinstance(v_list, list):
            parse_errors.append(f"LLR {llr_uid}: expected a list of verifications")
            continue
        parsed[llr_uid] = v_list

    if parse_errors:
        return json.dumps({"valid": False, "errors": parse_errors})

    unresolved: list[dict] = []
    warnings: list[str] = []
    verification_summary: dict[str, dict] = {}

    for llr_uid, verifs in parsed.items():
        resolved_count = 0
        total_refs = 0

        for v in verifs:
            test_label = v.get("test_name", "") or v.get("method", "")

            for cond in v.get("preconditions", []) + v.get("postconditions", []):
                sqn = cond.get("subject_qualified_name", "")
                oqn = cond.get("object_qualified_name", "")

                if sqn:
                    total_refs += 1
                    if _qname_resolves(sqn, ctx.has_qname):
                        resolved_count += 1
                    else:
                        suggestion = _suggest_qname(
                            sqn, design_lookup,
                            ctx.has_qname,
                        )
                        detail = {
                            "llr_uid": llr_uid,
                            "verification": test_label,
                            "field": "subject_qualified_name",
                            "value": sqn,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved.append(detail)

                if oqn:
                    total_refs += 1
                    if _qname_resolves(oqn, ctx.has_qname):
                        resolved_count += 1
                    else:
                        suggestion = _suggest_qname(
                            oqn, design_lookup,
                            ctx.has_qname,
                        )
                        detail = {
                            "llr_uid": llr_uid,
                            "verification": test_label,
                            "field": "object_qualified_name",
                            "value": oqn,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved.append(detail)

            for action in v.get("actions", []):
                callee = action.get("callee_qualified_name", "")
                if callee:
                    total_refs += 1
                    if _qname_resolves(callee, ctx.has_qname):
                        resolved_count += 1
                    else:
                        suggestion = _suggest_qname(
                            callee, design_lookup,
                            ctx.has_qname,
                        )
                        detail = {
                            "llr_uid": llr_uid,
                            "verification": test_label,
                            "field": "callee_qualified_name",
                            "value": callee,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved.append(detail)

                caller = action.get("caller_qualified_name", "")
                if caller and "::" not in caller:
                    warnings.append(
                        f"LLR {llr_uid} '{test_label}': caller "
                        f"'{caller}' is not a qualified name — leave empty "
                        f"if the caller is the test harness"
                    )

        verification_summary[llr_uid] = {
            "methods": len(verifs),
            "resolved_references": resolved_count,
            "unresolved_references": total_refs - resolved_count,
        }

    ctx.draft_verifications = parsed

    errors = [
        f"Unresolved reference: '{d['value']}'"
        + (f" Did you mean '{d['suggestion']}'?" if "suggestion" in d else "")
        for d in unresolved
    ]

    return json.dumps({
        "valid": len(unresolved) == 0 and len(parse_errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "verification_summary": verification_summary,
        "unresolved_details": unresolved,
    })


def handle_commit(
    ctx: VerificationDispatcher, tool_input: dict,
) -> str:
    """Commit the design and verifications — terminal tool."""
    errors: list[str] = []

    design = tool_input.get("design", [])
    verifications = tool_input.get("verifications", {})

    if not design:
        errors.append("No design provided. Call produce_oo_design first.")

    if not verifications:
        errors.append(
            "No verification procedures provided. "
            "Call draft_verifications first."
        )

    if design and verifications:
        design_lookup = _build_design_lookup(design)
        for llr_uid, verifs in verifications.items():
            for v in verifs:
                test_label = v.get("test_name", "") or v.get("method", "")
                for cond in v.get("preconditions", []) + v.get("postconditions", []):
                    for field_name in ("subject_qualified_name", "object_qualified_name"):
                        qn = cond.get(field_name, "")
                        if qn and not _qname_resolves(qn, ctx.has_qname):
                            suggestion = _suggest_qname(
                                qn, design_lookup,
                                ctx.has_qname,
                            )
                            msg = f"Unresolved reference: '{qn}'"
                            if suggestion:
                                msg += f" Did you mean '{suggestion}'?"
                            errors.append(msg)
                for action in v.get("actions", []):
                    callee = action.get("callee_qualified_name", "")
                    if callee and not _qname_resolves(callee, ctx.has_qname):
                        suggestion = _suggest_qname(
                            callee, design_lookup,
                            ctx.has_qname,
                        )
                        msg = f"Unresolved reference: '{callee}'"
                        if suggestion:
                            msg += f" Did you mean '{suggestion}'?"
                        errors.append(msg)

    if errors:
        return json.dumps({"committed": False, "errors": errors})

    return json.dumps({
        "committed": True,
        "design": design,
        "verifications": verifications,
    })


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════

def register_all(dispatcher: VerificationDispatcher) -> None:
    """Register all verification tools on a :class:`VerificationDispatcher`."""
    disp = dispatcher
    disp.register(
        "draft_verifications", DRAFT_VERIFICATIONS_SCHEMA,
        lambda inp: handle_draft_verifications(disp, inp),
    )
    disp.register(
        "commit_design_and_verifications", COMMIT_SCHEMA,
        lambda inp: handle_commit(disp, inp),
    )
