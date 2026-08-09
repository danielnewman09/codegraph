"""Declared skip — codegraph_project nodes render no C++.

``Component``, ``Dependency``, ``Language``, ``ProjectMeta`` are project
/ provenance metadata nodes (from ``codegraph_project``).  They are not
translation-unit content; ``Component`` may later drive file-plan
grouping, tracked for Phase 2.
"""

from __future__ import annotations

from codegraph.codegen.context.base import skip_builder

NODE_TYPES = ("Component", "Dependency", "Language", "ProjectMeta")

SKIP_REASONS = {
    "Component": "project metadata — may drive file-plan grouping in Phase 2",
    "Dependency": "project metadata — not emitted as C++",
    "Language": "project metadata — not emitted as C++",
    "ProjectMeta": "project metadata — not emitted as C++",
}

build_context = skip_builder("project metadata — not emitted as C++")
