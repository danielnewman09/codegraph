"""Unit tests for design-smell detection.

Tests the declarative smell-checker registry: each checker receives
in-memory ``list[dict]`` nodes and returns ``list[Smell]``.

Every test writes the invalid design to a gitignored file
(``tests/unit_test_data/``) so a human can review the fixture
side-by-side with the detected smells.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codegraph_design.tools.design_smells import (
    Severity,
    Smell,
    SmellReport,
    run_all_smells,
    handle_check_design_smells,
    _registry,
    _check_orphaned_enums,
    _check_orphaned_enumvalues,
    _check_duplicate_names,
)

# ── Git-ignored output directory for human review ────────────────────

UNIT_DATA = Path(__file__).resolve().parents[1] / "unit_test_data"


def _write_review_fixture(name: str, nodes: list[dict]) -> Path:
    """Save an invalid design fixture for human review.

    Returns the path so the test can display it in assertion messages.
    """
    UNIT_DATA.mkdir(exist_ok=True)
    path = UNIT_DATA / f"smells_{name}.json"
    path.write_text(json.dumps(nodes, indent=2))
    return path


def _make_namespace(name: str, composes: list[dict] | None = None, **kwargs) -> dict:
    """Minimal NamespaceNode dict, optionally with composed children."""
    node: dict = {"type": "NamespaceNode", "qualified_name": name, **kwargs}
    if composes is not None:
        node["composes"] = composes
    return node


def _make_class(name: str, **kwargs) -> dict:
    """Minimal ClassNode dict."""
    return {"type": "ClassNode", "qualified_name": name, **kwargs}


def _make_enum(name: str, values: list[str] | None = None) -> dict:
    """Minimal EnumNode dict, optionally with EnumValueNode children."""
    node: dict = {"type": "EnumNode", "qualified_name": name}
    if values is not None:
        node["composes"] = [
            {"type": "EnumValueNode", "qualified_name": v} for v in values
        ]
    return node


def _make_standalone_enumvalue(name: str) -> dict:
    """An EnumValueNode that is NOT nested under an EnumNode."""
    return {"type": "EnumValueNode", "qualified_name": name}


# ══════════════════════════════════════════════════════════════════════
# Orphaned enum
# ══════════════════════════════════════════════════════════════════════


class TestOrphanedEnum:
    """EnumNode with zero EnumValueNode children."""

    def test_detects_orphaned_enum(self):
        nodes = [
            _make_enum("colors::Palette"),        # orphaned — no values
            _make_enum("shapes::Kind", ["Circle", "Square"]),  # valid
        ]

        smells = _check_orphaned_enums(nodes)

        assert len(smells) == 1
        s = smells[0]
        assert s.id == "orphaned_enum"
        assert s.severity == Severity.BLOCKING
        assert s.element == "colors::Palette"
        assert "no values" in s.detail.lower()

    def test_all_valid_returns_empty(self):
        nodes = [
            _make_enum("shapes::Kind", ["Circle", "Square"]),
        ]
        smells = _check_orphaned_enums(nodes)
        assert smells == []

    def test_no_enums_returns_empty(self):
        nodes = [_make_class("foo::Bar"), _make_class("foo::Baz")]
        smells = _check_orphaned_enums(nodes)
        assert smells == []

    def test_multiple_orphaned_enums(self):
        nodes = [
            _make_enum("colors::Palette"),
            _make_enum("fonts::Family"),
            _make_enum("ok::Kind", ["A"]),
        ]
        smells = _check_orphaned_enums(nodes)
        assert len(smells) == 2
        elements = {s.element for s in smells}
        assert elements == {"colors::Palette", "fonts::Family"}


# ══════════════════════════════════════════════════════════════════════
# Orphaned enum values
# ══════════════════════════════════════════════════════════════════════


class TestOrphanedEnumValues:
    """EnumValueNode not nested under any EnumNode."""

    def test_detects_standalone_enumvalue(self):
        nodes = [
            _make_enum("shapes::Kind", ["Circle"]),
            _make_standalone_enumvalue("shapes::Orphan"),   # no parent
        ]
        smells = _check_orphaned_enumvalues(nodes)
        assert len(smells) == 1
        s = smells[0]
        assert s.id == "orphaned_enumvalue"
        assert s.severity == Severity.BLOCKING
        assert s.element == "shapes::Orphan"

    def test_multiple_standalone_values(self):
        nodes = [
            _make_standalone_enumvalue("a::X"),
            _make_standalone_enumvalue("b::Y"),
        ]
        smells = _check_orphaned_enumvalues(nodes)
        assert len(smells) == 2
        assert {s.element for s in smells} == {"a::X", "b::Y"}

    def test_nested_values_are_not_orphaned(self):
        nodes = [
            _make_enum("shapes::Kind", ["Circle", "Square"]),
        ]
        smells = _check_orphaned_enumvalues(nodes)
        assert smells == []

    def test_no_enumvalues_returns_empty(self):
        nodes = [_make_class("foo::Bar")]
        smells = _check_orphaned_enumvalues(nodes)
        assert smells == []


# ══════════════════════════════════════════════════════════════════════
# Duplicate qualified names
# ══════════════════════════════════════════════════════════════════════


class TestDuplicateNames:
    """Two or more design nodes sharing the same qualified_name."""

    def test_detects_exact_duplicate(self):
        nodes = [
            _make_class("app::Controller"),
            _make_class("app::Controller"),
            _make_class("app::Service"),
        ]
        smells = _check_duplicate_names(nodes)
        assert len(smells) == 1
        s = smells[0]
        assert s.id == "duplicate_qname"
        assert s.severity == Severity.BLOCKING
        assert s.element == "app::Controller"
        assert "appears 2 times" in s.detail

    def test_triplicate(self):
        nodes = [_make_class("X")] * 3
        smells = _check_duplicate_names(nodes)
        assert len(smells) == 1
        assert "appears 3 times" in smells[0].detail

    def test_all_unique_returns_empty(self):
        nodes = [
            _make_class("app::A"),
            _make_class("app::B"),
        ]
        smells = _check_duplicate_names(nodes)
        assert smells == []

    def test_empty_name_nodes_are_skipped(self):
        nodes = [
            {"type": "ClassNode", "qualified_name": ""},
            {"type": "ClassNode", "qualified_name": ""},
        ]
        smells = _check_duplicate_names(nodes)
        assert smells == []


# ══════════════════════════════════════════════════════════════════════
# Orchestrator integration
# ══════════════════════════════════════════════════════════════════════


class TestRunAllSmells:
    """The ``run_all_smells`` orchestrator runs all registered checkers."""

    def test_valid_design_passes_all(self):
        nodes = [
            {
                "type": "NamespaceNode",
                "qualified_name": "app",
                "composes": [
                    _make_enum("colors::Palette", ["Red", "Blue"]),
                    _make_class("app::Controller"),
                    _make_class("app::Service"),
                ],
            },
        ]
        report = run_all_smells(nodes)
        assert report.valid is True
        assert report.summary["blocking"] == 0
        assert report.summary["total"] == 0

    def test_invalid_design_combines_errors(self):
        """A flawed design should trigger multiple checkers."""
        nodes = [
            _make_enum("orphaned::Palette"),                     # orphaned enum
            _make_standalone_enumvalue("orphaned::LostValue"),   # orphaned value
            _make_class("dup::Widget"),
            _make_class("dup::Widget"),                          # duplicate
        ]
        review_path = _write_review_fixture("combined_invalid", nodes)

        report = run_all_smells(nodes)

        assert report.valid is False, (
            f"Expected blocking smells. See fixture: {review_path}\n"
            f"Summary: {json.dumps(report.summary)}\n"
            f"Smells: {json.dumps([vars(s) for s in report.smells], indent=2)}"
        )
        assert report.summary["blocking"] >= 3
        smell_ids = {s.id for s in report.smells}
        assert smell_ids >= {
            "orphaned_enum", "orphaned_enumvalue", "duplicate_qname"
        }

    def test_only_warnings_yields_valid(self):
        """Blocking == 0 → valid, even if warnings/info present."""
        # Currently no warning/info checkers are registered, so this is a
        # forward-looking test.  If a checker is added with severity
        # "warning", make sure valid is still True.
        nodes = [
            {
                "type": "NamespaceNode",
                "qualified_name": "app",
                "composes": [_make_class("app::A")],
            },
        ]
        report = run_all_smells(nodes)
        assert report.valid is True

    def test_recommendations_are_populated(self):
        nodes = [
            _make_enum("colors::Palette"),           # orphaned
            _make_class("dup::X"),
            _make_class("dup::X"),                   # duplicate
        ]
        review_path = _write_review_fixture("recommendations", nodes)

        report = run_all_smells(nodes)

        for s in report.smells:
            assert s.recommendation, (
                f"Smell {s.id} has no recommendation.\n"
                f"Fixture: {review_path}"
            )

    def test_empty_nodes_returns_blocking(self):
        """Empty node list should be caught by the handler, not the
        orchestrator — but the orchestrator itself returns empty."""
        report = run_all_smells([])
        assert report.valid is True
        assert report.summary["total"] == 0


# ══════════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════════


class TestRegistry:
    """The decorator registry is self-documenting."""

    def test_all_checkers_have_ids(self):
        for c in _registry:
            assert hasattr(c, "_smell_id"), f"{c} missing _smell_id"
            assert hasattr(c, "_severity"), f"{c} missing _severity"

    def test_all_checkers_are_callable(self):
        empty: list[dict] = []
        for c in _registry:
            result = c(empty)
            assert isinstance(result, list), f"{c} should return list[Smell]"


# ══════════════════════════════════════════════════════════════════════
# Tool handler
# ══════════════════════════════════════════════════════════════════════


class TestToolHandler:
    """``handle_check_design_smells`` — the tool entry point."""

    def test_valid_design(self, design_dispatcher):
        nodes = [
            _make_namespace("app", composes=[
                _make_class("app::Controller"),
                _make_class("app::Service"),
            ]),
        ]
        raw = handle_check_design_smells(design_dispatcher, {"nodes": nodes})
        result = json.loads(raw)
        assert result["valid"] is True
        assert result["summary"]["blocking"] == 0

    def test_invalid_design(self, design_dispatcher):
        nodes = [
            _make_enum("colors::Palette"),           # orphaned
            _make_class("dup::X"),
            _make_class("dup::X"),                   # duplicate
        ]
        review_path = _write_review_fixture("tool_handler_invalid", nodes)

        raw = handle_check_design_smells(design_dispatcher, {"nodes": nodes})
        result = json.loads(raw)

        assert result["valid"] is False, (
            f"Expected blocking smells. See fixture: {review_path}\n"
            f"Result: {json.dumps(result, indent=2)}"
        )
        assert result["summary"]["blocking"] >= 2

    def test_no_nodes_falls_back_to_draft(self, design_dispatcher):
        """When nodes list is empty, the handler should fall back to
        the dispatcher's design_draft."""
        # No draft → should return a blocking error
        raw = handle_check_design_smells(design_dispatcher, {"nodes": []})
        result = json.loads(raw)
        assert result["valid"] is False
        smells = result.get("smells", [])
        assert any(s["id"] == "no_input" for s in smells)

    def test_empty_call_no_draft(self, design_dispatcher):
        """Calling with no nodes and no draft should produce no_input."""
        raw = handle_check_design_smells(design_dispatcher, {})
        result = json.loads(raw)
        assert result["valid"] is False
        smells = result.get("smells", [])
        assert any(s["id"] == "no_input" for s in smells)


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def design_dispatcher():
    """A DesignToolDispatcher with no preloaded context.

    Tests that need a full Neo4j-backed dispatcher should use the
    integration marker.
    """
    from codegraph_design.tools.dispatcher import DesignToolDispatcher
    return DesignToolDispatcher()
