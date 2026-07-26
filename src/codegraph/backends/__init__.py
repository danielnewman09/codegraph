"""Backend registry — configure and access the active storage backend.

Usage::

    from codegraph.backends import get_backend

    # First call auto-configures from CODEGRAPH_BACKEND env var
    # (default: "neo4j").  No explicit set_backend() needed.
    backend = get_backend()
    node.save()  # delegates to backend.save(node)

For tests, call ``set_backend()`` before any ``get_backend()`` calls
to use a specific backend instance (e.g. with test credentials):

    from codegraph.backends import set_backend
    from codegraph.backends.neo4j import Neo4jBackend

    set_backend(Neo4jBackend(config=test_config))
"""

from __future__ import annotations

import logging
import os

from codegraph.backends.interface import Backend

log = logging.getLogger(__name__)

_current_backend: Backend | None = None
_force_configured: bool = False


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

    On the first call, reads the ``CODEGRAPH_BACKEND`` environment
    variable (default ``"neo4j"``) and creates the corresponding
    backend.  Subsequent calls return the same instance.

    Raises:
        ValueError: If ``CODEGRAPH_BACKEND`` names an unknown backend.
    """
    global _current_backend, _force_configured

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
    backend_name = os.environ.get("CODEGRAPH_BACKEND", "neo4j").strip().lower()

    if backend_name == "neo4j":
        from codegraph.backends.neo4j import Neo4jBackend, Neo4jConfig

        config = Neo4jConfig.from_env()
        return Neo4jBackend(config)

    if backend_name == "memory":
        from codegraph.backends.memory import InMemoryBackend

        return InMemoryBackend()

    raise ValueError(
        f"Unknown CODEGRAPH_BACKEND: '{backend_name}'. "
        f"Supported values: neo4j, memory"
    )
