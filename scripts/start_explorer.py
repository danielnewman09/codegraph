#!/usr/bin/env python3
"""Start the Codegraph Explorer against the cpp-sqlite integration database.

Boots ``codegraph.explorer.server`` with the sister repo's live sqlite
database (doxygen-index output, identical schema to the codegraph sqlite
backend) and opens the interactive browser app: namespace tree → class →
zoomable class-scoped diagram + requirements/tests narration.

Usage::

    python scripts/start_explorer.py                 # defaults below
    python scripts/start_explorer.py --port 9000
    python scripts/start_explorer.py --db /path/to/other.sqlite3 --tag as-built
    python scripts/start_explorer.py --fixture tests/pipelines/unit_test_data/design_layergraph.json

Defaults::

    db    ../Doxygen-Dependency-Parser/tests/unit_test_data/cpp_sqlite_integration.sqlite3
    tag   as-built
    host  127.0.0.1    port  8765

The explorer serves a static SPA + JSON API; the class-scoped diagrams
are rendered to SVG via the ``plantuml`` CLI (must be on PATH; the puml
text is served as a fallback otherwise).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codegraph.explorer.server import main as server_main

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = (
    _REPO_ROOT.parent
    / "Doxygen-Dependency-Parser"
    / "tests"
    / "unit_test_data"
    / "cpp_sqlite_integration.sqlite3"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="start_explorer",
        description=(
            "Start the Codegraph Explorer web app against a codegraph "
            "sqlite database."
        ),
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="path to a codegraph sqlite database "
             f"(default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--tag",
        default="as-built",
        help="provenance tag to load (default: as-built)",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="instead of the sqlite db, serve a serialized LayerGraph "
             "JSON fixture (fixture:<path>)",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="source checkout the generated code maps to; enables the "
             "edit → doxygen-index → reload loop in the code view",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.fixture:
        source = f"fixture:{args.fixture}"
    else:
        if not Path(args.db).exists():
            print(
                f"error: database not found: {args.db}\n"
                f"  pass --db <path> to a codegraph sqlite database",
                file=sys.stderr,
            )
            return 1
        source = f"sqlite:{args.db}:{args.tag}"

    argv = ["--source", source, "--host", args.host, "--port", str(args.port)]
    if args.project_dir:
        argv += ["--project-dir", args.project_dir]
    return server_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
