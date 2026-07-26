"""Integration test configuration.

Integration tests require a running backend (Neo4j by default).  Neo4j
fixtures are loaded globally from the root conftest.

All tests under this directory must go through the Backend ABC or
``GraphRepository`` — direct neomodel ``.all()`` calls on relationship
managers are deprecated.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _configure_backend():
    """Ensure the active backend is initialized before each test."""
    from codegraph.backends import get_backend

    get_backend()
    yield
