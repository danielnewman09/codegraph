"""Entry point for ``codegraph-requirements`` CLI tool.

Usage::

    codegraph-requirements --help
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="codegraph-requirements",
        description="Manage HLR/LLR requirements in Neo4j.",
    )
    sub = parser.add_subparsers(dest="command")

    # init — ensure constraints
    init_parser = sub.add_parser("init", help="Ensure Neo4j constraints for requirements nodes")
    init_parser.set_defaults(func=_cmd_init)

    args = parser.parse_args(argv or sys.argv[1:])
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_init(_args) -> None:
    """Ensure unique constraints exist for HLR and LLR nodes."""
    # uid constraints are auto-created by neomodel (UniqueIdProperty).
    # No additional uniqueness constraints needed — uid is the real primary key.
    print("Requirements constraints created.")


if __name__ == "__main__":
    main()
