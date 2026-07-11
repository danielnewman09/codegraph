"""Formatting helpers for requirement data.

Provides dict-based formatting functions for agent prompts.  These
helpers format requirements and verification stubs directly from dict
data (the LLM output format) without constructing neomodel instances.
"""

from __future__ import annotations


def format_hlr_dict(hlr_dict: dict, include_component: bool = False) -> str:
    """Format a single HLR dict as a prompt line."""
    comp = ""
    if include_component:
        comp_name = hlr_dict.get("component_name") or hlr_dict.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    hlr_id = hlr_dict.get("id", hlr_dict.get("uid", ""))
    return f"HLR {hlr_id}{comp}: {hlr_dict['description']}"


def format_llr_dict(llr_dict: dict) -> str:
    """Format a single LLR dict as a prompt line."""
    llr_id = llr_dict.get("id", llr_dict.get("uid", ""))
    return f"LLR {llr_id}: {llr_dict['description']}"


def format_hlrs_for_prompt(
    hlrs: list[dict],
    llrs: list[dict] | None = None,
    include_component: bool = False,
) -> str:
    """Format HLR/LLR dicts into a text block for agent prompts.

    Args:
        hlrs: List of HLR dicts with at least ``id`` and ``description``.
        llrs: Optional list of LLR dicts with ``id``, ``description``, ``hlr_id``.
        include_component: If True, include component name when available.

    Returns:
        Formatted multi-line string suitable for inclusion in an agent prompt.
    """
    lines = []
    for hlr in hlrs:
        lines.append(format_hlr_dict(hlr, include_component))
        if llrs:
            for llr in [l for l in llrs if l.get("hlr_id") == hlr.get("id")]:
                lines.append(f"  {format_llr_dict(llr)}")
    if llrs:
        unlinked = [l for l in llrs if l.get("hlr_id") is None]
        if unlinked:
            lines.append("\nUnlinked LLRs:")
            for llr in unlinked:
                lines.append(f"  {format_llr_dict(llr)}")
    return "\n".join(lines)


# ── Verification formatting ──────────────────────────────────────────────


def _format_condition_from_dict(cond: dict) -> str:
    """Format a condition dict (with edges) as a human-readable assertion."""
    edges = cond.get("edges", [])
    left = ""
    right = ""
    for e in edges:
        if e.get("relation_type") == "LEFT_OPERAND":
            left = e.get("target_uid", "")
        elif e.get("relation_type") == "RIGHT_OPERAND":
            right = e.get("target_uid", "")
    operator = cond.get("operator", "==")
    parts = [left, operator]
    if right:
        parts.append(right)
    return " ".join(parts)


def _format_action_from_dict(action: dict) -> str:
    """Format an action dict (with edges) as a human-readable step."""
    edges = action.get("edges", [])
    callee = ""
    caller = ""
    for e in edges:
        if e.get("relation_type") == "CALLEE":
            callee = e.get("target_uid", "")
        elif e.get("relation_type") == "CALLER":
            caller = e.get("target_uid", "")
    description = action.get("description", "")

    if caller and callee:
        core = f"{caller} → {callee}"
    elif callee:
        core = callee
    else:
        core = ""
    if description and core:
        return f"{core}: {description}"
    if description:
        return description
    return core or "(no action)"


def _format_verification_from_dict(v: dict) -> str:
    """Format a verification dict as a human-readable block."""
    title = f"[{v.get('method', 'automated')}]"
    if v.get("test_name"):
        title += f" {v['test_name']}"
    lines = [f"  {title}"]
    if v.get("description"):
        lines.append(f"    {v['description']}")

    pre = v.get("preconditions", [])
    post = v.get("postconditions", [])
    acts = v.get("actions", [])

    if pre:
        lines.append("    Pre-conditions:")
        for c in pre:
            lines.append(f"      {_format_condition_from_dict(c)}")
    else:
        lines.append("    Pre-conditions: (none)")

    if acts:
        lines.append("    Actions:")
        for a in acts:
            lines.append(f"      {_format_action_from_dict(a)}")
    else:
        lines.append("    Actions: (none)")

    if post:
        lines.append("    Post-conditions:")
        for c in post:
            lines.append(f"      {_format_condition_from_dict(c)}")
    else:
        lines.append("    Post-conditions: (none)")

    return "\n".join(lines)


def format_llrs_with_verifications_for_prompt(
    llrs: list[dict],
    llr_verifications: dict[int, list[dict]],
) -> str:
    """Format LLRs with their full verification stubs for agent prompts.

    Formats verification stubs directly from dict data — no neomodel
    instances are constructed.

    Args:
        llrs: List of LLR dicts with at least ``id``, ``description``, ``hlr_id``.
        llr_verifications: Dict mapping LLR ID to list of verification
            dicts (the raw LLM format with
            preconditions/actions/postconditions and edges arrays).

    Returns:
        Formatted text suitable for inclusion in an agent prompt.
    """
    lines = []
    for llr in llrs:
        llr_id = llr.get("id", llr.get("uid", ""))
        lines.append(f"LLR {llr_id}: {llr['description']}")
        verifs = llr_verifications.get(llr_id, [])
        if verifs:
            lines.append("  Verifications:")
            for v in verifs:
                lines.append(_format_verification_from_dict(v))
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)
