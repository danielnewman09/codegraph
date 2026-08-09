"""``codegraph-codegen`` CLI entry point (mirrors codegraph-html).

Reads ``.codegraph.toml`` (falling back to the ``[codegraph-codegen]``
section of ``.doxygen-index.toml``) via ``cli_config`` to discover the
project name, tag, and output directory.  ``--dry-run`` is the safe
default for planning (prints the planned file tree, writes nothing).

Subcommands (Phase 1):

    codegraph-codegen --dry-run --project-dir ../fixture   # plan only
    codegraph-codegen --output build/codegen --tag design  # write tree
    codegraph-codegen verify                               # uid-diff loop
    codegraph-codegen sync-fixtures push|pull|check        # R1 golden sync
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Raises:
        NotImplementedError: Phase 1 render slice (argparse shell only).
    """
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(
        prog="codegraph-codegen",
        description="Generate source code (C++ first) from a codegraph LayerGraph.",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="Project root containing .codegraph.toml or .doxygen-index.toml",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for the generated tree (default: plan only)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the planned file tree without writing",
    )
    parser.add_argument(
        "--pack", default=None,
        help="Custom TemplatePack directory (overrides the builtin cpp pack)",
    )
    parser.add_argument(
        "--tag", default="design",
        help="Provenance tag to generate from (default: design)",
    )
    args = parser.parse_args(argv)

    raise NotImplementedError(
        "codegraph-codegen CLI: Phase 1 render slice "
        "(config discovery → generate() → write or dry-run)"
    )


if __name__ == "__main__":
    sys.exit(main())
