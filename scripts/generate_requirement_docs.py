#!/usr/bin/env python3
"""Generate the full requirement document set from chain output.

Takes the design + tests markdown produced by the decompose-hlr agent
and generates the complete document set:

  requirements/
  ├── {feature}_design.md       ← authored (from chain output)
  ├── {feature}_tests.md        ← authored (from chain output)
  ├── {feature}_context.md      ← discovery context (from chain step 1)
  ├── generated/
  │   ├── coverage_report.json  ← from evaluate_design_coverage.py
  │   ├── hlr_docs/              ← from generate_hlr_docs.py
  │   └── feedback_docs/        ← from generate_hlr_feedback_docs.py
  └── analysis/
      └── coverage_analysis.md  ← LLM-enriched (manual)

After generating the documents, ingests the design + tests into Neo4j
and runs the verification scripts.

Usage:
    python scripts/generate_requirement_docs.py --feature "architecture_diagram_tool" \\
        --design-doc /path/to/chain_design_output.md \\
        --tests-doc /path/to/chain_tests_output.md \\
        --context-doc /path/to/discovery_context.md
"""

import argparse
import os
import re
import subprocess
import sys


def split_chain_output(output: str) -> tuple[str, str]:
    """Split a combined chain output into design and tests markdown.

    The decompose-hlr agent outputs two sections delimited by ---DESIGN---
    and ---TESTS--- markers.
    """
    design_match = re.search(
        r'---DESIGN---\s*\n(.*?)(?=---TESTS---|$)',
        output, re.DOTALL,
    )
    tests_match = re.search(
        r'---TESTS---\s*\n(.*?)(?=---DESIGN---|$)',
        output, re.DOTALL,
    )

    design = design_match.group(1).strip() if design_match else ""
    tests = tests_match.group(1).strip() if tests_match else ""

    if not design and not tests:
        # No delimiters — try to split on the second "# codegraph: design" header
        parts = output.split("# codegraph: design", 1)
        if len(parts) == 2:
            design = "# codegraph: design" + parts[0] if parts[0].strip() else ""
            tests = "# codegraph: design" + parts[1] if parts[1].strip() else ""
        else:
            design = output
            tests = ""

    return design, tests


def run_script(script_name: str, args: list[str]) -> bool:
    """Run a script from the scripts/ directory. Returns True on success."""
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    cmd = [sys.executable, script_path] + args
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr[:500]}")
        return False
    if result.stdout.strip():
        print(f"  Output: {result.stdout[:300]}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate the full requirement document set from chain output."
    )
    parser.add_argument(
        "--feature", required=True,
        help="Feature name slug (e.g., 'architecture_diagram_tool')",
    )
    parser.add_argument(
        "--design-doc", default=None,
        help="Path to the design markdown (from chain output). If omitted, reads from --chain-output.",
    )
    parser.add_argument(
        "--tests-doc", default=None,
        help="Path to the tests markdown (from chain output). If omitted, reads from --chain-output.",
    )
    parser.add_argument(
        "--chain-output", default=None,
        help="Path to combined chain output (with ---DESIGN---/---TESTS--- delimiters).",
    )
    parser.add_argument(
        "--context-doc", default=None,
        help="Path to the discovery context document (from chain step 1).",
    )
    parser.add_argument(
        "--requirements-dir", default="codegraph/requirements",
        help="Base requirements directory (default: codegraph/requirements)",
    )
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip Neo4j ingestion (just generate documents).",
    )
    args = parser.parse_args()

    req_dir = args.requirements_dir
    gen_dir = os.path.join(req_dir, "generated")
    analysis_dir = os.path.join(req_dir, "analysis")

    # ── Load documents ──────────────────────────────────────────────────

    if args.chain_output:
        with open(args.chain_output) as f:
            chain_text = f.read()
        design_md, tests_md = split_chain_output(chain_text)
    else:
        if args.design_doc:
            with open(args.design_doc) as f:
                design_md = f.read()
        else:
            print("ERROR: --design-doc or --chain-output required")
            sys.exit(1)
        if args.tests_doc:
            with open(args.tests_doc) as f:
                tests_md = f.read()
        else:
            tests_md = ""

    if not design_md.strip():
        print("ERROR: No design markdown found")
        sys.exit(1)

    # ── Save authored documents ─────────────────────────────────────────

    design_path = os.path.join(req_dir, f"{args.feature}_design.md")
    tests_path = os.path.join(req_dir, f"{args.feature}_tests.md")

    with open(design_path, "w") as f:
        f.write(design_md)
    print(f"✓ Wrote {design_path}")

    if tests_md.strip():
        with open(tests_path, "w") as f:
            f.write(tests_md)
        print(f"✓ Wrote {tests_path}")

    # ── Save context document ────────────────────────────────────────────

    if args.context_doc:
        context_path = os.path.join(req_dir, f"{args.feature}_context.md")
        with open(args.context_doc) as f:
            context_md = f.read()
        with open(context_path, "w") as f:
            f.write(context_md)
        print(f"✓ Wrote {context_path}")

    # ── Ingest into Neo4j ─────────────────────────────────────────────────

    if not args.skip_ingest:
        print("\n── Ingesting into Neo4j ──")
        if not run_script("ingest_design.py", [design_path]):
            print("  Design ingestion failed")
        if tests_md.strip():
            if not run_script("ingest_design.py", [tests_path]):
                print("  Tests ingestion failed")

        # ── Generate deterministic output ──────────────────────────────────
        print("\n── Generating deterministic output ──")
        os.makedirs(gen_dir, exist_ok=True)

        coverage_path = os.path.join(gen_dir, "coverage_report.json")
        run_script("evaluate_design_coverage.py", ["--json", coverage_path])

        run_script("generate_hlr_docs.py")

        run_script("generate_hlr_feedback_docs.py")

        # ── Verify integrity ────────────────────────────────────────────────
        print("\n── Verifying integrity ──")
        run_script("verify_callee_granularity.py")

    print(f"\n✓ Document set complete for '{args.feature}'")
    print(f"  Authored:  {req_dir}/{args.feature}_*.md")
    print(f"  Generated: {gen_dir}/")
    if args.context_doc:
        print(f"  Context:   {req_dir}/{args.feature}_context.md")


if __name__ == "__main__":
    main()