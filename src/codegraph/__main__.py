"""Entry point for ``python -m codegraph``.

Dispatches subcommands.  Currently supports:

    python -m codegraph viz <tag> [--output <path>] [--size large|small]
"""

import sys

_SUBCOMMANDS = {
    "viz": "codegraph.export.viz:main",
    "db": "codegraph.persistence.db_cli:main",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python -m codegraph <subcommand> [args...]")
        print()
        print("Subcommands:")
        print("  viz    Export a Cytoscape.js HTML graph visualisation")
        print("  db     Manage the project-local Neo4j Docker container")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in _SUBCOMMANDS:
        print(f"Unknown subcommand: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(_SUBCOMMANDS)}", file=sys.stderr)
        sys.exit(1)

    # Delegate to the subcommand
    mod_name, func_name = _SUBCOMMANDS[cmd].rsplit(":", 1)
    import importlib
    mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name)
    func(sys.argv[2:])


if __name__ == "__main__":
    main()
