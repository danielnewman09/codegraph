#!/usr/bin/env python3
"""Generate per-HLR feedback documents for human annotation.

Queries Neo4j for all HLR/LLR nodes tagged "design", groups LLRs
under their parent HLR, and writes one markdown file per HLR with
each LLR's description and a blank `### Feedback` section.

Workflow:
  1. Export: generates fresh feedback docs with blank sections
  2. Review: human/agent fills in feedback on each requirement
  3. Update: agent modifies Neo4j design nodes based on feedback
  4. Archive & re-export: existing feedback docs are moved to
     archive/{timestamp}/, then fresh docs are regenerated
  5. Repeat

Output is deterministic from Neo4j — no LLM enrichment.

Usage:
    python scripts/generate_hlr_feedback_docs.py
"""

import os
import shutil
from datetime import datetime
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "codegraph")

QUERY = """
MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR)
WHERE "design" IN hlr.tags AND "design" IN llr.tags
RETURN hlr.name as hlr_name,
       hlr.description as hlr_desc,
       llr.name as llr_name,
       llr.description as llr_desc
ORDER BY hlr_name, llr_name
"""

HLR_SLUGS = {
    "Architecture Diagram Generator \u2014 Unified Module View": "01_unified_module_view",
    "Architecture Diagram Generator \u2014 Query Integration": "02_query_integration",
    "Architecture Diagram Generator \u2014 HLR/LLR Traceability": "03_traceability",
    "Architecture Diagram Generator \u2014 Markdown Serialization": "04_markdown_serialization",
}


def generate():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    out_dir = "codegraph/requirements/generated/feedback_docs"
    archive_dir = os.path.join(out_dir, "archive")
    os.makedirs(out_dir, exist_ok=True)

    # Archive existing feedback docs before regenerating
    existing = [f for f in os.listdir(out_dir) if f.endswith(".md")]
    if existing:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = os.path.join(archive_dir, ts)
        os.makedirs(archive_path, exist_ok=True)
        for f in existing:
            shutil.move(os.path.join(out_dir, f), os.path.join(archive_path, f))
        print(f"Archived {len(existing)} feedback doc(s) to archive/{ts}/")
    else:
        print("No existing feedback docs to archive (first run)")

    # Group LLRs by HLR
    hlr_data: dict[str, dict] = {}
    with driver.session() as session:
        result = session.run(QUERY)
        for record in result:
            hlr_name = record["hlr_name"]
            if hlr_name not in hlr_data:
                hlr_data[hlr_name] = {
                    "desc": (record["hlr_desc"] or "").strip(),
                    "llrs": [],
                }
            hlr_data[hlr_name]["llrs"].append({
                "name": record["llr_name"],
                "desc": (record["llr_desc"] or "").strip(),
            })

    driver.close()

    count = 0
    for hlr_name, slug in HLR_SLUGS.items():
        data = hlr_data.get(hlr_name)
        if not data:
            continue

        lines = []
        lines.append(f"# {hlr_name}")
        lines.append("")
        lines.append("> **Source**: Neo4j codegraph, `design` tag — deterministic, no LLM enrichment")
        lines.append("> **Generated**: `scripts/generate_hlr_feedback_docs.py`")
        lines.append("> **Regenerate**: `python scripts/generate_hlr_feedback_docs.py`")
        lines.append("> **Cycle**: export → review → update Neo4j → archive → re-export")
        lines.append("")
        hlr_desc = data["desc"]
        if hlr_desc:
            lines.append(hlr_desc)
        lines.append("")
        lines.append("---")
        lines.append("")

        for llr in data["llrs"]:
            lines.append(f"## {llr['name']}")
            lines.append("")
            if llr["desc"]:
                lines.append(llr["desc"])
            else:
                lines.append("_(no description available)_")
            lines.append("")
            lines.append("### Feedback")
            lines.append("")
            lines.append("<!-- Write your feedback on this requirement below. -->")
            lines.append("")

        path = os.path.join(out_dir, f"{slug}.md")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        count += len(data["llrs"])
        print(f"  {slug}.md — {len(data['llrs'])} LLRs")

    print(f"\nGenerated {count} LLR sections across {len(hlr_data)} HLR documents in {out_dir}/")


if __name__ == "__main__":
    generate()
