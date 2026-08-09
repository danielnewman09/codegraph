"""Snapshot tests — rendered .hpp output pinned byte-for-byte.

Goldens live in ``tests/codegen/golden/cpp/`` (committed text).  Regenerate
with ``CODEGEN_ACCEPT=1 pytest tests/codegen/test_snapshots.py`` — the
test rewrites the golden files from the current renderer, so the diff
is reviewer-visible (full-file regeneration, spec resolved decision).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codegraph.codegen import generate

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

SNAPSHOTS = {
    "cpp/Migration.hpp": "design_layergraph_full_decl.json",
    "cpp/MigrationManager.hpp": "design_layergraph_full_decl.json",
    "cpp/MigrationErrorCode.hpp": "design_layergraph_full_decl.json",
    "cpp/CopyableTransferObject.hpp": "design_layergraph.json",
}


def _render_snapshot(rel: str) -> str:
    """Render the file for one snapshot from its owning fixture.

    Renders a single fixture and picks the one file — never merges
    multiple fixtures into one dict (overlapping rel paths between
    goldens would silently overwrite, and set iteration order is
    hash-randomized).
    """
    fixture = SNAPSHOTS[rel]
    data = json.loads((GOLDEN_DIR / fixture).read_text())
    result = generate(data)
    filename = rel.rsplit("/", 1)[-1]
    return result.files["include/cpp_sqlite/" + filename]


@pytest.mark.parametrize("rel", sorted(SNAPSHOTS))
def test_snapshot_matches_golden(rel: str):
    golden_path = GOLDEN_DIR / rel
    actual = _render_snapshot(rel)
    if os.environ.get("CODEGEN_ACCEPT") == "1":
        golden_path.write_text(actual, encoding="utf-8")
        return
    assert golden_path.exists(), (
        f"missing golden {golden_path} — run with CODEGEN_ACCEPT=1 to create it"
    )
    assert actual == golden_path.read_text(encoding="utf-8"), (
        f"render drift for {rel} — inspect the diff, then regenerate with "
        "CODEGEN_ACCEPT=1"
    )


def test_full_decl_tree_is_byte_stable():
    """Whole-tree determinism: rendering twice gives identical bytes."""
    data = json.loads((GOLDEN_DIR / "design_layergraph_full_decl.json").read_text())
    a = generate(data)
    b = generate(data)
    assert a.files == b.files
