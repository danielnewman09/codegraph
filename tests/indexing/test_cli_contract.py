from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).with_name("data") / "cli_help.normalized.txt"


def _help() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "codegraph_index.cli", "--help"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.replace("usage: doxygen-index", "usage: <index-cli>", 1).strip()


def test_codegraph_cli_matches_normalized_help_contract() -> None:
    expected = GOLDEN.read_text().strip()
    assert _help() == expected
