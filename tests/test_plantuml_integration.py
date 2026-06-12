"""Integration test: full Calculator graph → PlantUML → PNG.

Builds the complete Calculator graph from ``design_graph.json``, exports it
to PlantUML, compiles the diagram to PNG (if the PlantUML jar is available),
and verifies the exported diagram contains all expected elements.

Saves the following artefacts to ``unit_test_data/``:

- ``plantuml_integration.puml`` — the exported PlantUML source
- ``plantuml_integration.png`` — the compiled diagram (requires PlantUML jar)

Requires Neo4j for the initial ``to_neo4j()`` call.
PlantUML PNG compilation is skipped if ``tools/plantuml.jar`` is absent.
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode
from codegraph.plantuml import export_plantuml

# ── PNG compilation constants ────────────────────────────────────────────

PLANTUML_JAR = Path(__file__).resolve().parent.parent / "tools" / "plantuml.jar"


def _plantuml_available() -> bool:
    """Check whether the PlantUML jar exists and java is on PATH."""
    if not PLANTUML_JAR.is_file():
        return False
    try:
        import subprocess
        subprocess.run(["java", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"


def _count_all_entries(graph: LayerGraph) -> int:
    """Count all CompositeEntry instances across the entire tree."""
    return sum(1 for _ in graph._all_entries())


# ── Full integration: fixture → LayerGraph → PlantUML → PNG ────────────────


class TestPlantUMLIntegration:
    """End-to-end test: load design_graph.json, export to PlantUML,
    compile to PNG, and verify diagram content."""

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

        # No metadata note by default
        assert "note as N_metadata" not in puml

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
        assert "..|>" in puml or "realizes" in puml     # REALIZES
        assert "inherits_from" in puml or "<|--" in puml  # INHERITS_FROM

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
    import subprocess
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