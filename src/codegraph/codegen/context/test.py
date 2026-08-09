"""Declared skip — test scaffolding renders no C++ in Phase 1.

``TestNode`` / ``TestStepNode`` / ``AssertionNode`` / ``TestFixtureNode``
are verification scaffolding.  Phase 3 exports them as Catch2/GTest
(``test.j2``); until then the skip is declared, not accidental.
"""

from __future__ import annotations

from codegraph.codegen.context.base import skip_builder

NODE_TYPES = ("TestNode", "TestStepNode", "AssertionNode", "TestFixtureNode")

SKIP_REASONS = {
    "TestNode": "test scaffolding — Phase 3 Catch2/GTest export",
    "TestStepNode": "test scaffolding — Phase 3 Catch2/GTest export",
    "AssertionNode": "test scaffolding — Phase 3 Catch2/GTest export",
    "TestFixtureNode": "test scaffolding — Phase 3 Catch2/GTest export",
}

build_context = skip_builder("test scaffolding — Phase 3 Catch2/GTest export")
