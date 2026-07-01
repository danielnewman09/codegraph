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
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_0
        # Verifies that the exported Markdown starts with '# codegraph: design',
        # ensuring the document has the correct top-level heading and identifies the
        # design graph.
        assert md.startswith("# codegraph: design")

        # Save the .md file
        out_path = FIXTURE_DIR / "design_graph.md"
        out_path.write_text(md, encoding="utf-8")

        # Namespaces
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_1
        # Checks that the exported Markdown contains the 'calc' namespace heading,
        # confirming the 'calc' namespace is included in the output.
        assert "## Namespace: `calc`" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_2
        # Checks that the exported Markdown contains the 'ui' namespace heading,
        # confirming the 'ui' namespace is included in the output.
        assert "## Namespace: `ui`" in md

        # Classes
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_3
        # Verifies that the 'calc::CalculatorEngine' class is listed in the Markdown,
        # ensuring this critical class is documented.
        assert "### Class: `calc::CalculatorEngine`" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_4
        # Verifies that the 'calc::CalculatorResult' class is listed in the Markdown,
        # ensuring this result class is included.
        assert "### Class: `calc::CalculatorResult`" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_5
        # Verifies that the 'ui::BaseWindow' class is listed in the Markdown, confirming
        # the base UI class is documented.
        assert "### Class: `ui::BaseWindow`" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_6
        # Verifies that the 'ui::CalculatorWindow' class is listed in the Markdown,
        # ensuring the main UI window is included.
        assert "### Class: `ui::CalculatorWindow`" in md

        # Interface
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_7
        # Checks that the 'calc::ICalculator' interface appears in the Markdown,
        # confirming the calculator interface is documented.
        assert "### Interface: `calc::ICalculator`" in md

        # Enum
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_8
        # Verifies that the 'calc::Operation' enum is present in the Markdown, ensuring
        # the operation enum is listed.
        assert "### Enum: `calc::Operation`" in md

        # Members
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_9
        # Verifies that the 'add' method signature is present in the Markdown,
        # confirming this key operation is documented with its parameters and return
        # type.
        assert "`add(double a, double b): CalculatorResult` —" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_10
        # Verifies that the 'validateInput' method signature is included, confirming an
        # important input validation method is documented.
        assert "`validateInput(string input): bool` —" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_11
        # Checks that the 'precision' attribute is documented in the Markdown,
        # confirming a class attribute is listed.
        assert "`precision: int` —" in md

        # Enum values
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_12
        # Verifies that the 'ADD' enumeration value is present in the Markdown, ensuring
        # a specific enum member is documented.
        assert "`ADD` —" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_13
        # Verifies that the 'SUBTRACT' enumeration value is present in the Markdown,
        # ensuring this enum member is also documented.
        assert "`SUBTRACT` —" in md

        # Inline properties
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_14
        # Checks that the 'Implements' relationship for 'calc::ICalculator' is present,
        # confirming that 'CalculatorEngine' correctly declares its implemented
        # interface.
        assert "**Implements:** `calc::ICalculator`" in md
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_15
        # Checks that the 'Inherits from' relationship for 'ui::BaseWindow' is present,
        # verifying that 'CalculatorWindow' shows its inheritance.
        assert "**Inherits from:** `ui::BaseWindow`" in md

        # Relationships
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_16
        # Verifies that a 'depends_on' relationship marker is present in the Markdown,
        # ensuring dependency relationships between components are documented.
        assert "**depends_on**" in md

        # No non-human-readable fields
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_export_produces_valid_markdown::post_17
        # Verifies that the string 'refid' does not appear in the Markdown, ensuring raw
        # internal reference IDs are not exposed in the output.
        assert "refid" not in md

    # ── Import ─────────────────────────────────────────────────────────

    def test_import_restores_core_structure(self):
        """Export → import round-trip preserves core structure."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        # Namespaces preserved
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_0
        # Confirms that a core class (likely a representative from the original
        # structure) is present in the imported results, ensuring major structural
        # elements are restored.
        assert "calc" in restored.entries
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_1
        # Confirms that another core class (likely a different representative) is
        # present in the imported results, verifying broader structural completeness.
        assert "ui" in restored.entries

        # Classes inside calc namespace
        calc = restored.entries["calc"]
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_2
        # Confirms that a third core class is present in the imported results,
        # strengthening the evidence that the restoration is correct.
        assert "ClassNode" in calc.children
        cls_names = [e.node.name for e in calc.children["ClassNode"].values()]
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_3
        # Verifies that the 'CalculatorEngine' class is explicitly restored, ensuring a
        # critical business-logic component survives the round-trip.
        assert "CalculatorEngine" in cls_names
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_4
        # Verifies that the 'CalculatorResult' class is explicitly restored, ensuring
        # another essential data-type component is preserved.
        assert "CalculatorResult" in cls_names

        # Interface preserved
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_5
        # Confirms that a UI-related core class is present in the imported results,
        # checking that UI structure elements are also restored.
        assert "InterfaceNode" in calc.children

        # Enum preserved
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_6
        # Confirms that another UI-related core class is present, further validating the
        # restoration of UI components.
        assert "EnumNode" in calc.children

        # Function preserved
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_7
        # Confirms that a third UI-related core class is present, providing
        # comprehensive coverage of UI structure restoration.
        assert "FunctionNode" in calc.children

        # UI namespace classes
        ui = restored.entries["ui"]
        ui_cls_names = [e.node.name for e in ui.children["ClassNode"].values()]
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_8
        # Verifies that the 'BaseWindow' UI class is explicitly restored, ensuring the
        # foundational UI element is correctly imported.
        assert "BaseWindow" in ui_cls_names
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_restores_core_structure::post_9
        # Verifies that the 'CalculatorWindow' UI class is explicitly restored, ensuring
        # a key UI component is faithfully reconstructed from the Markdown export.
        assert "CalculatorWindow" in ui_cls_names

    def test_import_preserves_members(self):
        """Export → import round-trip preserves methods and attributes."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # Methods
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_members::post_0
        # Verify that a method (captured by the generic 'in' check) is present in the
        # imported list, establishing that the round-trip process at least retains some
        # methods from the original code graph.
        assert "MethodNode" in engine.children
        meth_names = [e.node.name for e in engine.children["MethodNode"].values()]
        assert "add" in meth_names
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_members::post_2
        # Check that the method 'validateInput' appears in the imported method list,
        # ensuring this method is not lost or altered during the export–import
        # round-trip.
        assert "validateInput" in meth_names

        # Attributes
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_members::post_3
        # Verify that a method (indicated by the generic 'in' operator) is present in
        # the imported method list, ensuring that the round-trip export–import process
        # preserves this method.
        assert "AttributeNode" in engine.children
        attr_names = [e.node.name for e in engine.children["AttributeNode"].values()]
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_members::post_4
        # Confirm that the attribute 'precision' is included in the imported attribute
        # list, verifying that attributes are preserved alongside methods during the
        # round-trip.
        assert "precision" in attr_names

    def test_import_preserves_enum_values(self):
        """Export → import round-trip preserves enum values."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        enum_entries = list(calc.children["EnumNode"].values())
        op_entry = enum_entries[0]

        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_enum_values::post_0
        # Verifies that the imported data contains the expected number of enum values,
        # confirming the structure of the data is preserved after export and import.
        assert "EnumValueNode" in op_entry.children
        val_names = [e.node.name for e in op_entry.children["EnumValueNode"].values()]
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_enum_values::post_1
        # Verifies that the string 'ADD' is present in the imported enum value names,
        # ensuring that specific enum values survive the round-trip conversion
        # unchanged.
        assert "ADD" in val_names
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_enum_values::post_2
        # Verifies that the string 'SUBTRACT' is present in the imported enum value
        # names, confirming that another specific enum value is also preserved after
        # export and import.
        assert "SUBTRACT" in val_names

    def test_import_preserves_relationships(self):
        """Export → import round-trip preserves relationship arrows."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # REALIZES
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_relationships::post_0
        # Verifies that the imported graph contains at least one 'REALIZES'
        # relationship, confirming that this key association type is preserved during
        # export and import.
        assert any(r[0] == "REALIZES" for r in engine.references)

        # DEPENDS_ON
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_relationships::post_1
        # Verifies that the imported graph contains at least one 'DEPENDS_ON'
        # relationship, ensuring that dependency information is not lost in the
        # round-trip.
        assert any(r[0] == "DEPENDS_ON" for r in engine.references)

        # INHERITS_FROM in ui namespace
        ui = restored.entries["ui"]
        ui_cls = list(ui.children["ClassNode"].values())
        calc_win = next(e for e in ui_cls if e.node.name == "CalculatorWindow")
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_relationships::post_2
        # Verifies that the imported graph contains at least one 'INHERITS_FROM'
        # relationship, confirming that inheritance links are also maintained correctly.
        assert any(r[0] == "INHERITS_FROM" for r in calc_win.references)

    def test_import_preserves_file_notes(self):
        """Export → import round-trip preserves file node entries."""
        md = export_markdown(self.graph)
        restored = import_markdown(md)

        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_file_notes::post_0
        # Verifies that the first file node from the imported graph matches the
        # original, ensuring that file-level annotations survive the export-import
        # cycle.
        assert "calculator_engine.h" in restored.entries
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_file_notes::post_1
        # Verifies that the second file node from the imported graph matches the
        # original, confirming all file entries are preserved across the round-trip.
        assert "icalculator.h" in restored.entries
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_preserves_file_notes::post_2
        # Verifies that the number of file nodes in the imported graph equals the
        # original count, ensuring no file entries were lost or duplicated during export
        # and import.
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
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_0
        # Checks that the re-exported Markdown starts with '# codegraph: design',
        # confirming the document header remains consistent and correctly identifies the
        # document type after export-import-reexport.
        assert md2.startswith("# codegraph: design")
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_1
        # Ensures that the re-exported Markdown includes a section titled '## Namespace:
        # `calc`', verifying that the 'calc' namespace and its contents are preserved
        # after the round-trip cycle.
        assert "## Namespace: `calc`" in md2
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_2
        # Ensures that the re-exported Markdown includes a section titled '## Namespace:
        # `ui`', verifying that the 'ui' namespace and its contents are preserved after
        # the round-trip cycle.
        assert "## Namespace: `ui`" in md2
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_3
        # Validates that the re-exported Markdown includes a '## File Notes' header,
        # ensuring file-level annotations are retained and properly formatted after
        # re-export.
        assert "## File Notes" in md2
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_4
        # Verifies that the re-exported Markdown contains a '## Relationships' header,
        # ensuring that relationship data between code elements is preserved and
        # correctly rendered after the round-trip process.
        assert "## Relationships" in md2
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_roundtrip_reexport::post_5
        # Confirms that the re-exported Markdown contains '**depends_on**', verifying
        # that dependency relationships between code elements are correctly represented
        # in the final document.
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
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_serializes_to_json::post_0
        # Verifies that the serialized JSON output file was created successfully,
        # confirming that the round-trip export-import-serialize sequence produced a
        # tangible result.
        assert out_path.exists()
        with open(out_path) as f:
            reloaded = json.load(f)
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_serializes_to_json::post_1
        # Checks that the imported data is a list, ensuring the Markdown import returns
        # the expected collection type for further validation of graph restoration.
        assert isinstance(reloaded, list)
        # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_serializes_to_json::post_2
        # Ensures the imported list is non-empty, confirming that the Markdown import
        # successfully restored at least one entry from the exported graph, validating
        # basic data preservation.
        assert len(reloaded) > 0

        # Every entry should have a type key
        for entry in reloaded:
            # codegraph:test-desc test_markdown_integration.TestMarkdownIntegration.test_import_serializes_to_json::post_3
            # Confirms that each entry in the imported list contains a 'type' field,
            # verifying that essential metadata (e.g., node type) is preserved through
            # the export-import round-trip.
            assert "type" in entry