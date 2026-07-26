"""Integration test configuration.

Integration tests require a running backend (Neo4j by default).  Neo4j
fixtures are loaded globally from the root conftest.

All tests under this directory must go through the Backend ABC or
``GraphRepository`` — direct neomodel ``.all()`` calls on relationship
managers are deprecated.

The ``INTEGRATION_DATA_DIR`` constant points to ``tests/integration/data/``
so tests can reference fixture files without fragile relative paths::

    from tests.integration.conftest import INTEGRATION_DATA_DIR
    fixture = INTEGRATION_DATA_DIR / "design_graph.json"
"""

from __future__ import annotations

from pathlib import Path

import pytest

INTEGRATION_DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Return the integration test data directory."""
    return INTEGRATION_DATA_DIR


@pytest.fixture(autouse=True)
def _configure_backend():
    """Ensure the active backend is initialized before each test."""
    from codegraph.backends import get_backend

    get_backend()
    yield
