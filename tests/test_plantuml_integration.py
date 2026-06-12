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
from codegraph.plantuml import export_plantuml, import_plantuml

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
        assert puml.startswith("@startuml")
        assert puml.endswith("@enduml")

        # Save the .puml file
        out_path = FIXTURE_DIR / "plantuml_integration.puml"
        out_path.write_text(puml, encoding="utf-8")

        # Namespaces
        assert 'package "calc"' in puml
        assert 'package "ui"' in puml

        # Classes
        assert "CalculatorEngine" in puml
        assert "CalculatorResult" in puml
        assert "BaseWindow" in puml
        assert "CalculatorWindow" in puml

        # Interface
        assert "ICalculator" in puml

        # Enum
        assert "Operation" in puml

        # Members inside classes
        assert "+add" in puml
        assert "+validateInput" in puml
        assert "precision" in puml

        # Enum values
        assert "ADD" in puml
        assert "SUBTRACT" in puml

        # Relationships
        assert "realizes" in puml
        assert "inherits_from" in puml

    # ── Import ─────────────────────────────────────────────────────────

    def test_import_restores_core_structure(self):
        """Export → import round-trip preserves core structure."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

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
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

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
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

        calc = restored.entries["calc"]
        enum_entries = list(calc.children["EnumNode"].values())
        op_entry = enum_entries[0]

        assert "EnumValueNode" in op_entry.children
        val_names = [e.node.name for e in op_entry.children["EnumValueNode"].values()]
        assert "ADD" in val_names
        assert "SUBTRACT" in val_names

    def test_import_preserves_relationships(self):
        """Export → import round-trip preserves relationship arrows."""
        puml = export_plantuml(self.graph)
        restored = import_plantuml(puml)

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
            json.dumps(json_data, indent=2),
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

    # ── PNG compilation ────────────────────────────────────────────────

    @pytest.mark.skipif(not _plantuml_available(), reason="PlantUML jar or java not available")
    def test_compile_to_png(self):
        """Compile the exported PlantUML to a PNG diagram."""
        puml = export_plantuml(self.graph)
        out_path = FIXTURE_DIR / "plantuml_integration.png"
        _compile_plantuml_to_png(puml, out_path)
        assert out_path.exists()
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