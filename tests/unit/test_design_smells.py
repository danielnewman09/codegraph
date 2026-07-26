"""Unit tests for design-smell checkers."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest

from codegraph.export.plantuml import PlantUMLExporter
from codegraph.graph import LayerGraph
from codegraph_design.tools.design_smells import (
    Severity,
    Smell,
    SmellReport,
    run_all_smells,
)

log = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent / "unit_test_data" / "smells"


def _dump(design: list[dict], stem: str) -> Path:
    """Write a design draft to a gitignored file for human review.

    Also exports a PlantUML ``.puml`` file and renders a ``.png``
    diagram so the design is visible at a glance.  Exports use
    ``LayerGraph._deserialize_nested`` and
    :class:`PlantUMLExporter` — failures are logged but do not
    fail the test.

    Returns the path to the JSON file so the caller can include
    it in assertion messages.
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{stem}.json"
    path.write_text(json.dumps(design, indent=2), encoding="utf-8")

    # ── PlantUML export ───────────────────────────────────────────
    puml_path = FIXTURES_DIR / f"{stem}.puml"
    try:
        graph = LayerGraph._deserialize_nested(design)
        exporter = PlantUMLExporter(graph)
        puml_text = exporter.export()
        puml_path.write_text(puml_text, encoding="utf-8")
    except Exception as exc:
        log.warning("PlantUML export failed for '%s': %s", stem, exc)
        return path

    # ── PNG render ────────────────────────────────────────────────
    png_path = FIXTURES_DIR / f"{stem}.png"
    try:
        subprocess.run(
            ["plantuml", "-tpng", str(puml_path.name)],
            cwd=str(FIXTURES_DIR.resolve()),
            capture_output=True,
            timeout=15,
            check=True,
        )
        if png_path.exists():
            log.info("Rendered %s (%d bytes)", stem, png_path.stat().st_size)
    except FileNotFoundError:
        log.info("plantuml CLI not installed — PNG render skipped")
    except subprocess.TimeoutExpired:
        log.warning("plantuml timed out for '%s'", stem)
    except subprocess.CalledProcessError as exc:
        log.warning("plantuml error for '%s': %s", stem, exc.stderr.decode()[:200] if exc.stderr else exc)

    return path


# ══════════════════════════════════════════════════════════════════════════
# orphaned_enum
# ══════════════════════════════════════════════════════════════════════════


def test_orphaned_enum_no_values() -> None:
    """An EnumNode with zero EnumValueNode children is a blocking smell."""
    design = [
        {
            "name": "app",
            "qualified_name": "app",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Status",
                    "qualified_name": "app::Status",
                    "type": "EnumNode",
                    "composes": [],
                },
            ],
        },
    ]
    path = _dump(design, "orphaned_enum_no_values")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smells\nDraft: {path}"
    assert report.summary["blocking"] == 1, (
        f"Expected exactly 1 blocking smell, got summary={report.summary}\n"
        f"Draft: {path}"
    )
    smell = report.smells[0]
    assert smell.id == "orphaned_enum", (
        f"Wrong smell id: {smell.id}\nDraft: {path}"
    )
    assert "app::Status" in smell.element


def test_orphaned_enum_with_values_is_clean() -> None:
    """An EnumNode with EnumValueNode children under a namespace is valid."""
    design = [
        {
            "name": "app",
            "qualified_name": "app",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Status",
                    "qualified_name": "app::Status",
                    "type": "EnumNode",
                    "composes": [
                        {"name": "ACTIVE", "qualified_name": "app::Status::ACTIVE", "type": "EnumValueNode"},
                        {"name": "INACTIVE", "qualified_name": "app::Status::INACTIVE", "type": "EnumValueNode"},
                    ],
                },
            ],
        },
    ]
    path = _dump(design, "orphaned_enum_with_values")

    report = run_all_smells(design)

    assert report.valid, (
        f"Expected no blocking smells, got: {report.smells}\nDraft: {path}"
    )
    assert report.summary["blocking"] == 0


def test_orphaned_enum_empty_composes_and_no_edges() -> None:
    """An enum with empty composes (intended to exist) under a namespace."""
    design = [
        {
            "name": "ui",
            "qualified_name": "ui",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Color",
                    "qualified_name": "ui::Color",
                    "type": "EnumNode",
                    "composes": [],  # explicitly empty — no values added
                    "edges": [],
                },
            ],
        },
    ]
    path = _dump(design, "orphaned_enum_empty_composes")

    report = run_all_smells(design)

    assert not report.valid, (
        f"Empty composes on an EnumNode should be flagged\nDraft: {path}"
    )
    assert any(s.id == "orphaned_enum" for s in report.smells), (
        f"Missing orphaned_enum smell in: {[s.id for s in report.smells]}\n"
        f"Draft: {path}"
    )


# ══════════════════════════════════════════════════════════════════════════
# orphaned_enumvalue
# ══════════════════════════════════════════════════════════════════════════


def test_orphaned_enumvalue_no_parent() -> None:
    """An EnumValueNode without a parent EnumNode is a blocking smell."""
    design = [
        {
            "name": "ORPHAN_VALUE",
            "qualified_name": "app::ORPHAN_VALUE",
            "type": "EnumValueNode",
        },
    ]
    path = _dump(design, "orphaned_enumvalue_no_parent")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smells\nDraft: {path}"
    smell = [s for s in report.smells if s.id == "orphaned_enumvalue"]
    assert smell, (
        f"No orphaned_enumvalue smell detected. Smells: {[s.id for s in report.smells]}\n"
        f"Draft: {path}"
    )
    assert "app::ORPHAN_VALUE" in smell[0].element


def test_orphaned_enumvalue_nested_is_clean() -> None:
    """An EnumValueNode nested under its parent EnumNode under a namespace is valid."""
    design = [
        {
            "name": "app",
            "qualified_name": "app",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Status",
                    "qualified_name": "app::Status",
                    "type": "EnumNode",
                    "composes": [
                        {
                            "name": "PENDING",
                            "qualified_name": "app::Status::PENDING",
                            "type": "EnumValueNode",
                        },
                    ],
                },
            ],
        },
    ]
    path = _dump(design, "orphaned_enumvalue_nested_clean")

    report = run_all_smells(design)

    assert report.valid, (
        f"Expected no blocking smells, got: {report.smells}\nDraft: {path}"
    )


def test_orphaned_enumvalue_multiple_siblings_one_orphan() -> None:
    """One of several EnumValueNodes is an orphan — only that one flagged."""
    design = [
        {
            "name": "Status",
            "qualified_name": "app::Status",
            "type": "EnumNode",
            "composes": [
                {"name": "ON", "qualified_name": "app::Status::ON", "type": "EnumValueNode"},
                {"name": "OFF", "qualified_name": "app::Status::OFF", "type": "EnumValueNode"},
            ],
        },
        {
            "name": "STRAY",
            "qualified_name": "app::STRAY",
            "type": "EnumValueNode",
        },
    ]
    path = _dump(design, "orphaned_enumvalue_one_orphan_among_siblings")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smell for stray EnumValue\nDraft: {path}"
    orphan_smells = [s for s in report.smells if s.id == "orphaned_enumvalue"]
    assert len(orphan_smells) == 1, (
        f"Expected exactly 1 orphaned_enumvalue, got {len(orphan_smells)}: {orphan_smells}\n"
        f"Draft: {path}"
    )
    assert orphan_smells[0].element == "app::STRAY"


# ══════════════════════════════════════════════════════════════════════════
# duplicate_qname
# ══════════════════════════════════════════════════════════════════════════


def test_duplicate_qname_direct_duplicate() -> None:
    """Two design nodes with the same qualified_name are a blocking smell."""
    design = [
        {
            "name": "Widget",
            "qualified_name": "ui::Widget",
            "type": "ClassNode",
            "composes": [],
        },
        {
            "name": "WidgetCopy",
            "qualified_name": "ui::Widget",  # duplicate
            "type": "ClassNode",
            "composes": [],
        },
    ]
    path = _dump(design, "duplicate_qname_direct")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smells\nDraft: {path}"
    smell = [s for s in report.smells if s.id == "duplicate_qname"]
    assert smell, (
        f"No duplicate_qname smell detected. Smells: {[s.id for s in report.smells]}\n"
        f"Draft: {path}"
    )
    assert "ui::Widget" in smell[0].element


def test_duplicate_qname_unique_names_clean() -> None:
    """All qualified_names are unique under a namespace — no duplicate smell."""
    design = [
        {
            "name": "ns",
            "qualified_name": "ns",
            "type": "NamespaceNode",
            "composes": [
                {"name": "A", "qualified_name": "ns::A", "type": "ClassNode"},
                {"name": "B", "qualified_name": "ns::B", "type": "ClassNode"},
                {"name": "C", "qualified_name": "ns::C", "type": "ClassNode"},
            ],
        },
    ]
    path = _dump(design, "duplicate_qname_unique_clean")

    report = run_all_smells(design)

    assert report.valid, f"Unexpected blocking smells: {report.smells}\nDraft: {path}"


def test_duplicate_qname_three_way() -> None:
    """Three nodes sharing the same qualified_name — flagged once per duplicate."""
    design = [
        {"name": "X1", "qualified_name": "lib::Thing", "type": "ClassNode"},
        {"name": "X2", "qualified_name": "lib::Thing", "type": "ClassNode"},
        {"name": "X3", "qualified_name": "lib::Thing", "type": "InterfaceNode"},
    ]
    path = _dump(design, "duplicate_qname_three_way")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smells\nDraft: {path}"
    dup_smells = [s for s in report.smells if s.id == "duplicate_qname"]
    assert len(dup_smells) == 1, (
        f"Expected 1 duplicate_qname entry, got {len(dup_smells)}. "
        f"The smell aggregates duplicates into one entry per name.\n"
        f"Draft: {path}"
    )
    assert "lib::Thing" in dup_smells[0].element
    assert dup_smells[0].detail and "3" in dup_smells[0].detail, (
        f"Detail should mention count 3, got: {dup_smells[0].detail}"
    )


# ══════════════════════════════════════════════════════════════════════════
# missing_namespace
# ══════════════════════════════════════════════════════════════════════════


def test_missing_namespace_no_namespace_node() -> None:
    """Compounds exist but no NamespaceNode — blocking smell."""
    design = [
        {
            "name": "Migration",
            "qualified_name": "cpp_sqlite::Migration",
            "type": "ClassNode",
        },
    ]
    path = _dump(design, "missing_namespace_no_node")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smell\nDraft: {path}"
    smell = [s for s in report.smells if s.id == "missing_namespace"]
    assert smell, (
        f"No missing_namespace smell. Found: {[s.id for s in report.smells]}\n"
        f"Draft: {path}"
    )


def test_missing_namespace_with_namespace_node_is_clean() -> None:
    """NamespaceNode present with compounds — no smell."""
    design = [
        {
            "name": "cpp_sqlite",
            "qualified_name": "cpp_sqlite",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Migration",
                    "qualified_name": "cpp_sqlite::Migration",
                    "type": "ClassNode",
                },
            ],
        },
    ]
    path = _dump(design, "missing_namespace_clean")

    report = run_all_smells(design)

    smells = [s for s in report.smells if s.id == "missing_namespace"]
    assert not smells, (
        f"Unexpected missing_namespace smell: {smells}\nDraft: {path}"
    )


def test_missing_namespace_only_namespace_node_is_clean() -> None:
    """A single NamespaceNode with no children — no smell (namespace exists)."""
    design = [
        {
            "name": "cpp_sqlite",
            "qualified_name": "cpp_sqlite",
            "type": "NamespaceNode",
        },
    ]
    path = _dump(design, "missing_namespace_only_ns")

    report = run_all_smells(design)

    smells = [s for s in report.smells if s.id == "missing_namespace"]
    assert not smells, (
        f"Unexpected missing_namespace smell: {smells}\nDraft: {path}"
    )


# ══════════════════════════════════════════════════════════════════════════
# unscoped_qname
# ══════════════════════════════════════════════════════════════════════════


def test_unscoped_qname_bare_class() -> None:
    """A ClassNode with no namespace prefix is a blocking smell."""
    design = [
        {
            "name": "Migration",
            "qualified_name": "Migration",  # no ::
            "type": "ClassNode",
        },
    ]
    path = _dump(design, "unscoped_qname_bare")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smell\nDraft: {path}"
    smell = [s for s in report.smells if s.id == "unscoped_qname"]
    assert smell, (
        f"No unscoped_qname smell. Found: {[s.id for s in report.smells]}\n"
        f"Draft: {path}"
    )
    assert "Migration" in smell[0].element


def test_unscoped_qname_scoped_is_clean() -> None:
    """Scoped qualified_name under a namespace — no unscoped smell."""
    design = [
        {
            "name": "cpp_sqlite",
            "qualified_name": "cpp_sqlite",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Migration",
                    "qualified_name": "cpp_sqlite::Migration",
                    "type": "ClassNode",
                },
            ],
        },
    ]
    path = _dump(design, "unscoped_qname_clean")

    report = run_all_smells(design)

    smells = [s for s in report.smells if s.id == "unscoped_qname"]
    assert not smells, (
        f"Unexpected unscoped_qname smell: {smells}\nDraft: {path}"
    )


def test_unscoped_qname_missing_qualified_name() -> None:
    """A compound with no qualified_name at all is flagged."""
    design = [
        {
            "name": "Orphan",
            "qualified_name": "",
            "type": "ClassNode",
        },
    ]
    path = _dump(design, "unscoped_qname_missing")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smell\nDraft: {path}"
    smell = [s for s in report.smells if s.id == "unscoped_qname"]
    assert smell, (
        f"No unscoped_qname smell for missing qualified_name. "
        f"Found: {[s.id for s in report.smells]}\nDraft: {path}"
    )
    assert "(missing qualified_name)" in smell[0].element


# ══════════════════════════════════════════════════════════════════════════
# Combined / edge cases
# ══════════════════════════════════════════════════════════════════════════


def test_multiple_independent_smells() -> None:
    """Multiple unrelated smells are all detected in one report."""
    design = [
        {
            "name": "EmptyEnum",
            "qualified_name": "app::EmptyEnum",
            "type": "EnumNode",
            "composes": [],
        },
        {
            "name": "OrphanValue",
            "qualified_name": "app::OrphanValue",
            "type": "EnumValueNode",
        },
        {
            "name": "A",
            "qualified_name": "ns::Dup",
            "type": "ClassNode",
        },
        {
            "name": "B",
            "qualified_name": "ns::Dup",
            "type": "ClassNode",
        },
    ]
    path = _dump(design, "multiple_independent_smells")

    report = run_all_smells(design)

    assert not report.valid, f"Expected blocking smells\nDraft: {path}"
    smell_ids = {s.id for s in report.smells}
    assert smell_ids >= {
        "orphaned_enum", "orphaned_enumvalue", "duplicate_qname",
        "missing_namespace",
    }, (
        f"Missing expected smell types. Found: {smell_ids}\nDraft: {path}"
    )
    assert report.summary["total"] >= 3


def test_empty_design_is_clean() -> None:
    """An empty design list has no smells at all."""
    report = run_all_smells([])

    assert report.valid
    assert report.summary["total"] == 0
    assert report.smells == []


def test_design_with_only_classes_is_clean() -> None:
    """A design with only well-formed classes under a namespace should pass."""
    design = [
        {
            "name": "climate",
            "qualified_name": "climate",
            "type": "NamespaceNode",
            "composes": [
                {
                    "name": "Thermostat",
                    "qualified_name": "climate::Thermostat",
                    "type": "ClassNode",
                    "composes": [
                        {
                            "name": "setTarget",
                            "qualified_name": "climate::Thermostat::setTarget",
                            "type": "MethodNode",
                            "return_type": "void",
                        },
                    ],
                },
                {
                    "name": "Display",
                    "qualified_name": "climate::Display",
                    "type": "ClassNode",
                    "composes": [],
                },
            ],
        },
    ]
    path = _dump(design, "clean_class_only_design")

    report = run_all_smells(design)

    assert report.valid, f"Unexpected smells in clean design: {report.smells}\nDraft: {path}"
    assert report.summary["total"] == 0
