"""Declared skip — requirements scaffolding renders no C++.

HLR / LLR nodes drive the file plan and doc comments only (spec D11):
they live inside design LayerGraphs but are not emitted as C++.  The
skip is declared, not accidental — the completeness gate sees an
explicit decision.
"""

from __future__ import annotations

from codegraph.codegen.context.base import skip_builder

NODE_TYPES = ("HLR", "LLR")

SKIP_REASONS = {
    "HLR": "requirements scaffolding — drives file plan / doc comments only (D11)",
    "LLR": "requirements scaffolding — drives file plan / doc comments only (D11)",
}

build_context = skip_builder("requirements scaffolding — not emitted as C++ (D11)")
