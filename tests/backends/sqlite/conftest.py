"""Pytest fixtures for SQLite backend tests.

No Docker, no Neo4j — each test runs against an in-memory SQLite
database via ``SqliteBackend``.  ``CODEGRAPH_TEST_SKIP_CONTAINER=1``
disables the Neo4j container fixtures from the global plugin so the
sqlite backend is used everywhere.

Lifecycle:
1. ``sqlite_backend`` (session) — builds an in-memory backend and calls
   ``set_backend()``.
2. ``clear_db`` (autouse, function) — deletes all rows from ``nodes``
   before each test; FK cascades clear edges/labels/tags/embeddings and
   the FTS shadow table is cleared explicitly.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def setup_neomodel():
    """Stand-in for the Neo4j plugin's ``setup_neomodel`` fixture.

    Integration suites request this fixture by name; under the sqlite
    plugin it is a no-op (the backend was already set by
    ``sqlite_backend_override``).
    """
    yield None


@pytest.fixture(scope="session")
def test_neo4j_container():
    """Override the global Neo4j container fixture — never touch Docker.

    The root ``tests.conftest`` registers ``tests.backends.neo4j.conftest``
    as a plugin; a fixture with the same name in a closer conftest wins.
    With this in place, ``setup_neomodel`` finds Bolt unreachable and
    yields without touching the backend.
    """
    yield


@pytest.fixture(scope="session", autouse=True)
def sqlite_backend_override():
    """Replace the global backend with an in-memory SQLite backend.

    Runs only when ``CODEGRAPH_BACKEND=sqlite``.  The Neo4j plugin
    fixtures become no-ops via the ``test_neo4j_container`` override
    above (and ``CODEGRAPH_TEST_SKIP_CONTAINER=1`` for safety).
    """
    os.environ.setdefault("CODEGRAPH_TEST_SKIP_CONTAINER", "1")
    if os.environ.get("CODEGRAPH_BACKEND", "neo4j").lower() != "sqlite":
        return

    from codegraph.backends import set_backend
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

    backend = SqliteBackend(SqliteConfig(path=":memory:"))
    backend.initialize(SqliteConfig(path=":memory:"))
    set_backend(backend)
    yield backend


@pytest.fixture(autouse=True)
def clear_db():
    """Clear the SQLite database before each test."""
    yield
    from codegraph.backends import get_backend

    backend = get_backend()
    if type(backend).__name__ == "SqliteBackend":
        import sqlalchemy as sa

        with backend._conn.engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM fts_nodes"))
            conn.execute(sa.text("DELETE FROM nodes"))


@pytest.fixture(autouse=True)
def canonical_identity_scope():
    """Wrap every sqlite-backend test in a canonical identity scope
    (WP A/D — canonical identity is mandatory; backend tests save code
    nodes that need a repository scope)."""
    from codegraph.identity import IdentityScope, identity_scope

    with identity_scope(
        IdentityScope.repository("codegraph-suite", "codegraph")
    ):
        yield
