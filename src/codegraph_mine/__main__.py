"""CLI entry point for ``codegraph-mine``.

Subcommands::

    codegraph-mine mine --all
    codegraph-mine mine --all --dry-run
    codegraph-mine mine --compound "codegraph.models.compound.ClassNode"
    codegraph-mine report
    codegraph-mine report --output REQUIREMENTS_REPORT.md

Environment:
    Requires ``LLM_API_KEY`` (and optionally ``LLM_BASE_URL``,
    ``LLM_MODEL``, ``LLM_BACKEND``) or the equivalent ``llm-caller``
    configuration.

    Requires ``NEO4J_URI``, ``NEO4J_USER``, ``NEO4J_PASSWORD`` (or a
    ``.env`` file in the working directory) for Neo4j connectivity.
"""

from __future__ import annotations

# ── Load .env BEFORE any other imports ────────────────────────────────
import os
from pathlib import Path

dotenv_path = Path.cwd() / ".env"
if dotenv_path.exists():
    try:
        from dotenv import load_dotenv as _load
        _load(dotenv_path)
    except ImportError:
        pass

import argparse
import json
import sys

from codegraph_mine import LLRMiner, mining_available, generate_report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Mine requirements from test evidence in the codegraph.",
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # ── mine ──────────────────────────────────────────────────────────
    mine_parser = sub.add_parser("mine", help="Mine requirements from tests")
    mine_parser.add_argument(
        "--compound",
        help="Qualified name of a single compound (class/interface/enum) "
             "to mine requirements for.",
    )
    mine_parser.add_argument(
        "--all",
        action="store_true",
        help="Mine requirements for all compounds with tests.",
    )
    mine_parser.add_argument(
        "--tag",
        default=None,
        help="Only consider tests with this provenance tag "
             "(e.g. 'as-built').",
    )
    mine_parser.add_argument(
        "--model", default="",
        help="LLM model override (default: llm-caller configured model).",
    )
    mine_parser.add_argument(
        "--dry-run", action="store_true",
        help="Build prompts and simulate without calling the LLM.",
    )
    mine_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing requirements.",
    )
    mine_parser.add_argument(
        "--max-tokens", type=int, default=16384,
        help="Maximum tokens per LLM response (default: 16384).",
    )
    mine_parser.add_argument(
        "--log-dir", default=None,
        help="Directory for prompt + response trace logs. "
             "Also settable via MINE_LOG_DIR env var.",
    )
    mine_parser.add_argument(
        "--allow-thinking", action="store_true",
        help="Allow the model to produce reasoning/thinking output.",
    )
    mine_parser.add_argument(
        "--agentic", action="store_true",
        help="Use agentic tool-loop flow: LLM explores the codegraph with "
             "tools before submitting results.",
    )
    mine_parser.set_defaults(func=_cmd_mine)

    # ── composite ───────────────────────────────────────────────────
    comp_parser = sub.add_parser(
        "composite",
        help="Mine composite technical requirements from HLR clusters",
    )
    comp_parser.add_argument(
        "--all",
        action="store_true",
        help="Mine composite HLRs for all namespaces with ≥2 child HLRs.",
    )
    comp_parser.add_argument(
        "--namespace",
        default=None,
        help="Qualified name of a single namespace to mine a composite HLR for.",
    )
    comp_parser.add_argument(
        "--tag",
        default=None,
        help="Only consider HLRs with this provenance tag (e.g. 'as-built').",
    )
    comp_parser.add_argument(
        "--model", default="",
        help="LLM model override (default: llm-caller configured model).",
    )
    comp_parser.add_argument(
        "--dry-run", action="store_true",
        help="Build prompts and simulate without calling the LLM.",
    )
    comp_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing composite requirements.",
    )
    comp_parser.add_argument(
        "--max-tokens", type=int, default=16384,
        help="Maximum tokens per LLM response (default: 16384).",
    )
    comp_parser.add_argument(
        "--log-dir", default=None,
        help="Directory for prompt + response trace logs.",
    )
    comp_parser.add_argument(
        "--allow-thinking", action="store_true",
        help="Allow the model to produce reasoning/thinking output.",
    )
    comp_parser.add_argument(
        "--agentic", action="store_true",
        help="Use agentic tool-loop flow: LLM explores the codegraph with "
             "tools before submitting results.",
    )
    comp_parser.set_defaults(func=_cmd_composite)

    # ── components ───────────────────────────────────────────────────
    components_parser = sub.add_parser(
        "components",
        help="Mine functional Components from the full HLR landscape",
    )
    components_parser.add_argument(
        "--tag", default=None,
        help="Only consider HLRs with this provenance tag (e.g. 'as-built').",
    )
    components_parser.add_argument(
        "--model", default="",
        help="LLM model override (default: llm-caller configured model).",
    )
    components_parser.add_argument(
        "--dry-run", action="store_true",
        help="Build prompt and simulate without calling the LLM.",
    )
    components_parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing mined Components.",
    )
    components_parser.add_argument(
        "--max-tokens", type=int, default=16384,
        help="Maximum tokens per LLM response (default: 16384).",
    )
    components_parser.add_argument(
        "--log-dir", default=None,
        help="Directory for prompt + response trace logs.",
    )
    components_parser.add_argument(
        "--allow-thinking", action="store_true",
        help="Allow the model to produce reasoning/thinking output.",
    )
    components_parser.add_argument(
        "--agentic", action="store_true",
        help="Use agentic tool-loop flow: LLM explores the codegraph with "
             "tools before submitting results.",
    )
    components_parser.set_defaults(func=_cmd_components)

    # ── report ────────────────────────────────────────────────────────
    report_parser = sub.add_parser(
        "report", help="Generate a markdown report from mined requirements"
    )
    report_parser.add_argument(
        "--tag", default="as-built",
        help="Provenance tag to filter HLRs by (default: 'as-built').",
    )
    report_parser.add_argument(
        "-o", "--output", default=None,
        help="Write the report to a file (default: stdout).",
    )
    report_parser.add_argument(
        "--no-composite", action="store_true",
        help="Exclude composite HLRs from the report.",
    )
    report_parser.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv or sys.argv[1:] if argv is None else argv)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


# ══════════════════════════════════════════════════════════════════════════
# Command implementations
# ══════════════════════════════════════════════════════════════════════════


def _check_neo4j() -> None:
    """Verify Neo4j connectivity; exit with message on failure."""
    try:
        from codegraph.backends import get_backend
        if not get_backend().health_check():
            print(
                "Cannot connect to Neo4j.\n"
                "Ensure the database is running and NEO4J_URI, "
                "NEO4J_USER, NEO4J_PASSWORD are set (or a .env "
                "file is present in the working directory).",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception as exc:
        print(
            f"Neo4j connection check failed: {exc}\n"
            "Ensure the database is running and credentials are correct.",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_mine(args) -> None:
    """Handle the ``mine`` subcommand."""
    if not args.compound and not args.all:
        print("Error: --compound or --all is required", file=sys.stderr)
        sys.exit(1)

    if not mining_available():
        print(
            "LLM mining is not configured.\n"
            "Set LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL, "
            "LLM_BACKEND).",
            file=sys.stderr,
        )
        sys.exit(1)

    _check_neo4j()

    log_dir = args.log_dir or os.environ.get("MINE_LOG_DIR")
    miner = LLRMiner(
        log_dir=log_dir,
        disable_thinking=not args.allow_thinking,
    )
    common = dict(
        model=args.model,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        max_tokens=args.max_tokens,
        agentic=getattr(args, 'agentic', False),
    )

    if args.compound:
        from codegraph.models.compound import (
            ClassNode, InterfaceNode, EnumNode
        )
        compound_node = None
        for cls in [ClassNode, InterfaceNode, EnumNode]:
            try:
                compound_node = cls.nodes.get_or_none(
                    qualified_name=args.compound
                )
                if compound_node:
                    break
            except Exception:
                pass

        if compound_node is None:
            print(f"Compound not found: {args.compound}", file=sys.stderr)
            sys.exit(1)

        result = miner.mine_one(compound_node, **common)
        print(json.dumps(result.to_dict(), indent=2))
    else:
        filters = {}
        if args.tag:
            filters["tag"] = args.tag

        summary = miner.mine_all(**common, **filters)
        print(json.dumps(summary.to_dict(), indent=2))


def _cmd_composite(args) -> None:
    """Handle the ``composite`` subcommand."""
    if not args.namespace and not args.all:
        print(
            "Error: --namespace or --all is required",
            file=sys.stderr,
        )
        sys.exit(1)

    if not mining_available():
        print(
            "LLM mining is not configured.\n"
            "Set LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL, "
            "LLM_BACKEND).",
            file=sys.stderr,
        )
        sys.exit(1)

    _check_neo4j()

    from codegraph_mine import CompositeHLRMiner

    log_dir = args.log_dir or os.environ.get("MINE_LOG_DIR")
    miner = CompositeHLRMiner(
        log_dir=log_dir,
        disable_thinking=not args.allow_thinking,
    )
    common = dict(
        model=args.model,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        max_tokens=args.max_tokens,
        agentic=getattr(args, 'agentic', False),
    )

    if args.namespace:
        from codegraph.models.namespace import NamespaceNode

        ns_node = NamespaceNode.nodes.get_or_none(
            qualified_name=args.namespace
        )
        if ns_node is None:
            print(
                f"Namespace not found: {args.namespace}",
                file=sys.stderr,
            )
            sys.exit(1)

        result = miner.mine_one(ns_node, **common)
        print(json.dumps(result.to_dict(), indent=2))
    else:
        filters = {}
        if args.tag:
            filters["tag"] = args.tag

        summary = miner.mine_all(**common, **filters)
        print(json.dumps(summary.to_dict(), indent=2))


def _cmd_components(args) -> None:
    """Handle the ``components`` subcommand."""
    if not mining_available():
        print(
            "LLM mining is not configured.\n"
            "Set LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL, "
            "LLM_BACKEND).",
            file=sys.stderr,
        )
        sys.exit(1)

    _check_neo4j()

    from codegraph_mine import ComponentMiner

    log_dir = args.log_dir or os.environ.get("MINE_LOG_DIR")
    miner = ComponentMiner(
        log_dir=log_dir,
        disable_thinking=not args.allow_thinking,
    )
    common = dict(
        model=args.model,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        max_tokens=args.max_tokens,
        agentic=getattr(args, 'agentic', False),
    )

    # Component miner is a global operation — one target (ProjectMeta)
    summary = miner.mine_all(**common)
    print(json.dumps(summary.to_dict(), indent=2))


def _cmd_report(args) -> None:
    """Handle the ``report`` subcommand."""
    _check_neo4j()

    md = generate_report(
        tag=args.tag,
        output=args.output,
        include_composite=not args.no_composite,
    )
    if not args.output:
        print(md)


if __name__ == "__main__":
    main()
