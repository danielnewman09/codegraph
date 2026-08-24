"""Unit tests for reproducible external-tool failure classification."""

from __future__ import annotations

import pytest

from tests.codegen.external_tools import classify_failure


@pytest.mark.parametrize(
    ("output", "category"),
    [
        ("conan: Recipe 'zlib/1.3.1' not found in local cache", "missing_recipe"),
        ("Version range could not be resolved; no remote defined", "missing_recipe"),
        ("Unable to connect to remote: Name or service not known", "network"),
        ("sqlite3.OperationalError: attempt to write a readonly database", "environment"),
        ("doxygen-index generated invalid graph relationships", "semantic"),
    ],
)
def test_external_failure_categories(output: str, category: str) -> None:
    assert classify_failure(output) == category
