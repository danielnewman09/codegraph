"""Declared skip — LiteralNode renders no C++.

LiteralNodes are verification-scaffolding values (``literal::30`` etc.),
never part of a C++ translation unit.  The skip is declared, not
accidental: this module exists so the completeness gate sees an explicit
decision for the node type.
"""

from __future__ import annotations

from codegraph.codegen.context.base import skip_builder

NODE_TYPES = ("LiteralNode",)

SKIP_REASONS = {
    "LiteralNode": "verification-scaffolding value (literal::…) — not emitted as C++",
}

build_context = skip_builder(SKIP_REASONS["LiteralNode"])
