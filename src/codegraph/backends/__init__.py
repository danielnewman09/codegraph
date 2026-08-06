"""Backend registry — configure and access the active storage backend.

Choosing a backend
------------------

Two mechanisms, used interchangeably (the most recent wins):

1. **Convention (env vars)** — the default path.  ``get_backend()``
   reads ``CODEGRAPH_BACKEND`` (``"sqlite"`` (default), ``"neo4j"``,
   ``"memory"``) plus the backend's own vars (``SQLITE_PATH`` or
   ``NEO4J_URI``/``NEO4J_USER``/``NEO4J_PASSWORD``).  A repo-root
   ``.env`` is loaded if present; explicitly-set shell/CI vars always
   win::

       CODEGRAPH_BACKEND=sqlite SQLITE_PATH=/tmp/cg.sqlite3 my_script.py

   or in ``.env``::

       CODEGRAPH_BACKEND=sqlite

2. **Programmatic (set_backend)** — for library consumers that have
   their own configuration (tests, embedding into another app):
   construct the backend explicitly and register it *before* the first
   ``get_backend()`` call::

       from codegraph.backends import set_backend, get_backend
       from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

       set_backend(SqliteBackend(SqliteConfig(path="/data/cg.sqlite3")))
       node = get_backend().graph.find_by_uid(...)

   This disables env-based auto-configuration for the rest of the
   process.

The backend is a process-global singleton: call ``get_backend()``
freely, it returns the same instance.  To swap backends mid-process
(e.g. between test suites) call ``set_backend()`` again with a new
instance.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from codegraph.backends.interface import Backend

log = logging.getLogger(__name__)

_current_backend: Backend | None = None
_force_configured: bool = False
_load_dotenv_called: bool = False


def set_backend(backend: Backend) -> None:
    """Force a specific backend.  Call before any ``get_backend()``.

    Once this is called, auto-configuration is disabled — subsequent
    ``get_backend()`` calls return the explicitly-set backend.

    Primarily used in tests to inject a backend with test credentials.
    """
    global _current_backend, _force_configured
    _current_backend = backend
    _force_configured = True


def get_backend() -> Backend:
    """Return the active backend, auto-configuring on first call.

    Loads a repo-root ``.env`` (if present; ``override=False`` so
    explicitly-set environment variables win), then reads the
    ``CODEGRAPH_BACKEND`` environment variable (default ``"sqlite"``)
    and creates the corresponding backend.  Subsequent calls return
    the same instance.  A backend set via :func:`set_backend` always
    wins over env-based auto-configuration.

    Raises:
        ValueError: If ``CODEGRAPH_BACKEND`` names an unknown backend.
    """
    global _current_backend, _force_configured, _load_dotenv_called

    if not _load_dotenv_called:
        # Load .env once, before reading CODEGRAPH_BACKEND.  Explicitly
        # set environment variables (shell / CI / set_backend) are not
        # overridden by the file (load_dotenv defaults to
        # override=False).
        load_dotenv()
        _load_dotenv_called = True

    if _current_backend is not None:
        return _current_backend

    if _force_configured:
        # set_backend() was called but somehow _current_backend is
        # None — should not happen, but belt-and-suspenders.
        raise RuntimeError(
            "Backend was force-configured but the instance is missing."
        )

    _current_backend = _create_backend_from_env()
    return _current_backend


def _create_backend_from_env() -> Backend:
    """Read CODEGRAPH_BACKEND env var and instantiate the backend."""
    backend_name = os.environ.get("CODEGRAPH_BACKEND", "sqlite").strip().lower()

    if backend_name == "neo4j":
        from codegraph.backends.neo4j import Neo4jBackend, Neo4jConfig

        config = Neo4jConfig.from_env()
        return Neo4jBackend(config)

    if backend_name == "memory":
        from codegraph.backends.memory import InMemoryBackend

        return InMemoryBackend()

    if backend_name == "sqlite":
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

        config = SqliteConfig.from_env()
        return SqliteBackend(config)

    raise ValueError(
        f"Unknown CODEGRAPH_BACKEND: '{backend_name}'. "
        f"Supported values: neo4j, memory, sqlite"
    )
