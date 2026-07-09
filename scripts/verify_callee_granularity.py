#!/usr/bin/env python3
"""Verify CALLEE edges point to correct granularity (method vs class/function).

For each test step with a CALLEE edge, checks whether the target is at the
appropriate level:
  - Steps that call methods (classify, export, add_mapping, etc.) should
    target MethodNode (qualified_name contains "::")
  - Steps that call top-level functions (generate, fetch, discover, etc.)
    should target FunctionNode

Usage:
    python scripts/verify_callee_granularity.py

Exit code 0 = all edges correct, 1 = issues found.
"""

import sys
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "codegraph")

# Maps step name keywords → expected target granularity
# "method" = should target a MethodNode (has :: in qname)
# "function" = should target a FunctionNode (no :: in qname)
STEP_EXPECTATIONS = {
    "classify": "method",
    "add_custom": "method",
    "add_mapping": "method",
    "get_color": "method",
    "export_diagram": "method",
    "export_and_assert": "method",
    "export_public_only": "method",
    "export_all": "method",
    "generate": "function",
    "call_fetch": "function",
    "call_discover": "function",
    "call_query": "function",
    "seed_graph": "function",
    "seed_requirements": "function",
    "build_graph": "function",
    "build_config": "function",
    "render_png": "function",
    "assert": "function",
    "monkeypatch": "function",
    "serialize": "function",
    "import_back": "function",
    "create_classifier": "function",
}


def verify():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    issues = []

    with driver.session() as session:
        result = session.run(
            """
            MATCH (step:TestStepNode)-[r:CALLEE]->(target)
            WHERE "design" IN step.tags
            RETURN step.name as step_name,
                   target.name as target_name,
                   target.qualified_name as target_qname,
                   labels(target) as target_labels
            ORDER BY step_name
            """
        )

        for record in result:
            step_name = record["step_name"]
            target_qname = record["target_qname"] or ""
            target_labels = record["target_labels"]
            is_method = "MethodNode" in target_labels
            is_function = "FunctionNode" in target_labels
            has_double_colon = "::" in target_qname

            # Determine expected type from step name
            expected = None
            for keyword, exp_type in STEP_EXPECTATIONS.items():
                if keyword in step_name:
                    expected = exp_type
                    break

            if expected is None:
                issues.append(
                    f"UNKNOWN: {step_name} → {target_qname} "
                    f"(no expectation rule for this step name keyword)"
                )
                continue

            if expected == "method" and (not has_double_colon or not is_method):
                issues.append(
                    f"WRONG: {step_name} → {target_qname} "
                    f"(expected method, got {target_labels})"
                )
            elif expected == "function" and not is_function:
                issues.append(
                    f"WRONG: {step_name} → {target_qname} "
                    f"(expected function, got {target_labels})"
                )

    driver.close()

    if issues:
        print(f"\n{len(issues)} CALLEE granularity issue(s) found:\n")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()
        return 1
    else:
        print("\n✓ All CALLEE edges correct (method→method, function→function)\n")
        return 0


if __name__ == "__main__":
    sys.exit(verify())
