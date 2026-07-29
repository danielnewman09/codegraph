"""Pytest fixtures for Neo4j integration tests.

Session lifecycle
-----------------
1. ``test_neo4j_container`` — starts a dedicated ``neo4j-codegraph-test``
   Docker container on port 7688 via ``docker compose``, waits for it
   to be healthy, and tears it down after the session.

2. ``setup_neomodel`` — connects to the test container, drops stale
   constraints/indexes, installs fresh labels, wipes once, and
   calls ``set_backend(Neo4jBackend())``.

3. ``clear_db`` — wipes the database after every test function.

Design notes
------------
Credentials are baked into ``tests/docker-compose.yml``.  The root
``tests/.env`` file is kept for documentation / human reference but
is **not** loaded — this avoids conflicts with VS Code's
``python.envFile`` pre-loading the project ``.env``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_COMPOSE_FILE = _HERE.parent.parent / "docker-compose.yml"

# Mirror the credentials baked into tests/docker-compose.yml.
_TEST_BOLT_PORT = 7688
_TEST_USER = "neo4j"
_TEST_PASSWORD = "codegraph-test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run ``docker compose -f <compose_file> ...``."""
    cmd = ["docker", "compose", "-f", str(_COMPOSE_FILE), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _bolt_reachable(uri: str, user: str, password: str, timeout: int = 60) -> bool:
    """Poll until Neo4j at *uri* accepts a real Bolt handshake."""
    from neo4j import GraphDatabase

    deadline = time.monotonic() + timeout
    last_err: Exception | None = None

    while time.monotonic() < deadline:
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            driver.close()
            return True
        except Exception as exc:
            last_err = exc
            time.sleep(2)

    if last_err:
        print(f"  Bolt connectivity check failed: {last_err}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_neo4j_container():
    """Start a dedicated Neo4j Docker container for the test session."""
    if os.environ.get("CODEGRAPH_TEST_SKIP_CONTAINER", "").lower() in ("1", "true", "yes"):
        yield
        return

    if not _COMPOSE_FILE.exists():
        pytest.fail(
            f"docker-compose.yml not found at {_COMPOSE_FILE} — "
            "cannot start test Neo4j container."
        )

    if not _docker_available():
        pytest.skip(
            "Docker daemon is not reachable.  "
            "Set CODEGRAPH_TEST_SKIP_CONTAINER=1 and provide your own "
            "Neo4j instance to run integration tests."
        )

    print("\n  Starting test Neo4j container ...")
    try:
        _compose("up", "--detach", "--wait")
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        pytest.fail(f"Failed to start test Neo4j container:\n{exc.stderr}")

    bolt_uri = f"bolt://localhost:{_TEST_BOLT_PORT}"
    if not _bolt_reachable(bolt_uri, _TEST_USER, _TEST_PASSWORD):
        _compose("down", "--volumes", check=False)
        pytest.fail("Test Neo4j container started but Bolt is not reachable.")

    print("  Test Neo4j container is ready.\n")

    yield

    print("\n  Tearing down test Neo4j container ...")
    _compose("down", "--volumes", check=False)
    print("  Done.\n")


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel(test_neo4j_container):
    """Configure neomodel, install labels, wipe once, set backend."""
    from neomodel import db, get_config

    uri = f"bolt://localhost:{_TEST_BOLT_PORT}"
    user = _TEST_USER
    password = _TEST_PASSWORD

    host = uri.replace("bolt://", "")
    config = get_config()
    config.database_url = f"bolt://{user}:{password}@{host}"

    if not _bolt_reachable(uri, user, password, timeout=3):
        import logging
        logging.getLogger(__name__).warning(
            "Neo4j not reachable at %s — skipping DB setup.",
            uri,
        )
        yield
        return

    # Drop stale constraints/indexes from previous sessions
    try:
        results, _ = db.cypher_query(
            "SHOW CONSTRAINTS YIELD name RETURN name"
        )
        for r in results:
            db.cypher_query(f"DROP CONSTRAINT {r[0]} IF EXISTS")
        results, _ = db.cypher_query(
            'SHOW INDEXES YIELD name, type WHERE type <> "LOOKUP" RETURN name'
        )
        for r in results:
            db.cypher_query(f"DROP INDEX {r[0]} IF EXISTS")
    except Exception:
        pass

    db.install_all_labels()

    from codegraph.backends import set_backend
    from codegraph.backends.neo4j import Neo4jBackend, Neo4jConfig

    backend_config = Neo4jConfig(
        uri=uri,
        user=user,
        password=password,
    )
    set_backend(Neo4jBackend(backend_config))

    # Wipe through the backend API (not raw Cypher)
    from codegraph.backends import get_backend
    get_backend().wipe()

    yield


@pytest.fixture(autouse=True)
def clear_db():
    """Clear the Neo4j database before each test."""
    yield
    try:
        from codegraph.backends import get_backend
        get_backend().wipe()
    except Exception:
        pass
