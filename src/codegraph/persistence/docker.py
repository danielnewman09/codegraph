"""Docker container management for project-local Neo4j instances.

Provides a modular, per-project Neo4j container strategy.  Each project
that depends on *codegraph* gets its own Docker container named
``neo4j-<project_name>`` with the Neo4j data files bind-mounted under
``<project_root>/codegraph/neo4j/``.  This keeps every project's graph
data self-contained, portable, and version-controllable (minus the
binary data directory, which is git-ignored).

Directory layout created on ``init`` / first ``start``::

    <project_root>/
    └── codegraph/
        └── neo4j/
            ├── data/       →  /data        (database files — persisted)
            ├── logs/       →  /logs        (server logs)
            ├── import/     →  /import      (bulk-import CSVs)
            └── plugins/    →  /plugins     (APOC, etc.)

Configuration is read from the same TOML files the rest of codegraph
uses (``.codegraph.toml`` or ``.doxygen-index.toml``), via an optional
``[codegraph-db]`` section::

    [codegraph-db]
    image = "neo4j:5-community"
    bolt_port = 7687
    http_port = 7474
    password = "codegraph-dev"

Only the project name (from ``[project].name``) is required; every
``[codegraph-db]`` field has a sensible default.

Typical workflow::

    # 1. Initialise directories (optional — start does this too)
    codegraph-db init

    # 2. Start the container (creates it if needed, loads persisted data)
    codegraph-db start

    # 3. Verify connectivity
    codegraph-db status

    # 4. Open a Cypher shell
    codegraph-db shell

    # 5. Stop when done (data is preserved on disk)
    codegraph-db stop

The project's ``.env`` file is automatically updated on ``start`` so
that ``NEO4J_URI``, ``NEO4J_USER``, and ``NEO4J_PASSWORD`` point at the
running container — no manual env management needed.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover — Python 3.11+
    import tomli as tomllib  # type: ignore[no-redef]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default Neo4j Community image tag.
DEFAULT_IMAGE = "neo4j:5-community"

#: Default Bolt port (binary protocol — used by neomodel / neo4j driver).
# TODO: This should probably be ignored in favor of the config.toml
DEFAULT_BOLT_PORT = 7687

#: Default HTTP port (Neo4j Browser + REST API).
# TODO: This should probably be ignored in favor of the config.toml
DEFAULT_HTTP_PORT = 7474

#: Default initial password (only applied on first database creation).
# TODO: This should probably be ignored in favor of the config.toml
DEFAULT_PASSWORD = "codegraph"

#: Subdirectory under ``codegraph/`` that holds the Neo4j data tree.
NEO4J_SUBDIR = "neo4j"

#: Named volumes inside that subdirectory.
NEO4J_VOLUME_DIRS = ("data", "logs", "import", "plugins")

#: Config-file section name.
DB_CONFIG_SECTION = "codegraph-db"

#: Maximum seconds to wait for Neo4j to become reachable after start.
START_TIMEOUT_S = 60

#: Polling interval (seconds) when waiting for connectivity.
POLL_INTERVAL_S = 2


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Neo4jContainerConfig:
    """Resolved configuration for a project's Neo4j Docker container.

    Attributes:
        project_name: Sanitized project name (from ``[project].name``).
        project_dir: Absolute path to the project root.
        container_name: Docker container name — ``neo4j-<project_name>``.
        neo4j_dir: Absolute path to ``<project_dir>/codegraph/neo4j/``.
        image: Docker image reference (e.g. ``neo4j:5-community``).
        bolt_port: Host port mapped to the container's Bolt listener.
        http_port: Host port mapped to the container's HTTP listener.
        password: Initial Neo4j password (applied only on first run).
        config_source: Name of the TOML file the settings came from.
    """

    project_name: str
    project_dir: Path
    container_name: str
    neo4j_dir: Path
    image: str = DEFAULT_IMAGE
    bolt_port: int = DEFAULT_BOLT_PORT
    http_port: int = DEFAULT_HTTP_PORT
    password: str = DEFAULT_PASSWORD
    config_source: str = ".doxygen-index.toml"


def _sanitize_container_name(name: str) -> str:
    """Make *name* safe for use as a Docker container name.

    Docker container names must match ``[a-zA-Z0-9][a-zA-Z0-9_.-]*``.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "-", name)
    sanitized = re.sub(r"^[^a-zA-Z0-9]", "x", sanitized)
    return sanitized


def load_container_config(
    project_dir: Path | str = ".",
) -> Neo4jContainerConfig:
    """Resolve Neo4j container settings from the project's TOML config.

    Reads ``.codegraph.toml`` first, then ``.doxygen-index.toml``
    (same priority as the HTML exporter).  The project name comes from
    ``[project].name``; the optional ``[codegraph-db]`` section
    provides Docker-specific overrides.

    Args:
        project_dir: Directory containing the config file.

    Returns:
        A fully resolved :class:`Neo4jContainerConfig`.

    Raises:
        SystemExit: If no config file is found or ``[project].name``
            is absent.
    """
    project_dir = Path(project_dir).resolve()

    codegraph_path = project_dir / ".codegraph.toml"
    doxygen_path = project_dir / ".doxygen-index.toml"

    if codegraph_path.exists():
        config_path = codegraph_path
        config_source = ".codegraph.toml"
    elif doxygen_path.exists():
        config_path = doxygen_path
        config_source = ".doxygen-index.toml"
    else:
        print(
            f"Error: no .codegraph.toml or .doxygen-index.toml found "
            f"in {project_dir}.",
            file=sys.stderr,
        )
        print(
            "Create one with at least a [project] section:\n\n"
            '[project]\nname = "my-project"\n',
            file=sys.stderr,
        )
        sys.exit(1)

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    proj = data.get("project", {})

    if "name" not in proj:
        print(
            f"Error: [project] section must specify 'name' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_name = proj["name"]
    project_name = _sanitize_container_name(raw_name)

    db_section = data.get(DB_CONFIG_SECTION, {})

    # The database container follows the current project configuration.
    # Legacy .doxygen-index.toml files use the standard codegraph directory;
    # the retired HTML exporter no longer supplies a configuration override.
    output_dir_raw = proj.get("output_dir", "codegraph")

    codegraph_dir = (project_dir / output_dir_raw).resolve()
    neo4j_dir = codegraph_dir / NEO4J_SUBDIR

    return Neo4jContainerConfig(
        project_name=project_name,
        project_dir=project_dir,
        container_name=f"neo4j-{project_name}",
        neo4j_dir=neo4j_dir,
        image=db_section.get("image", DEFAULT_IMAGE),
        bolt_port=int(db_section.get("bolt_port", DEFAULT_BOLT_PORT)),
        http_port=int(db_section.get("http_port", DEFAULT_HTTP_PORT)),
        password=db_section.get("password", DEFAULT_PASSWORD),
        config_source=config_source,
    )


# ---------------------------------------------------------------------------
# Docker plumbing
# ---------------------------------------------------------------------------


def _docker(*args: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """Run a ``docker`` CLI command.

    Args:
        *args: Arguments passed to ``docker``.
        capture: If True, capture stdout/stderr instead of inheriting.
        check: If True, raise on non-zero exit.
    """
    cmd = ["docker", *args]
    log.debug("docker %s", " ".join(args))
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
    )


def docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    try:
        result = _docker("info", capture=True, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _container_exists(cfg: Neo4jContainerConfig) -> bool:
    """Return True if a container with the configured name exists."""
    result = _docker(
        "ps", "-a", "--filter", f"name=^{cfg.container_name}$",
        "--format", "{{.Names}}", capture=True, check=False,
    )
    return cfg.container_name in result.stdout.split()


def _container_state(cfg: Neo4jContainerConfig) -> str:
    """Return the Docker status of the container, or ``"absent"``."""
    if not _container_exists(cfg):
        return "absent"
    result = _docker(
        "ps", "-a", "--filter", f"name=^{cfg.container_name}$",
        "--format", "{{.Status}}", capture=True, check=False,
    )
    status = result.stdout.strip()
    if status.startswith("Up"):
        return "running"
    if status.startswith("Exited"):
        return "stopped"
    return status or "unknown"


# ---------------------------------------------------------------------------
# Directory management
# ---------------------------------------------------------------------------


def ensure_directories(cfg: Neo4jContainerConfig) -> Path:
    """Create the Neo4j data tree under ``codegraph/neo4j/``.

    On Linux the directories are chowned to uid/gid 7474 (the neo4j
    user inside the container).  On macOS, Docker Desktop's virtiofs
    layer handles permission mapping transparently.

    Returns:
        The absolute path to the ``neo4j/`` directory.
    """
    cfg.neo4j_dir.mkdir(parents=True, exist_ok=True)
    for sub in NEO4J_VOLUME_DIRS:
        (cfg.neo4j_dir / sub).mkdir(exist_ok=True)

    # On Linux, Neo4j inside the container runs as uid 7474.
    # Bind-mounted directories must be writable by that user.
    if platform.system() == "Linux":
        for sub in NEO4J_VOLUME_DIRS:
            target = cfg.neo4j_dir / sub
            subprocess.run(
                ["sudo", "chown", "-R", "7474:7474", str(target)],
                check=False,
            )

    return cfg.neo4j_dir


# ---------------------------------------------------------------------------
# .env management
# ---------------------------------------------------------------------------

#: Lines in .env that codegraph-db manages (between markers).
_ENV_BEGIN = "# >>> codegraph-db >>>"
_ENV_END = "# <<< codegraph-db <<<"


def update_env_file(cfg: Neo4jContainerConfig) -> Path:
    """Update the project's ``.env`` file with the container's connection info.

    Inserts/replace a managed block delimited by marker comments so that
    repeated ``start`` calls stay idempotent.  Lines outside the block
    are preserved verbatim.

    Returns:
        Path to the ``.env`` file.
    """
    env_path = cfg.project_dir / ".env"
    managed_block = (
        f"{_ENV_BEGIN}\n"
        f"NEO4J_URI=bolt://localhost:{cfg.bolt_port}\n"
        f"NEO4J_USER=neo4j\n"
        f"NEO4J_PASSWORD={cfg.password}\n"
        f"{_ENV_END}"
    )

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        # Replace existing managed block, or strip stale NEO4J_* lines.
        if _ENV_BEGIN in content and _ENV_END in content:
            pattern = re.compile(
                re.escape(_ENV_BEGIN) + r".*?" + re.escape(_ENV_END),
                re.DOTALL,
            )
            content = pattern.sub(managed_block, content)
        else:
            # Remove any unmanaged NEO4J_* lines to avoid conflicts.
            lines = [
                line for line in content.splitlines()
                if not line.strip().startswith("NEO4J_")
            ]
            lines.append(managed_block)
            content = "\n".join(lines) + "\n"
        env_path.write_text(content, encoding="utf-8")
    else:
        env_path.write_text(managed_block + "\n", encoding="utf-8")

    return env_path


# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------


def _docker_run_args(cfg: Neo4jContainerConfig) -> list[str]:
    """Build the ``docker run`` argument list for *cfg*."""
    args = [
        "run",
        "-d",
        "--name", cfg.container_name,
        "--restart", "unless-stopped",
        "-p", f"{cfg.bolt_port}:7687",
        "-p", f"{cfg.http_port}:7474",
        "-v", f"{cfg.neo4j_dir / 'data'}:/data",
        "-v", f"{cfg.neo4j_dir / 'logs'}:/logs",
        "-v", f"{cfg.neo4j_dir / 'import'}:/import",
        "-v", f"{cfg.neo4j_dir / 'plugins'}:/plugins",
        "-e", f"NEO4J_AUTH=neo4j/{cfg.password}",
        "-e", "NEO4J_PLUGINS=[]",
        cfg.image,
    ]
    return args


def start_container(
    cfg: Neo4jContainerConfig,
    *,
    detach: bool = True,
    wait: bool = True,
) -> None:
    """Start (or create and start) the project's Neo4j container.

    * If the container doesn't exist, it is created from *cfg.image*
      with the data directories bind-mounted.
    * If it exists but is stopped, it is started.
    * If it is already running, nothing happens.

    The project's ``.env`` is updated with the container's connection
    info so that ``codegraph`` itself can connect immediately.

    Args:
        cfg: Resolved container configuration.
        detach: Run the container in the background (default).
        wait: Wait for Neo4j to accept connections before returning.
    """
    if not docker_available():
        print("Error: Docker daemon is not running or docker is not on PATH.",
              file=sys.stderr)
        sys.exit(1)

    ensure_directories(cfg)

    state = _container_state(cfg)

    if state == "running":
        print(f"Container {cfg.container_name} is already running.")
        print(f"  Bolt:  bolt://localhost:{cfg.bolt_port}")
        print(f"  Browser: http://localhost:{cfg.http_port}")
        update_env_file(cfg)
        return

    if state == "absent":
        print(f"Creating container {cfg.container_name} ...")
        print(f"  Image:   {cfg.image}")
        print(f"  Data:    {cfg.neo4j_dir / 'data'}")
        print(f"  Bolt:    localhost:{cfg.bolt_port} → 7687")
        print(f"  Browser: localhost:{cfg.http_port} → 7474")
        _docker(*_docker_run_args(cfg))
    else:
        # stopped — just start it
        print(f"Starting existing container {cfg.container_name} ...")
        _docker("start", cfg.container_name)

    update_env_file(cfg)

    if wait:
        print("Waiting for Neo4j to become reachable ...", end=" ", flush=True)
        if _wait_for_bolt(cfg):
            print("ready.")
            print(f"\n  Bolt:    bolt://localhost:{cfg.bolt_port}")
            print(f"  Browser: http://localhost:{cfg.http_port}")
            print(f"  User:    neo4j / {cfg.password}")
        else:
            print("timed out — container started but Neo4j may still be "
                  "initialising.")
            print(f"  Check logs: codegraph-db logs")


def stop_container(cfg: Neo4jContainerConfig) -> None:
    """Stop the project's Neo4j container (data is preserved on disk)."""
    state = _container_state(cfg)
    if state == "absent":
        print(f"No container named {cfg.container_name} exists.")
        return
    if state == "stopped":
        print(f"Container {cfg.container_name} is already stopped.")
        return
    print(f"Stopping {cfg.container_name} ...")
    _docker("stop", cfg.container_name)
    print(f"Stopped.  Data preserved at {cfg.neo4j_dir / 'data'}")


def restart_container(cfg: Neo4jContainerConfig) -> None:
    """Restart the container (stops, then starts, waiting for Bolt)."""
    state = _container_state(cfg)
    if state == "absent":
        print(f"No container named {cfg.container_name} exists.")
        print("Use 'codegraph-db start' to create one.")
        sys.exit(1)
    print(f"Restarting {cfg.container_name} ...")
    _docker("restart", cfg.container_name)
    print("Waiting for Neo4j to become reachable ...", end=" ", flush=True)
    if _wait_for_bolt(cfg):
        print("ready.")
    else:
        print("timed out.")


def remove_container(cfg: Neo4jContainerConfig, *, force: bool = False) -> None:
    """Remove the container (the bind-mounted data on disk is untouched).

    Args:
        cfg: Resolved container configuration.
        force: Remove even if the container is running.
    """
    state = _container_state(cfg)
    if state == "absent":
        print(f"No container named {cfg.container_name} exists.")
        return
    if not force and state == "running":
        print(f"Container {cfg.container_name} is running. "
              "Use --force to remove it anyway.")
        sys.exit(1)
    if state == "running":
        _docker("stop", cfg.container_name, check=False)
    _docker("rm", cfg.container_name)
    print(f"Removed container {cfg.container_name}.")
    print(f"Data files preserved at {cfg.neo4j_dir / 'data'}")


# ---------------------------------------------------------------------------
# Inspection / interaction
# ---------------------------------------------------------------------------


def show_status(cfg: Neo4jContainerConfig) -> None:
    """Print a human-readable status report for the container."""
    state = _container_state(cfg)
    print(f"Project:      {cfg.project_name}")
    print(f"Container:    {cfg.container_name}")
    print(f"State:        {state}")
    print(f"Image:        {cfg.image}")
    print(f"Data dir:     {cfg.neo4j_dir / 'data'}")
    print(f"Config from:  {cfg.config_source}")
    if state == "running":
        print(f"Bolt URI:     bolt://localhost:{cfg.bolt_port}")
        print(f"Browser URL:  http://localhost:{cfg.http_port}")
        print(f"Credentials:  neo4j / {cfg.password}")
        reachable = _check_bolt(cfg)
        print(f"Bolt ping:    {'✓ reachable' if reachable else '✗ no response'}")
    elif state == "absent":
        print("\nUse 'codegraph-db start' to create and start the container.")
    else:
        print("\nUse 'codegraph-db start' to start the container.")


def show_logs(cfg: Neo4jContainerConfig, *, follow: bool = False) -> None:
    """Print container logs (optionally tailing).

    Args:
        cfg: Resolved container configuration.
        follow: If True, stream logs until interrupted (``-f``).
    """
    state = _container_state(cfg)
    if state == "absent":
        print(f"No container named {cfg.container_name} exists.")
        sys.exit(1)
    args = ["logs", cfg.container_name]
    if follow:
        args.insert(1, "-f")
    # Don't check — we want to see output even if it exits non-zero.
    _docker(*args, check=False)


def open_shell(cfg: Neo4jContainerConfig) -> int:
    """Open an interactive ``cypher-shell`` session in the container.

    Returns the shell's exit code.
    """
    state = _container_state(cfg)
    if state != "running":
        print(f"Container {cfg.container_name} is not running (state: {state}).",
              file=sys.stderr)
        print("Start it first with 'codegraph-db start'.", file=sys.stderr)
        sys.exit(1)
    print(f"Opening Cypher shell in {cfg.container_name} ...")
    print(f"  (neo4j / {cfg.password})  —  type :exit to quit.\n")
    result = subprocess.run([
        "docker", "exec", "-it", cfg.container_name,
        "cypher-shell",
        "-u", "neo4j",
        "-p", cfg.password,
        "-a", "bolt://localhost:7687",
    ])
    return result.returncode


def browser_url(cfg: Neo4jContainerConfig, *, open_browser: bool = True) -> str:
    """Return (and optionally open) the Neo4j Browser URL."""
    url = f"http://localhost:{cfg.http_port}"
    print(f"Neo4j Browser: {url}")
    print(f"  Connect URL: bolt://localhost:{cfg.bolt_port}")
    print(f"  Username:    neo4j")
    print(f"  Password:    {cfg.password}")
    if open_browser:
        _open_in_browser(url)
    return url


def _open_in_browser(url: str) -> None:
    """Open *url* in the default web browser (best-effort)."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", url], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", url], check=False)
        else:
            subprocess.run(["cmd", "/c", "start", url], check=False)
    except FileNotFoundError:
        pass  # No opener available — URL was already printed.


# ---------------------------------------------------------------------------
# Connectivity checks
# ---------------------------------------------------------------------------


def _check_bolt(cfg: Neo4jContainerConfig) -> bool:
    """Return True if Neo4j accepts a Bolt connection on *cfg.bolt_port*.

    Uses the neo4j Python driver's connectivity check (a real Bolt
    handshake) rather than a bare TCP socket probe, so it only returns
    True once Neo4j is fully ready to serve queries.
    """
    from neo4j import GraphDatabase
    try:
        driver = GraphDatabase.driver(
            f"bolt://localhost:{cfg.bolt_port}",
            auth=("neo4j", cfg.password),
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


def _check_bolt_port(cfg: Neo4jContainerConfig) -> bool:
    """Quick TCP-level check — is the Bolt port open at all?

    Used as a fast pre-filter before the slower driver handshake.
    """
    import socket
    try:
        with socket.create_connection(
            ("localhost", cfg.bolt_port), timeout=2,
        ):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _wait_for_bolt(cfg: Neo4jContainerConfig, timeout: int = START_TIMEOUT_S) -> bool:
    """Poll until Neo4j accepts Bolt connections or *timeout* expires.

    Two-phase strategy:
    1. Fast-poll the TCP port until it opens (sub-second intervals).
    2. Once the port is open, run a real Bolt handshake via the neo4j
       driver to confirm the database is fully initialised.
    """
    deadline = time.monotonic() + timeout
    # Phase 1: wait for the port to open
    while time.monotonic() < deadline:
        if _check_bolt_port(cfg):
            break
        time.sleep(1)
    # Phase 2: wait for the Bolt handshake to succeed
    while time.monotonic() < deadline:
        if _check_bolt(cfg):
            return True
        time.sleep(POLL_INTERVAL_S)
    return False


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init_project(cfg: Neo4jContainerConfig, *, pull: bool = True) -> None:
    """Prepare a project for Neo4j without starting the container.

    Creates the directory tree and optionally pulls the Docker image.

    Args:
        cfg: Resolved container configuration.
        pull: If True, pull the Docker image.
    """
    ensure_directories(cfg)
    print(f"Neo4j data directory: {cfg.neo4j_dir}")
    for sub in NEO4J_VOLUME_DIRS:
        print(f"  {sub}/")

    if pull:
        print(f"\nPulling image {cfg.image} ...")
        _docker("pull", cfg.image)

    update_env_file(cfg)
    print(f"\n.env updated at {cfg.project_dir / '.env'}")
    print("\nRun 'codegraph-db start' to launch the container.")


# ---------------------------------------------------------------------------
# Backup / Restore / List
# ---------------------------------------------------------------------------

#: Subdirectory under ``codegraph/neo4j/`` for backup files.
BACKUP_SUBDIR = "backups"

#: Neo4j logical database name (Community Edition always uses "neo4j").
_DB_NAME = "neo4j"


def _backup_dir(cfg: Neo4jContainerConfig) -> Path:
    """Return the backup directory, creating it if necessary."""
    d = cfg.neo4j_dir / BACKUP_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_database(
    cfg: Neo4jContainerConfig,
    *,
    mode: str = "dump",
    keep: int | None = None,
) -> Path:
    """Create a backup of the Neo4j database.

    Two modes are supported:

    - ``mode="dump"`` (default): a logical dump via ``neo4j-admin
      database dump``.  Produces a portable, consistent ``.dump`` file
      that can be restored to any Neo4j 5.x Community instance.  The
      container is briefly stopped (typically < 30 s downtime).
    - ``mode="tar"``: a fast filesystem-level tar of the entire data
      directory.  Also requires the container to be stopped.

    After the backup is created, the container is restarted and the
    backup file's integrity is verified (for dump mode).

    Args:
        cfg: Resolved container configuration.
        mode: ``"dump"`` or ``"tar"``.
        keep: If set, rotate backups of the same mode keeping only the
            last *keep* files.

    Returns:
        The path to the created backup file.

    Raises:
        RuntimeError: If the container is not running or the backup
            fails.
    """
    from datetime import datetime

    if not docker_available():
        raise RuntimeError("Docker daemon is not running or docker is not on PATH.")

    state = _container_state(cfg)
    if state != "running":
        raise RuntimeError(
            f"Container {cfg.container_name} is not running (state: {state}). "
            "Start it first with codegraph-db start."
        )

    bdir = _backup_dir(cfg)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    print(f"=== Neo4j backup started at {datetime.now().isoformat()} ===")
    print(f"  Mode:      {mode}")
    print(f"  Container: {cfg.container_name}")
    print(f"  Backups:   {bdir}")

    # Stop the container for a consistent snapshot.
    print(f"Stopping {cfg.container_name} ...")
    _docker("stop", cfg.container_name)

    backup_file: Path
    try:
        if mode == "dump":
            print("Creating logical dump via neo4j-admin ...")
            _docker(
                "run", "--rm",
                "-v", f"{cfg.neo4j_dir / 'data'}:/data",
                "-v", f"{bdir}:/backups",
                cfg.image,
                "neo4j-admin", "database", "dump", _DB_NAME,
                "--to-path=/backups",
            )
            # neo4j-admin names the dump "<dbname>.dump"
            backup_file = bdir / f"neo4j-{timestamp}.dump"
            (bdir / f"{_DB_NAME}.dump").rename(backup_file)

            # Integrity check: Neo4j 5.x dumps use Zstandard (magic: DZV1).
            with open(backup_file, "rb") as f:
                magic = f.read(4)
            if magic == b"DZV1":
                print(f"Integrity: header check PASSED (Neo4j 5.x Zstd dump)")
            else:
                print(f"WARNING: unexpected dump header {magic!r} - file may be corrupt")

        elif mode == "tar":
            print("Creating tar backup of data directory ...")
            backup_file = bdir / f"neo4j-data-{timestamp}.tar.gz"
            subprocess.run(
                ["tar", "-czf", str(backup_file),
                 "-C", str(cfg.neo4j_dir), "data"],
                check=True,
            )
        else:
            raise ValueError(f"Unknown backup mode: {mode!r}. Use 'dump' or 'tar'.")

    except Exception:
        # Always restart the container even if the backup fails.
        print(f"Starting {cfg.container_name} (after backup failure) ...")
        _docker("start", cfg.container_name)
        raise

    # Restart the container.
    print(f"Starting {cfg.container_name} ...")
    _docker("start", cfg.container_name)

    size = backup_file.stat().st_size
    size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"
    print(f"Backup: {backup_file}  ({size_str})")

    # Retention: rotate old backups of the same mode.
    if keep is not None and keep > 0:
        print(f"Rotating backups: keeping last {keep} ...")
        if mode == "dump":
            pattern = "neo4j-*.dump"
        else:
            pattern = "neo4j-data-*.tar.gz"
        files = sorted(bdir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            print(f"  Deleting {old.name}")
            old.unlink()

    print(f"=== Backup complete at {datetime.now().isoformat()} ===")
    return backup_file


def restore_database(
    cfg: Neo4jContainerConfig,
    backup_file: str | Path,
) -> Path:
    """Restore the Neo4j database from a backup file.

    **WARNING**: This destroys the current database.  The function:

    1. Creates a safety tar backup of the current state.
    2. Stops the container.
    3. Wipes the data directory.
    4. Restores from the backup (``.dump`` via neo4j-admin, or ``.tar.gz``
       via tar extraction).
    5. Fixes permissions.
    6. Restarts the container.

    Args:
        cfg: Resolved container configuration.
        backup_file: Path to the backup file.  If relative, resolved
            against the backup directory.

    Returns:
        The resolved path of the backup file that was restored.

    Raises:
        FileNotFoundError: If the backup file does not exist.
        RuntimeError: If the container is not available.
        ValueError: If the backup format is unrecognized.
    """
    from datetime import datetime

    if not docker_available():
        raise RuntimeError("Docker daemon is not running or docker is not on PATH.")

    bdir = _backup_dir(cfg)
    backup_path = Path(backup_file)
    if not backup_path.is_absolute():
        backup_path = bdir / backup_path
    if not backup_path.exists():
        raise FileNotFoundError(
            f"Backup file not found: {backup_path}"
            f"{chr(10)}Available backups:{chr(10)}"
            f"{list_backups(cfg)}"
        )

    data_dir = cfg.neo4j_dir / "data"

    print(f"=== Restore started at {datetime.now().isoformat()} ===")
    print(f"  Backup:  {backup_path}")
    print(f"  Data:    {data_dir}")

    # Safety backup of current state before restore.
    print("\nCreating safety backup of current state before restore ...")
    try:
        backup_database(cfg, mode="tar")
    except Exception as exc:
        print(f"WARNING: safety backup failed: {exc}")
        print("  Proceeding with restore anyway.")

    # Stop the container.
    _docker("stop", cfg.container_name, check=False)

    # Wipe current data.
    print("Wiping current data ...")
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Restore.
    if backup_path.name.endswith(".dump"):
        print("Restoring from neo4j-admin dump ...")
        # neo4j-admin load requires --from-path to be a directory containing
        # the dump named <dbname>.dump.  Create a staging dir.
        import tempfile
        with tempfile.TemporaryDirectory() as staging:
            staging_path = Path(staging)
            shutil.copy2(backup_path, staging_path / f"{_DB_NAME}.dump")
            _docker(
                "run", "--rm",
                "-v", f"{data_dir}:/data",
                "-v", f"{staging_path}:/backups:ro",
                cfg.image,
                "neo4j-admin", "database", "load", _DB_NAME,
                "--from-path=/backups",
                "--overwrite-destination=true",
            )
    elif backup_path.name.endswith(".tar.gz"):
        print("Restoring from tar archive ...")
        subprocess.run(
            ["tar", "-xzf", str(backup_path),
             "-C", str(cfg.neo4j_dir)],
            check=True,
        )
    else:
        raise ValueError(
            f"Unrecognized backup format: {backup_path.name} "
            "(expected .dump or .tar.gz)"
        )

    # Fix permissions.
    print("Fixing permissions ...")
    for p in data_dir.rglob("*"):
        try:
            p.chmod(0o644 if p.is_file() else 0o755)
        except OSError:
            pass

    # Restart.
    print(f"Starting {cfg.container_name} ...")
    _docker("start", cfg.container_name)

    print(f"\n=== Restore complete at {datetime.now().isoformat()} ===")
    print("Neo4j is starting - wait ~10s for it to become ready.")
    return backup_path


def list_backups(cfg: Neo4jContainerConfig) -> list[dict]:
    """List available backup files with metadata.

    Args:
        cfg: Resolved container configuration.

    Returns:
        A list of dicts, each with keys:
        ``name``, ``path``, ``size_bytes``, ``size_human``, ``mode``
        ("dump" or "tar"), and ``mtime`` (ISO timestamp).
        Sorted newest-first.
    """
    from datetime import datetime

    bdir = cfg.neo4j_dir / BACKUP_SUBDIR
    if not bdir.exists():
        return []

    result: list[dict] = []
    for p in bdir.iterdir():
        if not p.is_file():
            continue
        if p.name.endswith(".dump"):
            mode = "dump"
        elif p.name.endswith(".tar.gz"):
            mode = "tar"
        else:
            continue
        stat = p.stat()
        size = stat.st_size
        if size > 1024 * 1024:
            size_human = f"{size / 1024 / 1024:.1f} MB"
        elif size > 1024:
            size_human = f"{size / 1024:.1f} KB"
        else:
            size_human = f"{size} B"
        result.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": size,
            "size_human": size_human,
            "mode": mode,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    result.sort(key=lambda x: x["mtime"], reverse=True)
    return result
