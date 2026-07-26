"""Unit test configuration — no database backend required.

Sets ``CODEGRAPH_TEST_SKIP_CONTAINER=1`` at session scope so the
Neo4j Docker container and neomodel label installation are skipped.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _skip_neo4j_container():
    """Prevent the backend conftest from starting a Neo4j container."""
    os.environ["CODEGRAPH_TEST_SKIP_CONTAINER"] = "1"
    yield
