"""Backend registry tests — set_backend / get_backend / env selection.

These are backend-free: they only exercise the registry's selection
logic (InMemoryBackend needs no database; SqliteBackend with
``SQLITE_PATH=:memory:`` never touches disk).
"""

from __future__ import annotations

import pytest

import codegraph.backends as backends_mod
from codegraph.backends import get_backend, set_backend
from codegraph.backends.interface import Backend
from codegraph.backends.memory import InMemoryBackend


@pytest.fixture(autouse=True)
def clear_db():
    """Override the backend plugin's ``clear_db`` — no-op.

    Registry tests manage backend state themselves via
    ``_clean_registry``; the plugin's function-scoped wipe would
    otherwise call ``get_backend()`` mid-teardown while the globals are
    in a transitional state.
    """
    yield


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Reset the registry globals around each test and stub .env loading.

    ``_load_dotenv_called=True`` keeps tests independent of any repo
    ``.env`` file; backend selection is driven purely by monkeypatched
    env vars.
    """
    before = (
        backends_mod._current_backend,
        backends_mod._force_configured,
        backends_mod._load_dotenv_called,
    )
    backends_mod._current_backend = None
    backends_mod._force_configured = False
    backends_mod._load_dotenv_called = True
    try:
        yield
    finally:
        # Restore the pre-test registry state (which may include the
        # session-scoped backend from the backend plugin's conftest) so
        # later tests don't inherit a clobbered global.
        backends_mod._current_backend, backends_mod._force_configured, backends_mod._load_dotenv_called = before


def test_set_backend_returns_same_instance():
    instance = InMemoryBackend()
    set_backend(instance)
    assert get_backend() is instance
    assert get_backend() is instance  # subsequent calls return the same


def test_set_backend_disables_env_autoconfig(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_BACKEND", "sqlite")
    set_backend(InMemoryBackend())
    assert type(get_backend()).__name__ == "InMemoryBackend"


def test_env_selection_memory(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_BACKEND", "memory")
    assert type(get_backend()).__name__ == "InMemoryBackend"


def test_env_selection_sqlite(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", ":memory:")
    assert type(get_backend()).__name__ == "SqliteBackend"


def test_env_selection_neo4j(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_BACKEND", "neo4j")
    assert type(get_backend()).__name__ == "Neo4jBackend"


def test_env_selection_default_is_sqlite(monkeypatch):
    monkeypatch.delenv("CODEGRAPH_BACKEND", raising=False)
    monkeypatch.setenv("SQLITE_PATH", ":memory:")
    assert type(get_backend()).__name__ == "SqliteBackend"


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("CODEGRAPH_BACKEND", "bogus")
    with pytest.raises(ValueError, match="bogus"):
        get_backend()


def test_set_backend_missing_instance_raises():
    # Belt-and-suspenders: force-configured but no instance present.
    backends_mod._force_configured = True
    backends_mod._current_backend = None
    with pytest.raises(RuntimeError):
        get_backend()


def test_backends_implement_abc():
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

    assert isinstance(InMemoryBackend(), Backend)
    sqlite = SqliteBackend(SqliteConfig(path=":memory:"))
    assert isinstance(sqlite, Backend)
