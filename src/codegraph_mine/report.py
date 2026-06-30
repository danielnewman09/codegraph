"""Markdown report generation for mined requirements.

Queries all mined HLRs (``tags=["as-built"]``) and their LLRs with
linked tests, then renders a structured markdown report showing:

- Component-level coverage summary
- Per-HLR: description, LLRs with test counts
- Per-LLR: linked tests with descriptions
- Gap analysis (compounds with tests but no requirements)

Usage::

    from codegraph_mine.report import generate_report

    md = generate_report()
    with open("REQUIREMENTS_REPORT.md", "w") as f:
        f.write(md)

    # Or via CLI:
    codegraph-mine report
    codegraph-mine report --output REQUIREMENTS_REPORT.md
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from neomodel import db

log = logging.getLogger(__name__)


def generate_report(*, tag: str = "as-built", output: str | None = None,
                    include_composite: bool = True) -> str:
    """Generate a markdown report of all mined requirements.

    Queries all HLRs with the given provenance tag, walks their LLRs
    and linked TestNodes, and renders a structured report.

    If ``include_composite`` is True, also queries composite HLRs
    (HLRs with the ``"composite"`` tag) and renders a
    ``Composite Technical Requirements`` section showing the
    composite → child HLR hierarchy.

    Args:
        tag: Provenance tag to filter HLRs by (default ``"as-built"``).
        output: Optional file path to write the report to.
        include_composite: If True, include a composite HLRs section.

    Returns:
        The full markdown report as a string.
    """
    hlr_data = _fetch_hlrs_with_llrs(tag)
    uncovered = _fetch_compounds_without_requirements(tag)
    composite_data = (
        _fetch_composite_hlrs(tag) if include_composite else []
    )

    md = _render_report(hlr_data, uncovered, tag, composite_data)

    if output:
        with open(output, "w") as f:
            f.write(md)
        print(f"Report written to {output}")

    return md


# ══════════════════════════════════════════════════════════════════════════
# Data fetching
# ══════════════════════════════════════════════════════════════════════════


def _fetch_hlrs_with_llrs(tag: str) -> list[dict]:
    """Fetch all HLRs with the given tag, each with its LLRs and tests.

    Returns a list of HLR dicts, each with:
        name, description, refid, llrs (list of LLR dicts with tests).
    """
    query = """
    MATCH (h:HLR)
    WHERE $tag IN h.tags
    OPTIONAL MATCH (h)-[:COMPOSES]->(l:LLR)
    OPTIONAL MATCH (l)-[:COMPOSES]->(t:TestNode)
    OPTIONAL MATCH (h)-[:COMPOSES]->(c)
    WHERE c:ClassNode OR c:InterfaceNode OR c:EnumNode OR c:UnionNode
    RETURN h, l, t, c
    ORDER BY h.name, l.name
    """
    try:
        results, _ = db.cypher_query(query, {"tag": tag})
    except Exception as exc:
        log.error("_fetch_hlrs_with_llrs: query failed: %s", exc)
        return []

    # Group by HLR
    hlr_map: dict[str, dict] = {}
    for row in results:
        h_node, l_node, t_node, c_node = row

        h_name = h_node.get("name", "")
        h_desc = h_node.get("description", "")
        h_refid = h_node.get("refid", "")

        if h_refid not in hlr_map:
            compound_name = c_node.get("qualified_name", "") if c_node else ""
            hlr_map[h_refid] = {
                "name": h_name,
                "description": h_desc,
                "refid": h_refid,
                "compound": compound_name,
                "llrs": {},
            }

        if l_node:
            l_name = l_node.get("name", "")
            l_desc = l_node.get("description", "")
            l_refid = l_node.get("refid", "")

            if l_refid not in hlr_map[h_refid]["llrs"]:
                hlr_map[h_refid]["llrs"][l_refid] = {
                    "name": l_name,
                    "description": l_desc,
                    "refid": l_refid,
                    "tests": [],
                }

            if t_node:
                test_qn = t_node.get("qualified_name", "")
                test_desc = t_node.get("description", "")
                test_mod = t_node.get("test_module", "")
                if test_qn:
                    hlr_map[h_refid]["llrs"][l_refid]["tests"].append({
                        "qualified_name": test_qn,
                        "description": test_desc,
                        "module": test_mod,
                    })

    # Convert to sorted list
    result: list[dict] = []
    for hlr in sorted(hlr_map.values(), key=lambda h: h["name"]):
        llrs = []
        for llr in sorted(hlr["llrs"].values(), key=lambda l: l["name"]):
            llrs.append(llr)
        hlr["llrs"] = llrs
        result.append(hlr)

    return result


def _fetch_compounds_without_requirements(tag: str) -> list[dict]:
    """Find compounds that have tests but no mined HLR.

    Returns a list of dicts with qualified_name and test_count.
    """
    from codegraph_mine.persistence import _make_hlr_name

    # Find all HLR names (existing requirements)
    hlr_query = """
    MATCH (h:HLR) WHERE $tag IN h.tags
    RETURN h.name AS name
    """
    try:
        hlr_results, _ = db.cypher_query(hlr_query, {"tag": tag})
    except Exception:
        return []

    existing_hlr_names = {row[0] for row in hlr_results}

    # Find compounds with tests
    test_query = """
    MATCH (t:TestNode)-[:VERIFIES]->(c)
    WHERE c:ClassNode OR c:InterfaceNode OR c:EnumNode OR c:UnionNode
    WITH c, count(t) AS test_count
    RETURN c.qualified_name AS qn, test_count
    ORDER BY test_count DESC
    """
    try:
        test_results, _ = db.cypher_query(test_query, {})
    except Exception:
        return []

    uncovered = []
    for row in test_results:
        qn = row[0] or ""
        count = row[1] or 0
        # Check if an HLR exists for this compound
        short = qn.rsplit(".", 1)[-1] if qn else ""
        hlr_name = f"Requirements for {short}"
        if hlr_name not in existing_hlr_names:
            uncovered.append({"qualified_name": qn, "test_count": count})

    return uncovered


def _fetch_composite_hlrs(tag: str) -> list[dict]:
    """Fetch all composite HLRs with their child HLRs.

    Composite HLRs carry the ``"composite"`` tag.  Each composite HLR
    composes one or more child HLRs via ``COMPOSES`` edges.  This
    function returns a list of composite HLR dicts, each with its
    description, rationale (if present), and a list of child HLR
    summaries.

    Returns a list of dicts, each with:
        name, description, refid, child_hlrs (list of dicts with
        name, description, compound).
    """
    query = """
    MATCH (h:HLR)
    WHERE 'composite' IN h.tags AND $tag IN h.tags
    OPTIONAL MATCH (h)-[:COMPOSES]->(child:HLR)
    WHERE NOT 'composite' IN child.tags
    OPTIONAL MATCH (child)-[:COMPOSES]->(c)
    WHERE c:ClassNode OR c:InterfaceNode OR c:EnumNode OR c:UnionNode
    OPTIONAL MATCH (h)-[:COMPOSES]->(ns:NamespaceNode)
    RETURN h, child, c, ns
    ORDER BY h.name, child.name
    """
    try:
        results, _ = db.cypher_query(query, {"tag": tag})
    except Exception as exc:
        log.error("_fetch_composite_hlrs: query failed: %s", exc)
        return []

    composite_map: dict[str, dict] = {}
    for row in results:
        h_node, child_node, c_node, ns_node = row

        h_refid = h_node.get("refid", "")
        if h_refid not in composite_map:
            ns_name = ns_node.get("qualified_name", "") if ns_node else ""
            composite_map[h_refid] = {
                "name": h_node.get("name", ""),
                "description": h_node.get("description", ""),
                "refid": h_refid,
                "namespace": ns_name,
                "child_hlrs": {},
            }

        if child_node:
            child_refid = child_node.get("refid", "")
            if child_refid not in composite_map[h_refid]["child_hlrs"]:
                compound_name = c_node.get("qualified_name", "") if c_node else ""
                composite_map[h_refid]["child_hlrs"][child_refid] = {
                    "name": child_node.get("name", ""),
                    "description": child_node.get("description", ""),
                    "refid": child_refid,
                    "compound": compound_name,
                }

    result: list[dict] = []
    for comp in sorted(composite_map.values(), key=lambda c: c["name"]):
        comp["child_hlrs"] = sorted(
            comp["child_hlrs"].values(), key=lambda h: h["name"]
        )
        result.append(comp)

    return result


# ══════════════════════════════════════════════════════════════════════════
# Rendering
# ══════════════════════════════════════════════════════════════════════════


def _render_report(
    hlrs: list[dict],
    uncovered: list[dict],
    tag: str,
    composite_hlrs: list[dict] | None = None,
) -> str:
    """Render the full markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total_hlrs = len(hlrs)
    total_llrs = sum(len(h["llrs"]) for h in hlrs)
    total_tests = sum(
        len(llr["tests"]) for h in hlrs for llr in h["llrs"]
    )
    # Distinct tests across all LLRs
    all_test_qns: set[str] = set()
    for h in hlrs:
        for llr in h["llrs"]:
            for t in llr["tests"]:
                all_test_qns.add(t["qualified_name"])

    lines = [
        f"# Requirements Report",
        f"",
        f"**Generated:** {now}  ",
        f"**Tag filter:** `{tag}`  ",
        f"**Summary:** {total_hlrs} HLRs, {total_llrs} LLRs, "
        f"{len(all_test_qns)} distinct tests linked  ",
        f"",
        "---",
        "",
    ]

    # ── Table of Contents ──
    lines.append("## Table of Contents")
    lines.append("")
    if composite_hlrs:
        lines.append(f"1. [Composite Technical Requirements](#composite-technical-requirements)")
        lines.append(f"2. [Per-Compound HLRs](#per-compound-hlrs)")
        if uncovered:
            lines.append(f"3. [Uncovered Compounds](#uncovered-compounds)")
        lines.append("")
    else:
        for i, hlr in enumerate(hlrs):
            comp = hlr.get("compound", "")
            comp_str = f" — `{comp}`" if comp else ""
            lines.append(
                f"{i + 1}. [{hlr['name']}](#hlr-{_anchor(hlr['name'])})"
                f"{comp_str} ({len(hlr['llrs'])} LLRs)"
            )
        if uncovered:
            lines.append("")
            lines.append("### [Uncovered Compounds](#uncovered-compounds)")
        lines.append("")
    lines.append("---")
    lines.append("")

    # ── Composite HLRs section ──
    if composite_hlrs:
        lines.append("## Composite Technical Requirements")
        lines.append("")
        lines.append(
            f"{len(composite_hlrs)} composite HLRs synthesised from "
            f"per-compound HLR clusters."
        )
        lines.append("")

        for comp in composite_hlrs:
            ns = comp.get("namespace", "")
            ns_str = f" — `{ns}`" if ns else ""
            lines.append(
                f"### {comp['name']}{{#composite-{_anchor(comp['name'])}}}"
            )
            lines.append("")
            lines.append(f"**Description:** {comp['description']}")
            lines.append("")
            if ns_str:
                lines.append(f"**Namespace:** `{ns}`")
                lines.append("")
            child_count = len(comp["child_hlrs"])
            lines.append(f"**Child HLRs:** {child_count}")
            lines.append("")

            for j, child in enumerate(comp["child_hlrs"]):
                comp_str = f" (`{child['compound']}`)" if child["compound"] else ""
                lines.append(f"{j + 1}. **{child['name']}**{comp_str}")
                lines.append(f"   {child['description']}")
                lines.append("")

            lines.append("---")
            lines.append("")

        lines.append("## Per-Compound HLRs")
        lines.append("")
        lines.append(
            f"{total_hlrs} per-compound HLRs with {total_llrs} LLRs "
            f"and {len(all_test_qns)} distinct tests."
        )
        lines.append("")

    # ── HLR detail sections ──
    for hlr in hlrs:
        lines.append(f"## {hlr['name']} {{#hlr-{_anchor(hlr['name'])}}}")
        lines.append("")
        lines.append(f"**Description:** {hlr['description']}")
        lines.append("")

        comp = hlr.get("compound", "")
        if comp:
            lines.append(f"**Compound:** `{comp}`")
            lines.append("")

        llr_count = len(hlr["llrs"])
        llr_tests = sum(len(llr["tests"]) for llr in hlr["llrs"])
        lines.append(f"**LLRs:** {llr_count} | **Linked tests:** {llr_tests}")
        lines.append("")

        for j, llr in enumerate(hlr["llrs"]):
            lines.append(f"### LLR {j + 1}: {llr['description']}")
            lines.append("")

            if llr["tests"]:
                lines.append("**Verification tests:**")
                lines.append("")
                lines.append(
                    "| Test | Module | Description |"
                )
                lines.append(
                    "|------|--------|-------------|"
                )
                for t in llr["tests"]:
                    desc = t["description"][:120] if t["description"] else "—"
                    test_short = t["qualified_name"].rsplit(".", 1)[-1]
                    lines.append(
                        f"| `{test_short}` "
                        f"| `{t['module']}` "
                        f"| {desc} |"
                    )
                lines.append("")
            else:
                lines.append("*No tests linked to this LLR.*")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ── Uncovered compounds ──
    if uncovered:
        lines.append("## Uncovered Compounds {#uncovered-compounds}")
        lines.append("")
        lines.append(
            "The following compounds have test coverage but no mined "
            "requirements. Run `codegraph-mine --compound <name>` to mine "
            "them."
        )
        lines.append("")
        lines.append("| Compound | Tests |")
        lines.append("|----------|-------|")
        for u in uncovered:
            lines.append(
                f"| `{u['qualified_name']}` | {u['test_count']} |"
            )
        lines.append("")

    return "\n".join(lines)


def _anchor(name: str) -> str:
    """Derive a markdown anchor from an HLR name."""
    return name.lower().replace(" ", "-").replace(".", "-")
