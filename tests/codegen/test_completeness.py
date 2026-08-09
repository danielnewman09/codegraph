"""Completeness gate — every codegraph node type has a codegen decision.

Iterates ``CodeGraphNode._registry`` (all registered model types,
including the lazily-registered requirements/project types) and asserts:

1. every type has a declared context builder (or a declared skip) in
   ``codegen.context.BUILDERS`` — adding a model type forces an explicit
   codegen decision;
2. every declared builder ``NODE_TYPES`` name is a real registered type;
3. builder coverage is disjoint and total across builder modules;
4. the cpp template pack mirrors the registry: every non-skipped type
   has a ``templates/cpp/<NodeType>/`` directory with at least one
   template; declared skips are covered by ``_skipped.j2``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import codegraph.models  # noqa: F401 — registers core model types
import codegraph_project.models.component  # noqa: F401 — registers project types
import codegraph_requirements.models.requirement  # noqa: F401 — registers HLR/LLR
from codegraph.codegen.context import (
    BUILDERS,
    SKIP_REASONS,
    base,
    compound,
    file,
    implementation,
    literal,
    member,
    namespace,
    parameter,
    project,
    requirements,
    test,
)
from codegraph.codegen.pack import PACK_SKIPPED, builtin_pack_dir
from codegraph.models.tags import CodeGraphNode

BUILDER_MODULES = (
    compound, member, file, namespace, parameter, implementation,
    literal, test, requirements, project,
)


def _all_registered_types() -> set[str]:
    """Registered node types from the model packages codegen mirrors.

    The gate covers ``codegraph.models.*`` (core node models),
    ``codegraph_project.models.*`` (project/dependency/language) and
    ``codegraph_requirements.models.*`` (HLR/LLR) — the packages the
    builder modules mirror.  Test fixtures (``TestClassNode`` etc.) and
    sibling subsystems that subclass ``CodeGraphNode`` but are not
    codegen inputs (``codegraph_memory.*`` registers MemoryNode,
    DecisionNode, …) pollute the global registry at collection time and
    are excluded.
    """
    allowed_prefixes = (
        "codegraph.models",
        "codegraph_project.models",
        "codegraph_requirements.models",
    )
    return {
        name
        for name, cls in CodeGraphNode._registry.items()
        if cls.__module__.startswith(allowed_prefixes)
    }


def test_every_registered_type_has_a_builder_or_declared_skip():
    missing = _all_registered_types() - set(BUILDERS)
    assert not missing, (
        f"node type(s) without a codegen builder: {sorted(missing)}. "
        "Declare a builder (or a skip) in codegen/context/."
    )


def test_no_stray_builders():
    stray = set(BUILDERS) - _all_registered_types()
    assert not stray, f"BUILDERS keys that are not registered types: {sorted(stray)}"


def test_builder_node_types_are_registered_types():
    for module in BUILDER_MODULES:
        unknown = set(module.NODE_TYPES) - _all_registered_types()
        assert not unknown, (
            f"{module.__name__}.NODE_TYPES references unregistered types: "
            f"{sorted(unknown)}"
        )


def test_builder_coverage_is_disjoint_and_total():
    seen: dict[str, str] = {}
    for module in BUILDER_MODULES:
        for node_type in module.NODE_TYPES:
            assert node_type not in seen, (
                f"{node_type} declared in both {seen[node_type]} and {module.__name__}"
            )
            seen[node_type] = module.__name__
    assert set(seen) == _all_registered_types(), (
        f"builder coverage != registry: "
        f"missing={sorted(_all_registered_types() - set(seen))}, "
        f"extra={sorted(set(seen) - _all_registered_types())}"
    )


def test_skip_builders_are_explicit():
    """Every declared skip has a reason; every reason maps to a builder."""
    assert set(SKIP_REASONS) <= set(BUILDERS)
    # Skip modules must expose a skip-reasoned builder (not a real one).
    for node_type in SKIP_REASONS:
        builder = BUILDERS[node_type]
        assert getattr(builder, "skip_reason", None), (
            f"{node_type} listed in SKIP_REASONS but its builder is not a "
            "skip_builder()"
        )


def test_every_skip_builder_returns_none():
    from codegraph.graph import LayerGraph

    for node_type, builder in BUILDERS.items():
        if node_type not in SKIP_REASONS:
            continue
        # A skip must produce no context regardless of input.
        assert builder(None, None) is None  # type: ignore[arg-type]


# ── Template pack completeness (R2: templates mirror models/) ───────────────

def _template_dirs() -> dict[str, Path]:
    pack_root = builtin_pack_dir("cpp")
    return {d.name: d for d in pack_root.iterdir() if d.is_dir()}


def test_pack_mirrors_registry():
    dirs = _template_dirs()
    registry = _all_registered_types()
    for node_type in registry:
        if node_type in PACK_SKIPPED:
            continue
        if node_type == "FileNode":
            # FileNode's templates are the pack-root document
            # orchestrators (spec mapping table; template_contract.md).
            assert (builtin_pack_dir("cpp") / "file_header.j2").exists()
            assert (builtin_pack_dir("cpp") / "file_source.j2").exists()
            continue
        assert node_type in dirs, (
            f"no template directory for {node_type} in the cpp pack. "
            "Create templates/cpp/<NodeType>/ with at least one .j2 "
            "(or add to PACK_SKIPPED with a reason)."
        )
        templates = [f for f in dirs[node_type].iterdir() if f.suffix == ".j2"]
        assert templates, f"templates/cpp/{node_type}/ has no .j2 templates"


def test_pack_skipped_has_marker():
    pack_root = builtin_pack_dir("cpp")
    assert (pack_root / "_skipped.j2").exists(), (
        "pack-level _skipped.j2 must exist for declared skips"
    )


def test_pack_skipped_covers_all_skip_builders():
    skip_types = set(SKIP_REASONS)
    assert skip_types <= PACK_SKIPPED, (
        f"declared-skip types missing from PACK_SKIPPED: "
        f"{sorted(skip_types - PACK_SKIPPED)}"
    )


def test_pack_dirs_have_no_unknown_types():
    dirs = _template_dirs()
    registry = _all_registered_types()
    unknown = set(dirs) - registry
    assert not unknown, (
        f"template directories with no registered node type: {sorted(unknown)}"
    )


def test_pack_layout_documentation_exists():
    pack_root = builtin_pack_dir("cpp")
    assert (pack_root / "template_contract.md").exists()
    assert (pack_root / "defaults.toml").exists()


def test_file_node_orchestrators_at_pack_root():
    """FileNode's templates are the pack-root document orchestrators, not a
    FileNode/ subdirectory (spec: file_header.j2 / file_source.j2)."""
    pack_root = builtin_pack_dir("cpp")
    assert (pack_root / "file_header.j2").exists()
    assert (pack_root / "file_source.j2").exists()
    assert not (pack_root / "FileNode").exists()
