"""Declared skip — ExecutionEvidenceNode renders no C++.

Execution evidence records that a build or test run *happened* (WP5.4);
it is durable overlay data captured by
``scripts/capture_transaction_slice_evidence.py``, never part of a C++
translation unit.  The skip is declared, not accidental: this module
exists so the completeness gate sees an explicit decision for the node
type, mirroring the ``LiteralNode`` / ``HLR`` / ``LLR`` skips.
"""

from __future__ import annotations

from codegraph.codegen.context.base import skip_builder

NODE_TYPES = ("ExecutionEvidenceNode",)

SKIP_REASONS = {
    "ExecutionEvidenceNode": (
        "execution-evidence record (evidence::…) — durable overlay data, "
        "not emitted as C++"
    ),
}

build_context = skip_builder(SKIP_REASONS["ExecutionEvidenceNode"])
