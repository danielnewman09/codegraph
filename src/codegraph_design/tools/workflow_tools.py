"""Workflow tools — ported from scripts/ for agent-driven persistence.

These tools allow the decompose-hlr subagent to ingest designs, generate
docs, evaluate coverage, and verify callee granularity by calling registered
tools instead of running scripts manually.

Registered by ``register_all(dispatcher)`` on a
:class:`DesignDiscoveryDispatcher`.

.. todo::

    Full refactor needed.  The 4 handler functions
    (handle_generate_hlr_docs, handle_generate_feedback_docs,
    handle_evaluate_coverage, handle_verify_callee_granularity) have zero
    unit tests, duplicate inline-Cypher + column-index-mapping patterns, and
    mix query/transform/present concerns.  They should be split into
    query → transform → present layers with proper tests.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

INGEST_DESIGN_SCHEMA = {
    "name": "ingest_design",
    "description": (
        "Ingest a codegraph design or test Markdown file into Neo4j. "
        "The file must use the codegraph Markdown format (## Component, "
        "### HLR, #### LLR, ## Namespace, ### Class, ## Test, ### TestStep). "
        "Call this after writing the design/tests markdown to a file."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the Markdown file to ingest.",
            },
            "tag": {
                "type": "string",
                "default": "design",
                "description": "Provenance tag for the ingested nodes (default: 'design').",
            },
        },
        "required": ["file_path"],
    },
}


GENERATE_HLR_DOCS_SCHEMA = {
    "name": "generate_hlr_docs",
    "description": (
        "Generate one markdown document per HLR showing the full "
        "requirement → test → design stack. Reads from Neo4j (design tag) "
        "and writes to the generated/hlr_docs/ directory."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "output_dir": {
                "type": "string",
                "default": "codegraph/requirements/generated/hlr_docs",
                "description": "Output directory for per-HLR documents.",
            },
        },
        "required": [],
    },
}


GENERATE_FEEDBACK_DOCS_SCHEMA = {
    "name": "generate_feedback_docs",
    "description": (
        "Generate per-HLR feedback documents with blank ### Feedback sections "
        "under each LLR. Archives existing feedback docs before regenerating."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "output_dir": {
                "type": "string",
                "default": "codegraph/requirements/generated/feedback_docs",
                "description": "Output directory for feedback documents.",
            },
        },
        "required": [],
    },
}


EVALUATE_COVERAGE_SCHEMA = {
    "name": "evaluate_coverage",
    "description": (
        "Evaluate test coverage for design-layer methods and functions. "
        "Queries Neo4j for all MethodNode/FunctionNode tagged 'design', "
        "counts CALLEE edges from test steps, and returns a structured "
        "report. Flags uncovered public methods as design smells."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Optional path to write the JSON report.",
            },
        },
        "required": [],
    },
}


VERIFY_CALLEE_SCHEMA = {
    "name": "verify_callee_granularity",
    "description": (
        "Verify that all CALLEE edges from test steps target the correct "
        "granularity (method-level for method calls, function-level for "
        "function calls). Returns a list of issues or 'all correct'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════


def handle_ingest_design(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Ingest a design markdown file into Neo4j."""
    file_path = tool_input.get("file_path", "")
    tag = tool_input.get("tag", "design")

    if not file_path:
        return json.dumps({"error": "file_path is required"})

    p = Path(file_path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {file_path}"})

    try:
        from neomodel import db as neomodel_db

        from codegraph.export.markdown import MarkdownImporter

        text = p.read_text(encoding="utf-8")
        importer = MarkdownImporter(tags=frozenset({tag}), strict=False)
        graph = importer.import_markdown(text)

        # Reconstruct with create_missing=True to auto-create scaffold
        # targets (AttributeNode, LiteralNode) referenced by edges
        # (LEFT_OPERAND, RIGHT_OPERAND, CALLEE) but not present as
        # headings in the markdown.
        from codegraph.graph import LayerGraph
        flat = graph.serialize()
        graph = LayerGraph.deserialize(flat, create_missing=True)

        # Check for errors
        if importer.diagnostics:
            errors = [d for d in importer.diagnostics if d.severity == "error"]
            if errors:
                return json.dumps({
                    "ingested": False,
                    "errors": [d.message for d in errors],
                    "warnings": len(importer.diagnostics) - len(errors),
                })

        # Count nodes
        def count_all(entries):
            total = len(entries)
            for _qname, entry in entries.items():
                for _child_type, children in entry.children.items():
                    total += count_all(children)
            return total

        node_count = count_all(graph.entries)

        # Persist to Neo4j
        graph.to_neo4j()

        warnings = len(importer.diagnostics) if importer.diagnostics else 0
        return json.dumps({
            "ingested": True,
            "node_count": node_count,
            "tag": tag,
            "file": str(p),
            "warnings": warnings,
        })
    except Exception as exc:
        log.exception("ingest_design failed for %s", file_path)
        return json.dumps({"ingested": False, "error": str(exc)})


def handle_generate_hlr_docs(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Generate per-HLR documents from Neo4j."""
    output_dir = tool_input.get("output_dir", "codegraph/requirements/generated/hlr_docs")

    try:
        from neomodel import db as neomodel_db

        results, meta = neomodel_db.cypher_query("""
                MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR)
                WHERE "design" IN hlr.tags
                OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode)
                OPTIONAL MATCH (test)-[:VERIFIES]->(verifies_target)
                OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode)
                OPTIONAL MATCH (step)-[:CALLEE]->(step_target)
                RETURN hlr.name as hlr_name, hlr.description as hlr_desc,
                       llr.name as llr_name, llr.description as llr_desc,
                       test.name as test_name, test.description as test_desc,
                       test.qualified_name as test_qname,
                       verifies_target.name as verifies_target_name,
                       verifies_target.qualified_name as verifies_target_qname,
                       step.name as step_name, step.description as step_desc,
                       step_target.name as step_target_name,
                       step_target.qualified_name as step_target_qname
                ORDER BY hlr_name, llr_name, test_name, step_name
            """)

        # Build column index from meta for named access.
        cols = {name: idx for idx, name in enumerate(meta)}

        hlr_data = {}
        for row in results:
            h = row[cols["hlr_name"]]
            if h not in hlr_data:
                hlr_data[h] = {"desc": row[cols["hlr_desc"]] or "", "llrs": {}}
            l_name = row[cols["llr_name"]]
            if l_name and l_name not in hlr_data[h]["llrs"]:
                hlr_data[h]["llrs"][l_name] = {
                    "desc": row[cols["llr_desc"]] or "", "tests": {}
                }
            t_name = row[cols["test_name"]]
            if t_name and l_name and t_name not in hlr_data[h]["llrs"][l_name]["tests"]:
                hlr_data[h]["llrs"][l_name]["tests"][t_name] = {
                    "desc": row[cols["test_desc"]] or "",
                    "steps": [],
                    "targets": set(),
                }

            # Collect VERIFIES targets.
            verifies_qname = row[cols["verifies_target_qname"]]
            if t_name and verifies_qname:
                hlr_data[h]["llrs"][l_name]["tests"][t_name]["targets"].add(
                    verifies_qname
                )

            # Collect step-level CALLEE targets.
            step_name = row[cols["step_name"]]
            step_desc = row[cols["step_desc"]] or ""
            step_target_qname = row[cols["step_target_qname"]]
            if t_name and step_name:
                hlr_data[h]["llrs"][l_name]["tests"][t_name]["steps"].append(
                    (step_name, step_desc)
                )
                if step_target_qname:
                    hlr_data[h]["llrs"][l_name]["tests"][t_name]["targets"].add(
                        step_target_qname
                    )

        os.makedirs(output_dir, exist_ok=True)

        # Clear existing
        for f in os.listdir(output_dir):
            if f.endswith(".md"):
                os.remove(os.path.join(output_dir, f))

        count = 0
        for hlr_name, data in sorted(hlr_data.items()):
            lines = []
            lines.append(f"# {hlr_name}")
            lines.append("")
            lines.append("> **Source**: Neo4j codegraph, `design` tag — deterministic, no LLM enrichment")
            lines.append("")
            lines.append("## Description")
            lines.append("")
            lines.append(data['desc'].replace('\n', ' ').strip())
            lines.append("")
            lines.append("---")
            lines.append("")

            all_llrs = sorted(data['llrs'].items())
            covered = sum(1 for _, ld in all_llrs if ld['tests'])
            lines.append(f"**{covered}/{len(all_llrs)} LLRs verified**")
            lines.append("")

            all_targets = set()

            for llr_name, llr_data in all_llrs:
                lines.append(f"## {llr_name}")
                lines.append("")
                lines.append(llr_data['desc'].replace('\n', ' ').strip())
                lines.append("")

                tests = sorted(llr_data['tests'].items())
                if not tests:
                    lines.append("> ⚠ No tests defined for this LLR.")
                    lines.append("")
                    continue

                for test_name, test_data in tests:
                    lines.append(f"### `{test_name}`")
                    lines.append("")
                    lines.append(test_data['desc'].replace('\n', ' ').strip())
                    lines.append("")

                    if test_data['steps']:
                        lines.append("**Steps:**")
                        lines.append("")
                        for i, (sname, sdesc) in enumerate(test_data['steps'], 1):
                            short = sname.split('.')[-1] if '.' in sname else sname
                            lines.append(f"{i}. **{short}** — {sdesc}")
                        lines.append("")

                    if test_data['targets']:
                        all_targets.update(test_data['targets'])
                        lines.append("**Exercises:**")
                        lines.append("")
                        for tq in sorted(test_data['targets']):
                            lines.append(f"- `{tq}`")
                        lines.append("")

            lines.append("---")
            lines.append("")
            lines.append("## Design Elements Exercised")
            lines.append("")
            for tq in sorted(all_targets):
                kind = "method" if "::" in tq else "function"
                lines.append(f"- `{tq}` — {kind}")
            lines.append("")

            # Generate slug from HLR name
            import re
            slug = re.sub(r'[^a-z0-9]+', '_', hlr_name.lower()).strip('_')
            slug = re.sub(r'_+', '_', slug)

            path = os.path.join(output_dir, f"{slug}.md")
            with open(path, "w") as f:
                f.write('\n'.join(lines))
            count += 1

        return json.dumps({"generated": True, "hlr_count": count, "output_dir": output_dir})
    except Exception as exc:
        log.exception("generate_hlr_docs failed")
        return json.dumps({"generated": False, "error": str(exc)})


def handle_generate_feedback_docs(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Generate per-HLR feedback documents with blank feedback sections."""
    output_dir = tool_input.get("output_dir", "codegraph/requirements/generated/feedback_docs")

    try:
        from neomodel import db as neomodel_db

        results, meta = neomodel_db.cypher_query("""
            MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR)
            WHERE "design" IN hlr.tags AND "design" IN llr.tags
            RETURN hlr.name as hlr_name, hlr.description as hlr_desc,
                   llr.name as llr_name, llr.description as llr_desc
            ORDER BY hlr_name, llr_name
        """)

        cols = {name: idx for idx, name in enumerate(meta)}

        hlr_data = {}
        for row in results:
            hlr_name = row[cols["hlr_name"]]
            if hlr_name not in hlr_data:
                hlr_data[hlr_name] = {"desc": (row[cols["hlr_desc"]] or "").strip(), "llrs": []}
            hlr_data[hlr_name]["llrs"].append({
                "name": row[cols["llr_name"]],
                "desc": (row[cols["llr_desc"]] or "").strip(),
            })

        os.makedirs(output_dir, exist_ok=True)

        # Archive existing
        existing = [f for f in os.listdir(output_dir) if f.endswith(".md")]
        if existing:
            archive_dir = os.path.join(output_dir, "archive")
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            archive_path = os.path.join(archive_dir, ts)
            os.makedirs(archive_path, exist_ok=True)
            for f in existing:
                shutil.move(os.path.join(output_dir, f), os.path.join(archive_path, f))

        import re
        count = 0
        for hlr_name, data in sorted(hlr_data.items()):
            lines = []
            lines.append(f"# {hlr_name}")
            lines.append("")
            lines.append("> **Source**: Neo4j codegraph, `design` tag — deterministic, no LLM enrichment")
            lines.append("> **Cycle**: export → review → update Neo4j → archive → re-export")
            lines.append("")
            if data["desc"]:
                lines.append(data["desc"])
            lines.append("")
            lines.append("---")
            lines.append("")

            for llr in data["llrs"]:
                lines.append(f"## {llr['name']}")
                lines.append("")
                lines.append(llr["desc"] if llr["desc"] else "_(no description available)_")
                lines.append("")
                lines.append("### Feedback")
                lines.append("")
                lines.append("<!-- Write your feedback on this requirement below. -->")
                lines.append("")

            slug = re.sub(r'[^a-z0-9]+', '_', hlr_name.lower()).strip('_')
            slug = re.sub(r'_+', '_', slug)
            path = os.path.join(output_dir, f"{slug}.md")
            with open(path, "w") as f:
                f.write('\n'.join(lines))
            count += len(data["llrs"])

        return json.dumps({
            "generated": True,
            "llr_count": count,
            "hlr_count": len(hlr_data),
            "output_dir": output_dir,
        })
    except Exception as exc:
        log.exception("generate_feedback_docs failed")
        return json.dumps({"generated": False, "error": str(exc)})


def handle_evaluate_coverage(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Evaluate test coverage for design-layer methods and functions."""
    output_path = tool_input.get("output_path")

    try:
        from neomodel import db as neomodel_db

        results, meta = neomodel_db.cypher_query("""
            MATCH (m)
            WHERE "design" IN m.tags
              AND (m:MethodNode OR m:FunctionNode)
            OPTIONAL MATCH (step:TestStepNode)-[:CALLEE]->(m)
            WHERE "design" IN step.tags
            OPTIONAL MATCH (step)<-[:COMPOSES]-(test:TestNode)
            RETURN m.qualified_name as qname,
                   m.name as name,
                   labels(m) as labels,
                   m.description as description,
                   m.visibility as visibility,
                   count(DISTINCT step) as callee_count,
                   collect(DISTINCT step.name) as callers,
                   collect(DISTINCT test.name) as tests
            ORDER BY callee_count, qname
        """)

        cols = {name: idx for idx, name in enumerate(meta)}

        methods = []
        for row in results:
            labels = row[cols["labels"]]
            is_method = "MethodNode" in labels
            vis = row[cols["visibility"]] or ""
            name_val = row[cols["name"]] or ""
            is_private = vis == "private" or name_val.startswith("_")

            methods.append({
                "qualified_name": row[cols["qname"]],
                "name": name_val,
                "kind": "method" if is_method else "function",
                "visibility": vis if vis else ("private" if is_private else "public"),
                "description": row[cols["description"]] or "",
                "callee_count": row[cols["callee_count"]],
                "covered": row[cols["callee_count"]] > 0,
                "callers": sorted(row[cols["callers"]] or []),
                "tests": sorted(set(row[cols["tests"]] or [])),
            })

        # Refine visibility
        for m in methods:
            leaf_name = m["name"].rsplit(".", 1)[-1] if "." in m["name"] else m["name"]
            if leaf_name.startswith("_"):
                m["visibility"] = "private"

        public = [m for m in methods if m["visibility"] == "public"]
        covered = [m for m in methods if m["covered"]]
        public_uncovered = [m for m in public if not m["covered"]]

        report = {
            "summary": {
                "total": len(methods),
                "covered": len(covered),
                "uncovered": len(methods) - len(covered),
                "public_total": len(public),
                "public_covered": len([m for m in public if m["covered"]]),
                "public_uncovered": len(public_uncovered),
            },
            "design_smells": [
                {
                    "element": m["qualified_name"],
                    "kind": m["kind"],
                    "smell": "uncovered_public",
                    "detail": "Public API with zero direct test coverage. Consider making it private or inlining into its sole caller.",
                }
                for m in public_uncovered
            ],
            "coverage_gaps": [
                {"element": m["qualified_name"], "kind": m["kind"]}
                for m in public_uncovered
            ],
        }

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2)

        return json.dumps(report, indent=2)
    except Exception as exc:
        log.exception("evaluate_coverage failed")
        return json.dumps({"error": str(exc)})


def handle_verify_callee_granularity(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Verify CALLEE edges target correct granularity."""
    try:
        from neomodel import db as neomodel_db

        results, meta = neomodel_db.cypher_query("""
            MATCH (step:TestStepNode)-[r:CALLEE]->(target)
            WHERE "design" IN step.tags
            RETURN step.name as step_name,
                   target.name as target_name,
                   target.qualified_name as target_qname,
                   labels(target) as target_labels
            ORDER BY step_name
        """)

        cols = {name: idx for idx, name in enumerate(meta)}

        issues = []
        for row in results:
            step_name = row[cols["step_name"]] or ""
            target_qname = row[cols["target_qname"]] or ""
            target_labels = row[cols["target_labels"]]
            is_method = "MethodNode" in target_labels
            is_function = "FunctionNode" in target_labels
            has_double_colon = "::" in target_qname

            if has_double_colon and not is_method:
                issues.append(f"{step_name} → {target_qname}: expected MethodNode, got {target_labels}")
            elif not has_double_colon and not is_function and "ClassNode" in target_labels:
                issues.append(f"{step_name} → {target_qname}: expected method-level (with ::), got ClassNode")

        if issues:
            return json.dumps({"verified": False, "issues": issues, "count": len(issues)})
        return json.dumps({"verified": True, "issues": [], "count": 0})
    except Exception as exc:
        log.exception("verify_callee_granularity failed")
        return json.dumps({"error": str(exc)})


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════


def register_all(dispatcher: DesignDiscoveryDispatcher) -> None:
    """Register all workflow tools on a DesignDiscoveryDispatcher."""
    disp = dispatcher
    disp.register(
        "ingest_design", INGEST_DESIGN_SCHEMA,
        lambda inp: handle_ingest_design(disp, inp),
    )
    disp.register(
        "generate_hlr_docs", GENERATE_HLR_DOCS_SCHEMA,
        lambda inp: handle_generate_hlr_docs(disp, inp),
    )
    disp.register(
        "generate_feedback_docs", GENERATE_FEEDBACK_DOCS_SCHEMA,
        lambda inp: handle_generate_feedback_docs(disp, inp),
    )
    disp.register(
        "evaluate_coverage", EVALUATE_COVERAGE_SCHEMA,
        lambda inp: handle_evaluate_coverage(disp, inp),
    )
    disp.register(
        "verify_callee_granularity", VERIFY_CALLEE_SCHEMA,
        lambda inp: handle_verify_callee_granularity(disp, inp),
    )