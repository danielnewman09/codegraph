"""Integration test: full Calculator graph → PlantUML → PNG.

Builds the complete Calculator graph from ``design_graph.json``, exports it
to PlantUML, imports it back, and compiles the diagram to PNG.

Saves the following artefacts:

- ``unit_test_data/plantuml_integration.puml`` — exported PlantUML source
- ``unit_test_data/plantuml_integration.png`` — compiled diagram (requires jar)
- ``tests/data/design_graph_puml.json`` — restored graph serialized as JSON,
  suitable for diffing against the original ``design_graph.json`` to see
  exactly what the PlantUML round-trip preserves and what it loses.

Requires Neo4j for the initial ``to_neo4j()`` call.
PlantUML PNG compilation is skipped if ``tools/plantuml.jar`` is absent.
"""

import json
import subprocess
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode
from codegraph.export.plantuml import export_plantuml, import_plantuml

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"

# ── PNG compilation constants ────────────────────────────────────────────

PLANTUML_JAR = Path(__file__).resolve().parent.parent / "tools" / "plantuml.jar"


def _plantuml_available() -> bool:
    """Check whether the PlantUML jar exists and java is on PATH."""
    if not PLANTUML_JAR.is_file():
        return False
    try:
        subprocess.run(["java", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Full integration: fixture → LayerGraph → PlantUML → PNG ────────────────


class TestPlantUMLIntegration:
    """End-to-end test: load design_graph.json, export to PlantUML,
    import back, compile to PNG, and verify diagram content."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load and persist the fixture graph once for all tests."""
        with open(FIXTURE) as f:
            self.nodes_data = json.load(f)
        self.graph = LayerGraph.deserialize(self.nodes_data)
        self.graph.to_neo4j()
        FIXTURE_DIR.mkdir(exist_ok=True)

    # ── Export ──────────────────────────────────────────────────────────

    def test_export_produces_valid_plantuml(self):
        """Export the full Calculator graph to PlantUML and save to disk."""
        puml = export_plantuml(self.graph)

        # Basic structure
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_0
        # Checks that the generated PlantUML output starts with '@startuml', a
        # fundamental syntax requirement for valid PlantUML diagrams.
        assert puml.startswith("@startuml")
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_1
        # Verifies that the PlantUML output ends with '@enduml', a necessary closing tag
        # for valid PlantUML diagram syntax.
        assert puml.endswith("@enduml")

        # Save the .puml file
        out_path = FIXTURE_DIR / "plantuml_integration.puml"
        out_path.write_text(puml, encoding="utf-8")

        # Namespaces
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_2
        # Verifies that the 'calc' package is declared in the PlantUML output, ensuring
        # package-level grouping from the source code is maintained.
        assert 'package "calc"' in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_3
        # Verifies that the 'ui' package is declared in the PlantUML output, ensuring
        # proper package separation for user interface components in the diagram.
        assert 'package "ui"' in puml

        # Classes
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_4
        # Verifies that the 'CalculatorEngine' class appears in the PlantUML diagram,
        # confirming that core business logic classes are exported.
        assert "CalculatorEngine" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_5
        # Checks that 'CalculatorResult' class is present in the diagram, confirming
        # that return types or result objects are included in the export.
        assert "CalculatorResult" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_6
        # Confirms that 'BaseWindow' base class is represented in the diagram, ensuring
        # inheritance within the UI layer is captured in the export.
        assert "BaseWindow" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_7
        # Verifies that 'CalculatorWindow' UI class appears in the PlantUML diagram,
        # ensuring user interface components from the 'ui' package are exported.
        assert "CalculatorWindow" in puml

        # Interface
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_8
        # Ensures that the 'ICalculator' interface is present in the diagram, confirming
        # that interfaces are correctly exported.
        assert "ICalculator" in puml

        # Enum
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_9
        # Verifies that the class 'Operation' is included in the diagram, ensuring that
        # all expected classes from the calculator module are represented in the export.
        assert "Operation" in puml

        # Members inside classes
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_10
        # Verifies that the public method '+add' is present in the PlantUML diagram,
        # ensuring method visibility is correctly exported.
        assert "+add" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_11
        # Confirms that '+validateInput' method is included in the exported diagram,
        # validating that public methods of the code are represented in the PlantUML
        # output.
        assert "+validateInput" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_12
        # Confirms that 'precision' attribute appears in the PlantUML diagram,
        # validating that class attributes are captured in the export.
        assert "precision" in puml

        # Enum values
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_13
        # Verifies that 'ADD' appears in the PlantUML output, confirming that the ADD
        # operation is correctly represented in the exported diagram.
        assert "ADD" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_14
        # Confirms that 'SUBTRACT' operation is represented in the diagram, ensuring
        # subtraction logic is captured in the export.
        assert "SUBTRACT" in puml

        # Relationships
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_15
        # Checks that 'realizes' (interface realization) is in the PlantUML output,
        # confirming that interface-implementation relationships are accurately
        # diagrammed.
        assert "realizes" in puml
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_export_produces_valid_plantuml::post_16
        # Checks that 'inherits_from' is present in the PlantUML diagram, ensuring
        # inheritance relationships from the code are properly captured.
        assert "inherits_from" in puml

    # ── Import ─────────────────────────────────────────────────────────

    def test_import_restores_core_structure(self):
        """Export → import round-trip preserves core structure."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        # Namespaces preserved
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_0
        # Verifies that a key class from the core structure is present in the
        # re-imported graph, ensuring the round-trip preserved it.
        assert "calc" in restored.entries
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_1
        # Checks that another core class is present in the re-imported graph, confirming
        # the export-import cycle did not lose it.
        assert "ui" in restored.entries

        # Classes inside calc namespace
        calc = restored.entries["calc"]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_2
        # Asserts that a third core class is still present after the round-trip,
        # validating the integrity of the process.
        assert "ClassNode" in calc.children
        cls_names = [e.node.name for e in calc.children["ClassNode"].values()]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_3
        # Ensures the 'CalculatorEngine' class, part of the core structure, is present
        # in the re-imported graph. This is critical because it must survive the
        # export-import cycle.
        assert "CalculatorEngine" in cls_names
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_4
        # Verifies that the 'CalculatorResult' class is present in the re-imported
        # graph, confirming its preservation during the round-trip.
        assert "CalculatorResult" in cls_names

        # Interface preserved
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_5
        # Confirms that a specific UI class from the core structure is included in the
        # re-imported UI class names.
        assert "InterfaceNode" in calc.children

        # Enum preserved
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_6
        # Checks that another UI class is present in the re-imported UI class names,
        # ensuring UI structure is intact.
        assert "EnumNode" in calc.children

        # Function preserved
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_7
        # Asserts that yet another core class is present in the re-imported graph,
        # reinforcing the round-trip fidelity.
        assert "FunctionNode" in calc.children

        # UI namespace classes
        ui = restored.entries["ui"]
        ui_cls_names = [e.node.name for e in ui.children["ClassNode"].values()]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_8
        # Verifies that the 'BaseWindow' UI class is present in the re-imported UI class
        # names, confirming the preservation of the UI hierarchy.
        assert "BaseWindow" in ui_cls_names
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_restores_core_structure::post_9
        # Ensures that the 'CalculatorWindow' UI class is present in the re-imported UI
        # class names, validating the round-trip for a key UI component.
        assert "CalculatorWindow" in ui_cls_names

    def test_import_preserves_members(self):
        """Export → import round-trip preserves methods and attributes."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # Methods
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_members::post_0
        # Check that the imported code graph is structurally valid and contains the
        # expected class, ensuring the basic import process works.
        assert "MethodNode" in engine.children
        meth_names = [e.node.name for e in engine.children["MethodNode"].values()]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_members::post_1
        # Verify that the method 'add' is present in the imported graph, confirming that
        # exported methods are correctly preserved through the round-trip.
        assert "add" in meth_names
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_members::post_2
        # Check that the method 'validateInput' exists in the imported graph, validating
        # that all class methods survive the export-import cycle.
        assert "validateInput" in meth_names

        # Attributes
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_members::post_3
        # Confirm that all original methods from the exported graph are present in the
        # imported version, ensuring complete method preservation.
        assert "AttributeNode" in engine.children
        attr_names = [e.node.name for e in engine.children["AttributeNode"].values()]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_members::post_4
        # Verify that the attribute 'precision' exists in the imported graph, ensuring
        # that class attributes are also faithfully maintained through the round-trip.
        assert "precision" in attr_names

    def test_import_preserves_enum_values(self):
        """Export → import round-trip preserves enum values."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        calc = restored.entries["calc"]
        enum_entries = list(calc.children["EnumNode"].values())
        op_entry = enum_entries[0]

        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_enum_values::post_0
        # Confirms that the imported code contains an enum with named values,
        # establishing that the export-import process preserves the overall structure of
        # enum types.
        assert "EnumValueNode" in op_entry.children
        val_names = [e.node.name for e in op_entry.children["EnumValueNode"].values()]
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_enum_values::post_1
        # Checks that 'ADD' is included in the imported enum values, verifying that this
        # specific value is not lost or altered during the export and import cycle.
        assert "ADD" in val_names
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_enum_values::post_2
        # Verifies that 'SUBTRACT' is present in the list of enum value names after
        # import, ensuring that all original enum values survive the export-import round
        # trip.
        assert "SUBTRACT" in val_names

    def test_import_preserves_relationships(self):
        """Export → import round-trip preserves relationship arrows."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        calc = restored.entries["calc"]
        cls_entries = list(calc.children["ClassNode"].values())
        engine = next(e for e in cls_entries if e.node.name == "CalculatorEngine")

        # REALIZES
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_relationships::post_0
        # Verifies that a 'REALIZES' relationship exists in the engine's references,
        # ensuring that implementation relationships are correctly preserved through the
        # export-import round trip.
        assert any(r[0] == "REALIZES" for r in engine.references)

        # DEPENDS_ON
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_relationships::post_1
        # Verifies that a 'DEPENDS_ON' relationship exists in the engine's references,
        # confirming that dependency relationships are accurately maintained after the
        # export-import round trip.
        assert any(r[0] == "DEPENDS_ON" for r in engine.references)

        # INHERITS_FROM in ui namespace
        ui = restored.entries["ui"]
        ui_cls = list(ui.children["ClassNode"].values())
        calc_win = next(e for e in ui_cls if e.node.name == "CalculatorWindow")
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_preserves_relationships::post_2
        # Verifies that an 'INHERITS_FROM' relationship exists in the target component's
        # references, ensuring that inheritance relationships are properly restored
        # after the export-import round trip.
        assert any(r[0] == "INHERITS_FROM" for r in calc_win.references)

    def test_import_serializes_to_json(self):
        """Export → import round-trip, then serialize the restored graph to JSON.

        Saves ``design_graph_puml.json`` alongside the original
        ``design_graph.json`` fixture so the two can be diffed to see
        exactly what the PlantUML round-trip preserves and what it loses."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        json_data = restored.serialize(fields="all")
        out_path = DATA_DIR / "design_graph_puml.json"
        out_path.write_text(
            json.dumps(json_data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Verify the file was written and is valid JSON
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_serializes_to_json::post_0
        # Verifies that the JSON output file was successfully created on disk, ensuring
        # the serialization step completed and wrote data to the expected location.
        assert out_path.exists()
        with open(out_path) as f:
            reloaded = json.load(f)
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_serializes_to_json::post_1
        # Asserts that the reloaded data is a list, verifying that the import process
        # returned data in the expected container format for further processing.
        assert isinstance(reloaded, list)
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_serializes_to_json::post_2
        # Confirms that the reloaded list is not empty, ensuring that the export-import
        # round-trip actually transferred graph elements and did not result in a loss of
        # content.
        assert len(reloaded) > 0

        # Every entry should have a type key
        for entry in reloaded:
            # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_import_serializes_to_json::post_3
            # Checks that each element in the reloaded data contains a 'type' field,
            # confirming that the import and serialization preserved the structural
            # metadata required by the graph model.
            assert "type" in entry

    # ── PNG compilation ────────────────────────────────────────────────

    @pytest.mark.skipif(not _plantuml_available(), reason="PlantUML jar or java not available")
    def test_compile_to_png(self):
        """Compile the exported PlantUML to a PNG diagram."""
        puml = export_plantuml(self.graph)
        out_path = FIXTURE_DIR / "plantuml_integration.png"
        _compile_plantuml_to_png(puml, out_path)
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_compile_to_png::post_0
        # Checks that the output PNG file actually exists on disk, confirming that the
        # compilation process completed and produced a file at the expected location.
        assert out_path.exists()
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_compile_to_png::post_1
        # Verifies that the output PNG file is larger than 1000 bytes, ensuring the
        # generated diagram is not empty or trivial, which confirms a meaningful diagram
        # was produced.
        assert out_path.stat().st_size > 1000  # non-trivial PNG

    @pytest.mark.skipif(not _plantuml_available(), reason="PlantUML jar or java not available")
    def test_roundtrip_compile_to_png(self):
        """Export → import → re-export, then compile the round-tripped diagram."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)
        puml2 = export_plantuml(restored)
        out_path = FIXTURE_DIR / "plantuml_roundtrip.png"
        _compile_plantuml_to_png(puml2, out_path)
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_roundtrip_compile_to_png::post_0
        # Verifies that the generated PNG file exists on disk, confirming that the
        # compile step completed without file‑system errors.
        assert out_path.exists()
        # codegraph:test-desc test_plantuml_integration.TestPlantUMLIntegration.test_roundtrip_compile_to_png::post_1
        # Checks that the PNG file is larger than 1000 bytes, ensuring the compiled
        # output is meaningful and not an empty or corrupted image.
        assert out_path.stat().st_size > 1000  # non-trivial PNG


# ── Helpers ────────────────────────────────────────────────────────────────


def _compile_plantuml_to_png(puml: str, output_path: Path) -> None:
    """Compile PlantUML text to a PNG file."""
    plantuml_jar = Path(__file__).resolve().parent.parent / "tools" / "plantuml.jar"
    result = subprocess.run(
        ["java", "-jar", str(plantuml_jar),
         "-pipe", "-tpng", "-charset", "UTF-8"],
        input=puml.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, f"PlantUML failed: {result.stderr.decode()}"
    output_path.write_bytes(result.stdout)