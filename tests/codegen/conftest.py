"""Codegen test configuration — no database backend required.

Mirrors ``tests/unit/conftest.py``: codegen unit tests exercise the
model surface + layer graph JSON directly (D2 — a pack can be tested
against raw graph JSON without a database).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.codegen.external_tools import (
    ConanTestEnvironment,
    prepare_conan_environment,
)


@pytest.fixture(scope="session", autouse=True)
def _skip_neo4j_container():
    """Prevent the backend conftest from starting a Neo4j container."""
    os.environ["CODEGRAPH_TEST_SKIP_CONTAINER"] = "1"
    yield


@pytest.fixture(scope="session")
def conan_test_environment(tmp_path_factory) -> ConanTestEnvironment:
    """Provide disposable Conan 2 state for the C++ integration suites."""
    return prepare_conan_environment(
        Path(tmp_path_factory.mktemp("conan-environment")),
        project_dir=(
            Path(__file__).resolve().parent.parent
            / "unit_test_data/cpp_sqlite_impl_src/tests/fixtures/cpp-sqlite"
        ),
    )
