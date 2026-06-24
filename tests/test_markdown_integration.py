"""Integration test: full Calculator graph → Markdown → round-trip.

Builds the complete Calculator graph from ``design_graph.json``, exports it
to Markdown, imports it back, and verifies the round-trip preserves core
structure, members, and relationships.

Saves the following artefacts:

- ``unit_test_data/design_graph.md`` — exported Markdown source
- ``unit_test_data/design_graph_roundtrip.md`` — round-tripped Markdown
  (export → import → re-export), useful for visual diff
- ``tests/data/design_graph_md.json`` — restored graph serialized as JSON,
  suitable for diffing against the original ``design_graph.json`` to see
  exactly what the Markdown round-trip preserves and what it loses.

Requires Neo4j for the initial ``to_neo4j()`` call.
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.export.markdown import export_markdown, import_markdown

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"


# ── Full integration: fixture → LayerGraph → Markdown → round-trip ──────────


class TestMarkdownIntegration:
    """End-to-end test: load design_graph.json, export to Markdown,
    import back, re-export, and verify content."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load and persist the fixture graph once for all tests."""
        with open(FIXTURE) as f:
            self.nodes_data = json.load(f)
        self.graph = LayerGraph.deserialize(self.nodes_data)
        self.graph.to_neo4j()
        FIXTURE_DIR.mkdir(exist_ok=True)

    # ── Export ──────────────────────────────────────────────────────────

    def test_export_produces_valid_markdown(self):
        """Export the full Calculator graph to Markdown and save to disk."""
        md = export_markdown(self.graph)

        # Basic structure
        assert md.startswith("# codegraph: design")

        # Save the .md file
        out_path = FIXTURE_DIR / "design_graph.md"
        out_path.write_text(md, encoding="utf-8")

        # Namespaces
        assert "## Namespace: `calc`" in md
        assert "## Namespace: `ui`" in md

        # Classes
        assert "### Class: `calc::CalculatorEngine`" in md
        assert "### Class: `calc::CalculatorResult`" in md
        assert "### Class: `ui::BaseWindow`" in md
        assert "### Class: `ui::CalculatorWindow`" in md

        # Interface
        assert "### Interface: `calc::ICalculator`" in md

        # Enum
        assert "### Enum: `calc::Operation`" in md

        # Members
        assert "`add(double a, double b): CalculatorResult` —" in md
        assert "`validateInput(string input): bool` —" in md
        assert "`precision: int` —" in md

        # Enum values
        assert "`ADD` —" in md
        assert "`SUBTRACT` —" in md

        # Inline properties
        assert "**Implements:** `calc::ICalculator`" in md
        assert "**Inherits from:** `ui::BaseWindow`" in md

        # Relationships
        assert "**depends_on**" in md

        # No non-human-readable fields
        assert "refid" not in md

    # ── Import ─────────────────────────────────────────────────────────

    def test_import_restores_core_structure(self):
        """Export → import round-trip preserves core structure."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        # Namespaces preserved
        assert "calc" in restored.entries
        assert "ui" in restored.entries

        # Classes inside calc namespace
        calc = restored.entries["calc"]
        assert "ClassNode" in calc.children
        cls_names = [e.node.name for e in calc.children["ClassNode"].values()]
        assert "CalculatorEngine" in cls_names
        assert "CalculatorResult" in cls_names

        # Interface preserved
        assert "InterfaceNode" in calc.children

        # Enum preserved
        assert "EnumNode" in calc.children

        # Function preserved
        assert "FunctionNode" in calc.children

        # UI namespace classes
        ui = restored.entries["ui"]
        ui_cls_names = [e.node.name for e in ui.children["ClassNode"].values()]
        assert "BaseWindow" in ui_cls_names
        assert "CalculatorWindow" in ui_cls_names

    def test_import_preserves_members(self):
        """Export → import round-trip preserves methods and attributes."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # Methods
        assert "MethodNode" in engine.children
        meth_names = [e.node.name for e in engine.children["MethodNode"].values()]
        assert "add" in meth_names
        assert "validateInput" in meth_names

        # Attributes
        assert "AttributeNode" in engine.children
        attr_names = [e.node.name for e in engine.children["AttributeNode"].values()]
        assert "precision" in attr_names

    def test_import_preserves_enum_values(self):
        """Export → import round-trip preserves enum values."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        enum_entries = list(calc.children["EnumNode"].values())
        op_entry = enum_entries[0]

        assert "EnumValueNode" in op_entry.children
        val_names = [e.node.name for e in op_entry.children["EnumValueNode"].values()]
        assert "ADD" in val_names
        assert "SUBTRACT" in val_names

    def test_import_preserves_relationships(self):
        """Export → import round-trip preserves relationship arrows."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # REALIZES
        assert any(r[0] == "REALIZES" for r in engine.references)

        # DEPENDS_ON
        assert any(r[0] == "DEPENDS_ON" for r in engine.references)

        # INHERITS_FROM in ui namespace
        ui = restored.entries["ui"]
        ui_cls = list(ui.children["ClassNode"].values())
        calc_win = next(e for e in ui_cls if e.node.name == "CalculatorWindow")
        assert any(r[0] == "INHERITS_FROM" for r in calc_win.references)

    def test_import_preserves_file_notes(self):
        """Export → import round-trip preserves file node entries."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        assert "calculator_engine.h" in restored.entries
        assert "icalculator.h" in restored.entries
        assert "operation.h" in restored.entries

    # ── Round-trip re-export ────────────────────────────────────────────

    def test_roundtrip_reexport(self):
        """Export → import → re-export produces valid, stable Markdown."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)
        md2 = export_markdown(restored)

        # Save the round-trip markdown for visual diffing
        out_path = FIXTURE_DIR / "design_graph_roundtrip.md"
        out_path.write_text(md2, encoding="utf-8")

        # Should still be valid markdown with all sections
        assert md2.startswith("# codegraph: design")
        assert "## Namespace: `calc`" in md2
        assert "## Namespace: `ui`" in md2
        assert "## File Notes" in md2
        assert "## Relationships" in md2
        assert "**depends_on**" in md2

    def test_import_serializes_to_json(self):
        """Export → import round-trip, then serialize the restored graph to JSON.

        Saves ``design_graph_md.json`` alongside the original
        ``design_graph.json`` fixture so the two can be diffed to see
        exactly what the Markdown round-trip preserves and what it loses."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        json_data = restored.serialize(fields="all")
        out_path = DATA_DIR / "design_graph_md.json"
        out_path.write_text(
            json.dumps(json_data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Verify the file was written and is valid JSON
        assert out_path.exists()
        with open(out_path) as f:
            reloaded = json.load(f)
        assert isinstance(reloaded, list)
        assert len(reloaded) > 0

        # Every entry should have a type key
        for entry in reloaded:
            assert "type" in entry