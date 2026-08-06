"""CLI entry point for ``codegraph-db``.

Manages a project-local Neo4j Docker container.  Each project gets its
own container named ``neo4j-<project_name>`` with data bind-mounted at
``<project_root>/codegraph/neo4j/``.

Usage::

    codegraph-db start [--project-dir DIR] [--no-wait]
    codegraph-db stop  [--project-dir DIR]
    codegraph-db restart [--project-dir DIR]
    codegraph-db status [--project-dir DIR]
    codegraph-db logs   [--project-dir DIR] [--follow]
    codegraph-db shell  [--project-dir DIR]
    codegraph-db browser [--project-dir DIR] [--no-open]
    codegraph-db init   [--project-dir DIR] [--no-pull]
    codegraph-db rm     [--project-dir DIR] [--force]
    codegraph-db backup [--project-dir DIR] [--mode dump|tar] [--keep N]
    codegraph-db restore [--project-dir DIR] [backup_file]
    codegraph-db backups [--project-dir DIR]

Configuration is read from ``.codegraph.toml`` or
``.doxygen-index.toml`` in the project directory.  An optional
``[codegraph-db]`` section customises the image, ports, and password::

    [codegraph-db]
    image = "neo4j:5-community"
    bolt_port = 7687
    http_port = 7474
    password = "codegraph-dev"
"""

from __future__ import annotations

import argparse
import sys

from codegraph.persistence.docker import (
    Neo4jContainerConfig,
    backup_database,
    browser_url,
    init_project,
    list_backups,
    load_container_config,
    open_shell,
    remove_container,
    restart_container,
    restore_database,
    show_logs,
    show_status,
    start_container,
    stop_container,
)


def _add_project_dir_arg(p: argparse.ArgumentParser) -> None:
    """Add the common ``--project-dir`` option."""
    p.add_argument(
        "--project-dir",
        default=".",
        help="Project root containing .codegraph.toml or .doxygen-index.toml "
             "(default: current directory)",
    )


def main(argv: list[str] | None = None) -> None:
    """CLI dispatch for ``codegraph-db``."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="codegraph-db",
        description="Manage a project-local Neo4j Docker container.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- start ---
    p_start = sub.add_parser(
        "start", help="Create and/or start the Neo4j container.",
        description=(
            "Start the project's Neo4j container.  If the container "
            "doesn't exist, it is created with data bind-mounted at "
            "codegraph/neo4j/.  The .env file is updated with the "
            "container's connection info."
        ),
    )
    _add_project_dir_arg(p_start)
    p_start.add_argument(
        "--no-wait", action="store_true",
        help="Don't wait for Neo4j to become reachable before returning.",
    )

    # --- stop ---
    p_stop = sub.add_parser(
        "stop", help="Stop the container (data is preserved on disk).",
        description="Stop the project's Neo4j container. Data on disk is preserved.",
    )
    _add_project_dir_arg(p_stop)

    # --- restart ---
    p_restart = sub.add_parser(
        "restart", help="Restart the container.",
        description="Restart the project's Neo4j container.",
    )
    _add_project_dir_arg(p_restart)

    # --- status ---
    p_status = sub.add_parser(
        "status", help="Show container status and connection info.",
        description="Print the container's state, ports, data directory, and "
                    "Bolt connectivity check. With --backend sqlite, prints "
                    "the SQLite file state instead.",
    )
    _add_project_dir_arg(p_status)
    p_status.add_argument(
        "--backend", choices=["auto", "neo4j", "sqlite"], default="auto",
        help="Which backend to report on (default: auto).",
    )

    # --- logs ---
    p_logs = sub.add_parser(
        "logs", help="Show container logs.",
        description="Print the Neo4j container's logs.",
    )
    _add_project_dir_arg(p_logs)
    p_logs.add_argument(
        "-f", "--follow", action="store_true",
        help="Stream logs continuously.",
    )

    # --- shell ---
    p_shell = sub.add_parser(
        "shell", help="Open an interactive Cypher shell.",
        description="Open a cypher-shell session inside the running container.",
    )
    _add_project_dir_arg(p_shell)

    # --- browser ---
    p_browser = sub.add_parser(
        "browser", help="Print / open the Neo4j Browser URL.",
        description="Print the Neo4j Browser URL and optionally open it.",
    )
    _add_project_dir_arg(p_browser)
    p_browser.add_argument(
        "--no-open", action="store_true",
        help="Print the URL but don't open a browser.",
    )

    # --- init ---
    p_init = sub.add_parser(
        "init", help="Create directories and pull image without starting.",
        description=(
            "Create the codegraph/neo4j/ directory tree, optionally pull "
            "the Docker image, and update .env — all without starting the "
            "container."
        ),
    )
    _add_project_dir_arg(p_init)
    p_init.add_argument(
        "--no-pull", action="store_true",
        help="Skip pulling the Docker image.",
    )

    # --- rm ---
    p_rm = sub.add_parser(
        "rm", help="Remove the container (data files are preserved).",
        description="Remove the Neo4j container. Bind-mounted data on disk is "
                    "preserved — only the container itself is removed.",
    )
    _add_project_dir_arg(p_rm)
    p_rm.add_argument(
        "--force", action="store_true",
        help="Remove even if the container is currently running.",
    )

    # --- backup ---
    p_backup = sub.add_parser(
        "backup", help="Create a database backup (dump, tar, or file copy).",
        description=(
            "Create a backup of the database. Neo4j: the container is briefly "
            "stopped for a consistent snapshot, then restarted. SQLite: a "
            "consistent file copy (no Docker)."
        ),
    )
    _add_project_dir_arg(p_backup)
    p_backup.add_argument(
        "--backend", choices=["auto", "neo4j", "sqlite"], default="auto",
        help="Backend to back up. 'auto' uses CODEGRAPH_BACKEND / SQLITE_PATH "
             "(default: sqlite).",
    )
    p_backup.add_argument(
        "--mode", choices=["dump", "tar"], default="dump",
        help="Backup mode (Neo4j only): 'dump' (logical neo4j-admin dump, "
             "default) or 'tar' (filesystem-level tar.gz).",
    )
    p_backup.add_argument(
        "--keep", type=int, default=None,
        help="Rotate backups: keep only the last N files of this mode.",
    )

    # --- restore ---
    p_restore = sub.add_parser(
        "restore", help="Restore the database from a backup file.",
        description=(
            "Restore the database from a backup file. WARNING: this "
            "destroys the current database. A safety backup is created first. "
            "Neo4j restores from a container; SQLite restores by file copy."
        ),
    )
    _add_project_dir_arg(p_restore)
    p_restore.add_argument(
        "--backend", choices=["auto", "neo4j", "sqlite"], default="auto",
        help="Backend to restore into. 'auto' uses CODEGRAPH_BACKEND (default: sqlite).",
    )
    p_restore.add_argument(
        "backup_file", nargs="?", default="",
        help="Backup file to restore. If omitted, lists available backups.",
    )

    # --- backups ---
    p_backups = sub.add_parser(
        "backups", help="List available backup files.",
        description="List all backup files with size, mode, and timestamp.",
    )
    _add_project_dir_arg(p_backups)
    p_backups.add_argument(
        "--backend", choices=["auto", "neo4j", "sqlite"], default="auto",
        help="Which backend's backups to list (default: auto).",
    )

    args = parser.parse_args(argv)

    from codegraph.persistence import sqlite_cli

    def _backend_is(args) -> bool:
        """Resolve --backend: explicit flag wins; else CODEGRAPH_BACKEND."""
        flag = getattr(args, "backend", "auto")
        if flag == "sqlite":
            return True
        if flag == "neo4j":
            return False
        return sqlite_cli.is_sqlite_configured(args.project_dir)

    cfg: Neo4jContainerConfig | None = None

    def _config() -> Neo4jContainerConfig:
        """Load the container config lazily (not needed for sqlite)."""
        nonlocal cfg
        if cfg is None:
            cfg = load_container_config(args.project_dir)
        return cfg

    if args.command == "start":
        start_container(_config(), wait=not args.no_wait)
    elif args.command == "stop":
        stop_container(_config())
    elif args.command == "restart":
        restart_container(_config())
    elif args.command == "status":
        if _backend_is(args):
            sqlite_cli.sqlite_status(args.project_dir)
        else:
            show_status(_config())
    elif args.command == "logs":
        show_logs(_config(), follow=args.follow)
    elif args.command == "shell":
        sys.exit(open_shell(_config()))
    elif args.command == "browser":
        browser_url(_config(), open_browser=not args.no_open)
    elif args.command == "init":
        init_project(_config(), pull=not args.no_pull)
    elif args.command == "rm":
        remove_container(_config(), force=args.force)
    elif args.command == "backup":
        if _backend_is(args):
            sqlite_cli.sqlite_backup(args.project_dir, keep=args.keep)
        else:
            backup_database(_config(), mode=args.mode, keep=args.keep)
    elif args.command == "restore":
        if _backend_is(args):
            if not args.backup_file:
                backups = sqlite_cli.sqlite_list_backups(args.project_dir)
                if not backups:
                    print("No backups found.")
                else:
                    print(f"Available backups in {args.project_dir}/codegraph/backups:")
                    for b in backups:
                        print(f"  {b['name']}  ({b['size_human']}, {b['mode']}, {b['mtime']})")
                    print("\nUsage: codegraph-db restore <backup_file> --backend sqlite")
            else:
                sqlite_cli.sqlite_restore(args.project_dir, args.backup_file)
        elif not args.backup_file:
            # List available backups if no file specified.
            backups = list_backups(_config())
            if not backups:
                print("No backups found.")
            else:
                print(f"Available backups in {_config().neo4j_dir / 'backups'}:")
                for b in backups:
                    print(f"  {b['name']}  ({b['size_human']}, {b['mode']}, {b['mtime']})")
                print(f"\nUsage: codegraph-db restore <backup_file>")
        else:
            restore_database(_config(), args.backup_file)
    elif args.command == "backups":
        if _backend_is(args):
            backups = sqlite_cli.sqlite_list_backups(args.project_dir)
            if not backups:
                print("No backups found.")
            else:
                print(f"Backups in {args.project_dir}/codegraph/backups:")
                for b in backups:
                    print(f"  {b['name']}  ({b['size_human']}, {b['mode']}, {b['mtime']})")
        else:
            backups = list_backups(_config())
            if not backups:
                print("No backups found.")
            else:
                print(f"Backups in {_config().neo4j_dir / 'backups'}:")
                for b in backups:
                    print(f"  {b['name']}  ({b['size_human']}, {b['mode']}, {b['mtime']})")


if __name__ == "__main__":
    main()