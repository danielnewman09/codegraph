"""Canonical generated-artifact locations for cpp-sqlite integration tests."""

from __future__ import annotations

import os
from pathlib import Path


CODEGRAPH_ROOT = Path(os.environ.get("CODEGRAPH_ROOT", Path(__file__).resolve().parents[4]))
ARTIFACT_ROOT = CODEGRAPH_ROOT / "tests"
UNIT_TEST_DATA = ARTIFACT_ROOT / "unit_test_data"
CODEGRAPH_OUTPUT = ARTIFACT_ROOT / "codegraph_output"
CPP_SQLITE_ROOT = Path(
    os.environ.get("CPP_SQLITE_ROOT", CODEGRAPH_ROOT.parent / "cpp-sqlite")
)
CONAN_GENERATORS_DIR = CPP_SQLITE_ROOT / "build" / "Debug" / "generators"
