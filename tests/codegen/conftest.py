"""Codegen test configuration — no database backend required.

Mirrors ``tests/unit/conftest.py``: codegen unit tests exercise the
model surface + layer graph JSON directly (D2 — a pack can be tested
against raw graph JSON without a database).
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _skip_neo4j_container():
    """Prevent the backend conftest from starting a Neo4j container."""
    os.environ["CODEGRAPH_TEST_SKIP_CONTAINER"] = "1"
    yield
