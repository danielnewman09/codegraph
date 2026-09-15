"""Canonical generated-artifact locations for Python integration tests."""

from __future__ import annotations

import os
from pathlib import Path


CODEGRAPH_ROOT = Path(
    os.environ.get("CODEGRAPH_ROOT", Path(__file__).resolve().parents[4])
)
ARTIFACT_ROOT = CODEGRAPH_ROOT / "tests"
UNIT_TEST_DATA = ARTIFACT_ROOT / "unit_test_data"
CODEGRAPH_OUTPUT = ARTIFACT_ROOT / "codegraph_output"
