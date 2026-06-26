"""CLI entry point for ``codegraph-enrich``.

Enriches test node descriptions (or other fields) using an LLM.
Operates directly on the Neo4j codegraph.

Usage::

    codegraph-enrich --all
    codegraph-enrich --all --dry-run
    codegraph-enrich --test "tests::test_engine::test_set_target"
    codegraph-enrich --all --tag as-built --field summary --overwrite

Environment:
    Requires ``LLM_API_KEY`` (and optionally ``LLM_BASE_URL``,
    ``LLM_MODEL``, ``LLM_BACKEND``) or the equivalent ``llm-caller``
    configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from codegraph_enrich import TestEnricher, enrichment_available


def _load_dotenv() -> None:
    """Load .env from the current working directory into os.environ."""
    from pathlib import Path

    dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> None:
    # Load .env from the current working directory so that LLM_API_KEY,
    # LLM_MODEL, etc. are available without manual export.
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Enrich test node descriptions using an LLM.",
    )
    parser.add_argument(
        "--test",
        help="Qualified name of a single TestNode to enrich.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Enrich all test nodes (optionally filtered by --tag).",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Only enrich tests with this provenance tag (e.g. 'as-built').",
    )
    parser.add_argument(
        "--field",
        default="description",
        help="Node attribute to enrich (default: 'description').",
    )
    parser.add_argument(
        "--model",
        default="",
        help="LLM model override (default: llm-caller configured model).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompts and simulate without calling the LLM.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing descriptions (default: skip already-set fields).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum tokens per LLM response (default: 1024).",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Directory for full prompt + response trace logs. "
             "Also settable via ENRICH_LOG_DIR env var. "
             "(default: codegraph/logs/ from .env).",
    )
    parser.add_argument(
        "--allow-thinking",
        action="store_true",
        help="Allow the model to produce reasoning/thinking output. "
             "By default, thinking is suppressed via model-specific mechanisms.",
    )

    args = parser.parse_args(argv)

    if not args.test and not args.all:
        parser.print_help()
        sys.exit(1)

    if not enrichment_available():
        print(
            "LLM enrichment is not configured.\n"
            "Set LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL, LLM_BACKEND).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve log directory: CLI flag > ENRICH_LOG_DIR env > None
    log_dir = args.log_dir or os.environ.get("ENRICH_LOG_DIR")
    enricher = TestEnricher(
        enrichment_field=args.field,
        log_dir=log_dir,
        disable_thinking=not args.allow_thinking,
    )
    common = dict(
        model=args.model,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        max_tokens=args.max_tokens,
    )

    if args.test:
        from codegraph.models.test import TestNode

        try:
            test_node = TestNode.nodes.get(qualified_name=args.test)
        except Exception as exc:
            print(f"TestNode not found: {args.test}", file=sys.stderr)
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        summary = enricher.enrich_one(test_node, **common)
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        filters = {}
        if args.tag:
            filters["tag"] = args.tag

        results = enricher.enrich_all(**common, **filters)

        combined = {
            "total_targets": len(results),
            "total_enriched": sum(s.total_enriched for s in results.values()),
            "total_skipped": sum(s.total_skipped for s in results.values()),
            "total_errors": sum(s.total_errors for s in results.values()),
            "targets": {qn: s.to_dict() for qn, s in results.items()},
        }
        print(json.dumps(combined, indent=2))


if __name__ == "__main__":
    main()
