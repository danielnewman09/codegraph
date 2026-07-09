#!/usr/bin/env python3
"""Evaluate test coverage for design-layer methods and functions.

Queries Neo4j for all MethodNode/FunctionNode instances tagged "design",
checks CALLEE edges from test steps, and outputs a structured JSON report.

Output is deterministic given the same Neo4j state — no LLM involved.
Use the JSON output as input to an LLM for natural-language insights.

Usage:
    python scripts/evaluate_design_coverage.py [--json report.json]
"""

import json
import argparse
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "codegraph")

QUERY = """
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
"""


def evaluate(output_path=None):
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    methods = []
    with driver.session() as session:
        result = session.run(QUERY)
        for record in result:
            labels = record["labels"]
            is_method = "MethodNode" in labels
            is_function = "FunctionNode" in labels
            vis = record["visibility"] or ""
            is_private = vis == "private" or record["name"].startswith("_")

            methods.append({
                "qualified_name": record["qname"],
                "name": record["name"],
                "kind": "method" if is_method else "function",
                "visibility": vis if vis else ("private" if is_private else "public"),
                "description": record["description"] or "",
                "callee_count": record["callee_count"],
                "covered": record["callee_count"] > 0,
                "callers": sorted(record["callers"] or []),
                "tests": sorted(set(record["tests"] or [])),
            })

    driver.close()

    # Refine visibility: _-prefixed leaf names are private regardless of stored visibility
    for m in methods:
        leaf_name = m["name"].rsplit(".", 1)[-1] if "." in m["name"] else m["name"]
        if leaf_name.startswith("_"):
            m["visibility"] = "private"

    public_methods = [m for m in methods if m["visibility"] == "public"]
    private_methods = [m for m in methods if m["visibility"] == "private"]
    covered = [m for m in methods if m["covered"]]
    uncovered = [m for m in methods if not m["covered"]]
    public_uncovered = [m for m in public_methods if not m["covered"]]

    report = {
        "summary": {
            "total_methods_and_functions": len(methods),
            "total_covered": len(covered),
            "total_uncovered": len(uncovered),
            "public_total": len(public_methods),
            "public_covered": len([m for m in public_methods if m["covered"]]),
            "public_uncovered": len(public_uncovered),
            "private_total": len(private_methods),
            "private_covered": len([m for m in private_methods if m["covered"]]),
            "private_uncovered": len([m for m in private_methods if not m["covered"]]),
        },
        "covered": covered,
        "uncovered": uncovered,
        "public_uncovered": public_uncovered,
        "all_methods": methods,
        "coverage_gaps": [
            {
                "element": m["qualified_name"],
                "kind": m["kind"],
                "reason": (
                    "Public API with no direct test coverage. "
                    "May be tested indirectly or may be a coverage gap."
                ),
            }
            for m in public_uncovered
        ],
        "design_smells": [
            {
                "element": m["qualified_name"],
                "kind": m["kind"],
                "smell": "uncovered_public",
                "detail": (
                    "Public API method/function with zero direct test coverage. "
                    "If its behavior is adequately verified through indirect "
                    "(integration) tests and no external caller outside this "
                    "module needs access, it should not be public. Consider "
                    "making it private (_-prefixed) or inlining it into its "
                    "sole caller."
                ),
            }
            for m in public_uncovered
        ],
    }

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to {output_path}")

    # Print summary
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"Design Coverage Report")
    print(f"{'='*60}")
    print(f"Total methods/functions:  {s['total_methods_and_functions']}")
    print(f"  Covered:               {s['total_covered']}")
    print(f"  Uncovered:             {s['total_uncovered']}")
    print(f"")
    print(f"Public:  {s['public_covered']}/{s['public_total']} covered"
          f" ({s['public_uncovered']} uncovered)")
    print(f"Private: {s['private_covered']}/{s['private_total']} covered"
          f" ({s['private_uncovered']} uncovered)")
    print(f"{'='*60}")

    if report["coverage_gaps"]:
        print(f"\nPublic coverage gaps:")
        for gap in report["coverage_gaps"]:
            print(f"  ✗ {gap['element']} ({gap['kind']})")

    if report["design_smells"]:
        print(f"\n⚠ Design smells (uncovered public = potential API leak):")
        for ds in report["design_smells"]:
            print(f"  ⚡ {ds['element']} ({ds['kind']})")
            print(f"     → {ds['detail']}")

    if uncovered:
        print(f"\nAll uncovered elements:")
        for m in uncovered:
            print(f"  - [{m['kind']}] {m['qualified_name']}")

    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Evaluate design test coverage")
    p.add_argument("--json", default=None, help="Output JSON report path")
    args = p.parse_args()
    evaluate(args.json)
