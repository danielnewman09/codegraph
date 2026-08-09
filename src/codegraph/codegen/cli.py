"""``codegraph-codegen`` CLI entry point (mirrors codegraph-html).

Phase 1 usage:

    codegraph-codegen --input graph.json --dry-run         # plan only
    codegraph-codegen --input graph.json --output build/   # write tree
    codegraph-codegen --input graph.json --pack custom/    # custom pack

``--dry-run`` is the safe default mode for planning: prints the planned
file tree and renders nothing to disk.  Config discovery
(``.codegraph.toml`` / ``.doxygen-index.toml``) and the ``verify`` /
``sync-fixtures`` subcommands land with their own slices.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    from codegraph.codegen import generate

    parser = argparse.ArgumentParser(
        prog="codegraph-codegen",
        description="Generate source code (C++ first) from a codegraph LayerGraph.",
    )
    parser.add_argument(
        "--input", default=None,
        help="Path to a serialized LayerGraph JSON (nested format). "
             "Default: discover via --project-dir config, else stdin.",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="Project root containing .codegraph.toml or .doxygen-index.toml "
             "(used to discover the graph JSON when --input is omitted)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for the generated tree (default: dry-run only)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the planned file tree without writing (default when "
             "--output is omitted)",
    )
    parser.add_argument(
        "--pack", default=None,
        help="Custom TemplatePack directory (overrides the builtin cpp pack)",
    )
    parser.add_argument(
        "--language", default="cpp",
        help="Target language key (default: cpp)",
    )
    parser.add_argument(
        "--markers", action="store_true",
        help="Emit `// @codegraph uid:…` provenance markers above each "
             "declaration (default: off — markers are a side-channel and "
             "break byte-fidelity with hand-written source; verify() does "
             "not need them).",
    )
    parser.add_argument(
        "--as-built", default=None,
        help="Serialized as-built LayerGraph JSON for 'verify': asserts the "
             "design's stable compounds survive the round trip.",
    )
    parser.add_argument(
        "--tier", type=int, default=1, choices=[1, 2],
        help="Verification tier: 1 = compound qname subset (default), "
             "2 = canonical method uids (Phase 2).",
    )
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            data = json.load(fh)
    elif args.project_dir != ".":
        # Config discovery: .codegraph.toml → .doxygen-index.toml →
        # graph JSON at {output_dir}/{name}.json (mirrors codegraph-html).
        from codegraph.codegen.cli_config import load_config

        config, _project = load_config(args.project_dir)
        if not config.graph_json.exists():
            print(
                f"Error: graph JSON not found: {config.graph_json} "
                f"(configured via {config.source_file} in {args.project_dir})",
                file=sys.stderr,
            )
            return 1
        with open(config.graph_json, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = json.load(sys.stdin)

    if args.as_built:
        from codegraph.codegen.verify import verify
        from codegraph.graph import LayerGraph

        with open(args.as_built, encoding="utf-8") as fh:
            as_built = LayerGraph.deserialize(json.load(fh))
        design = LayerGraph.deserialize(data)
        report = verify(design, as_built, tier=args.tier)
        print(f"verify: {report.summarize()}")
        for qn in report.missing:
            print(f"  missing: {qn}")
        if report.missing_methods:
            print("  missing methods:")
            for label in report.missing_methods:
                print(f"    {label}")
        if report.drift_methods:
            print("  signature drift:")
            for label in report.drift_methods:
                print(f"    {label}")
        if report.missing:
            return 1
        return 0

    kwargs = {}
    if args.pack:
        kwargs["pack"] = args.pack
    if args.markers:
        kwargs["emit_markers"] = True
    if args.output and not args.dry_run:
        kwargs["output_dir"] = args.output

    result = generate(data, language=args.language, **kwargs)

    for path in sorted(result.files):
        size = len(result.files[path])
        print(f"{path}  ({size} bytes)")
    print(f"-- {result.summarize()}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
