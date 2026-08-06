"""SQLite-specific ``codegraph-db`` subcommands (file-copy backup/restore).

Neo4j backups stop a Docker container and use ``neo4j-admin``; SQLite
backups are a plain file copy — SQLite guarantees a consistent snapshot
for a single-writer file copied while no writes are in flight (WAL mode
also makes the ``-wal``/``-shm`` sidecar files part of a safe copy; use
the SQLite backup API via ``SqliteConnection`` for zero-risk copies).

Subcommands added to ``codegraph-db``:

- ``backup --backend sqlite`` — copy the database file (+ WAL/SHM if
  present) into ``<project_dir>/codegraph/backups/``.
- ``restore --backend sqlite`` — copy a backup over the live file,
  creating a safety backup first.
- ``backups --backend sqlite`` — list sqlite backup files.
- ``status --backend sqlite`` — report file state + schema/node counts.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

_BACKUP_SUBDIR = Path("codegraph") / "backups"


def resolve_path(project_dir: str) -> Path:
    """Resolve the SQLite database path for a project directory.

    Precedence: ``SQLITE_PATH`` env var → ``<project_dir>/codegraph.sqlite3``.
    """
    import os

    env_path = os.environ.get("SQLITE_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path(project_dir) / "codegraph.sqlite3"


def is_sqlite_configured(project_dir: str) -> bool:
    """True when the SQLite backend is selected (env or CLI flag)."""
    import os

    return os.environ.get("CODEGRAPH_BACKEND", "sqlite").lower() == "sqlite"


def _backup_dir(project_dir: str) -> Path:
    d = Path(project_dir) / _BACKUP_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def sqlite_backup(
    project_dir: str,
    *,
    keep: int | None = None,
) -> Path:
    """Copy the SQLite database file into the backups directory.

    Uses the SQLite online backup API (``VACUUM INTO``) when possible
    for a consistent snapshot even with a live WAL database; falls back
    to a plain copy.

    Returns the backup path.
    """
    db_path = resolve_path(project_dir)
    if not db_path.exists():
        raise RuntimeError(
            f"No SQLite database at {db_path}. "
            "Set SQLITE_PATH or run the sqlite backend once (create the schema)."
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = _backup_dir(project_dir) / f"sqlite-{db_path.stem}-{stamp}.sqlite3"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            backup = sqlite3.connect(str(out))
            try:
                conn.backup(backup)
            finally:
                backup.close()
        finally:
            conn.close()
    except Exception:
        # Fallback: plain file copy (+ WAL/SHM sidecars if present).
        shutil.copy2(db_path, out)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            if sidecar.exists():
                shutil.copy2(sidecar, Path(f"{out}{suffix}"))

    if keep:
        _rotate(_backup_dir(project_dir), keep)

    size = out.stat().st_size
    print(f"Backed up SQLite database to {out} ({_human(size)}).")
    return out


def sqlite_restore(project_dir: str, backup_file: str) -> None:
    """Restore a SQLite backup over the live database.

    Creates a safety backup of the current database first (mirroring the
    Neo4j restore flow).
    """
    backup_path = Path(backup_file)
    if not backup_path.is_absolute():
        backup_path = _backup_dir(project_dir) / backup_path
    if not backup_path.exists():
        raise RuntimeError(f"Backup file not found: {backup_path}")
    if not backup_path.name.endswith(".sqlite3"):
        raise RuntimeError(
            f"{backup_path.name} does not look like a sqlite backup "
            "(.sqlite3). Refusing to restore."
        )

    db_path = resolve_path(project_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        sqlite_backup(project_dir, keep=1)  # safety snapshot
    # Copy the backup over the live file, then drop stale WAL/SHM.
    shutil.copy2(backup_path, db_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    print(f"Restored {backup_path} -> {db_path}")


def sqlite_list_backups(project_dir: str) -> list[dict]:
    """List sqlite backup files with size and mtime."""
    d = _backup_dir(project_dir)
    entries: list[dict] = []
    for f in sorted(d.glob("sqlite-*.sqlite3"), reverse=True):
        entries.append({
            "name": f.name,
            "size": f.stat().st_size,
            "size_human": _human(f.stat().st_size),
            "mode": "file",
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return entries


def sqlite_status(project_dir: str) -> None:
    """Print file state + schema/node counts for the SQLite database."""
    db_path = resolve_path(project_dir)
    print(f"SQLite database: {db_path}")
    if not db_path.exists():
        print("  status: not created yet (run the backend once to create the schema)")
        return
    print(f"  size: {_human(db_path.stat().st_size)}")
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            print(f"  schema version: {version}")
            print(f"  nodes: {nodes}  edges: {edges}")
            print(f"  journal mode: {journal}")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"  error: {exc}")


def _rotate(d: Path, keep: int) -> None:
    """Delete all but the newest *keep* sqlite backups."""
    files = sorted(d.glob("sqlite-*.sqlite3"), reverse=True)
    for stale in files[keep:]:
        stale.unlink()


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"
