"""Behavioral checks for DDP-origin coverage that was formerly import-only."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path


def _module(name: str):
    package = "doxygen_index" if os.environ.get("DDP_PARITY_IMPLEMENTATION") == "baseline" else "codegraph_index"
    return importlib.import_module(f"{package}.{name}")


def test_json_backend_writes_a_complete_empty_parse_result(tmp_path: Path) -> None:
    """Exercise the historical JSON backend as an output contract."""
    model = _module("parser.model")
    backend = _module("json_backend")
    output = tmp_path / "nested" / "result.json"

    backend.write_result(model.ParseResult(), output, source="parity")

    payload = json.loads(output.read_text())
    assert payload["metadata"]["source"] == "parity"
    assert payload["metadata"]["format_version"] == 1
    assert payload["files"] == []
    assert payload["tests"] == []


def test_test_comment_writer_is_idempotent_after_reparse(tmp_path: Path) -> None:
    """Exercise the unchanged-text branch after generated comments reparse."""
    parser = _module("parser")
    comments = _module("parser.python.test_comments")
    source = tmp_path / "test_example.py"
    source.write_text("def test_example():\n    assert True\n", encoding="utf-8")

    first = parser.parse_python_dir([tmp_path], source="parity", progress_interval=0)
    first.tests[0].description = "Verifies the example behavior."
    comments.write_test_comments(first)

    second = parser.parse_python_dir([tmp_path], source="parity", progress_interval=0)
    report = comments.write_test_comments(second)
    assert report.files_unchanged == [str(source)]


def test_test_comment_writer_preserves_no_terminal_newline_on_reparse(tmp_path: Path) -> None:
    """Exercise the no-terminal-newline side of the writer's branch."""
    parser = _module("parser")
    comments = _module("parser.python.test_comments")
    source = tmp_path / "test_no_newline.py"
    source.write_text("def test_no_newline():\n    assert True", encoding="utf-8")

    first = parser.parse_python_dir([tmp_path], source="parity", progress_interval=0)
    first.tests[0].description = "Verifies source without a terminal newline."
    comments.write_test_comments(first)

    second = parser.parse_python_dir([tmp_path], source="parity", progress_interval=0)
    report = comments.write_test_comments(second)
    assert report.files_unchanged == [str(source)]
