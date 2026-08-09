#!/usr/bin/env python3
"""Sync the codegen golden design fixture between repos (R1).

The canonical design LayerGraph lives in the sister repo
``doxygen-dependency-parser/tests/data/design_layergraph.json``.  The
codegraph repo keeps a reviewed golden at
``tests/codegen/golden/design_layergraph.json`` plus the fresh
generator output at ``tests/pipelines/unit_test_data/design_layergraph.json``
(written by ``tests/pipelines/test_design_migration_manager.py``).

Actions
-------
push   generated pipeline copy → sister repo  → golden (refresh all)
pull   sister repo → golden (sister regenerated; pull the new canonical)
check  byte-compare all three; fail on drift

Usage::

    python scripts/sync_codegen_fixtures.py check
    python scripts/sync_codegen_fixtures.py push
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SISTER = ROOT.parent / "doxygen-dependency-parser"

PIPELINE_COPY = ROOT / "tests/pipelines/unit_test_data/design_layergraph.json"
GOLDEN = ROOT / "tests/codegen/golden/design_layergraph.json"
SISTER_CANONICAL = SISTER / "tests/data/design_layergraph.json"


def _sha(path: Path) -> str:
    if not path.exists():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _same(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()


def check() -> int:
    failures = 0
    print(f"pipeline copy : {PIPELINE_COPY} {_sha(PIPELINE_COPY)}")
    print(f"golden        : {GOLDEN} {_sha(GOLDEN)}")
    print(f"sister repo   : {SISTER_CANONICAL} {_sha(SISTER_CANONICAL)}")
    if SISTER.exists():
        if not _same(PIPELINE_COPY, SISTER_CANONICAL):
            print("DRIFT: pipeline copy != sister repo (generator output not pushed)")
            failures += 1
        if not _same(GOLDEN, SISTER_CANONICAL):
            print("DRIFT: golden != sister repo (run pull)")
            failures += 1
    else:
        print(f"note: sister repo not at {SISTER} — skipping cross-repo checks")
    if not GOLDEN.exists():
        print("DRIFT: golden missing")
        failures += 1
    print("OK" if not failures else f"{failures} drift(s)")
    return 1 if failures else 0


def push() -> int:
    if not PIPELINE_COPY.exists():
        print(f"generator output not found: {PIPELINE_COPY}")
        print("run tests/pipelines/test_design_migration_manager.py first")
        return 1
    if SISTER.exists():
        shutil.copy2(PIPELINE_COPY, SISTER_CANONICAL)
        print(f"pushed → {SISTER_CANONICAL}")
    else:
        print(f"note: sister repo not at {SISTER} — skipped cross-repo copy")
    shutil.copy2(PIPELINE_COPY, GOLDEN)
    print(f"pushed → {GOLDEN}")
    return check()


def pull() -> int:
    """Adopt the sister repo as canonical: copy it over the golden."""
    if not SISTER_CANONICAL.exists():
        print(f"sister repo canonical not found: {SISTER_CANONICAL}")
        return 1
    shutil.copy2(SISTER_CANONICAL, GOLDEN)
    print(f"pulled → {GOLDEN}")
    if not _same(PIPELINE_COPY, SISTER_CANONICAL):
        print(
            "note: pipeline generator output differs from the adopted "
            "canonical — run push after the next generator run"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the requested sync action."""
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 1 or argv[0] not in ("push", "pull", "check"):
        print(__doc__)
        return 2
    return {"push": push, "pull": pull, "check": check}[argv[0]]()


if __name__ == "__main__":
    sys.exit(main())
