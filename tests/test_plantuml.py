"""Tests for PlantUML export.

Covers export_plantuml, node type mapping, relationship mapping,
member formatting, stereotype mapping, PNG compilation, and error handling.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode, FunctionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.plantuml import (
    export_plantuml,
    PlantUMLExporter,
    _sanitize_alias,
    _visibility_prefix,
)

# ── PNG compilation constants ────────────────────────────────────────────

PLANTUML_JAR = Path(__file__).resolve().parent.parent / "tools" / "plantuml.jar"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"


def _plantuml_available() -> bool:
    """Check whether the PlantUML jar exists and java is on PATH."""
    if not PLANTUML_JAR.is_file():
        return False
    try:
        subprocess.run(["java", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_simple_graph() -> LayerGraph:
    """Build a small LayerGraph with a namespace, class, and method."""
    ns = NamespaceNode(name="calc", kind="namespace", qualified_name="calc",
                       tags=["design"])
    cls = ClassNode(name="CalculatorEngine", kind="class",
                    qualified_name="calc::CalculatorEngine",
                    tags=["design"], visibility="public",
                    brief_description="Core calculator engine.")
    iface = InterfaceNode(name="ICalculator", kind="interface",
                          qualified_name="calc::ICalculator",
                          tags=["design"], visibility="public",
                          brief_description="Calculator interface.")
    meth = MethodNode(name="add", kind="method",
                      qualified_name="calc::CalculatorEngine::add",
                      tags=["design"], visibility="public",
                      type_signature="int",
                      argsstring="(int a, int b)")
    attr = AttributeNode(name="precision", kind="attribute",
                         qualified_name="calc::CalculatorEngine::precision",
                         tags=["design"], visibility="private",
                         type_signature="int")
    op_enum = EnumNode(name="Operation", kind="enum",
                       qualified_name="calc::Operation",
                       tags=["design"], visibility="public")
    add_val = EnumValueNode(name="ADD", kind="enumvalue",
                            qualified_name="calc::Operation::ADD",
                            tags=["design"])
    func = FunctionNode(name="formatResult", kind="function",
                        qualified_name="calc::formatResult",
                        tags=["design"], visibility="public",
                        type_signature="string",
                        argsstring="(double result)")

    # Build entries
    meth_entry = CompositeEntry(node=meth)
    attr_entry = CompositeEntry(node=attr)
    add_val_entry = CompositeEntry(node=add_val)

    cls_entry = CompositeEntry(
        node=cls,
        children={"MethodNode": {"calc::CalculatorEngine::add": meth_entry},
                  "AttributeNode": {"calc::CalculatorEngine::precision": attr_entry}},
        references=[("REALIZES", "calc::ICalculator", "InterfaceNode")]
    )
    iface_entry = CompositeEntry(node=iface)
    op_entry = CompositeEntry(
        node=op_enum,
        children={"EnumValueNode": {"calc::Operation::ADD": add_val_entry}},
    )
    func_entry = CompositeEntry(node=func)

    ns_entry = CompositeEntry(
        node=ns,
        children={
            "ClassNode": {"calc::CalculatorEngine": cls_entry},
            "InterfaceNode": {"calc::ICalculator": iface_entry},
            "EnumNode": {"calc::Operation": op_entry},
            "FunctionNode": {"calc::formatResult": func_entry},
        },
    )

    return LayerGraph(tags=frozenset({"design"}), entries={"calc": ns_entry})


# ── _sanitize_alias ────────────────────────────────────────────────────────


class TestSanitizeAlias:
    def test_replaces_double_colon(self):
        assert _sanitize_alias("calc::CalculatorEngine") == "calc__CalculatorEngine"

    def test_replaces_spaces(self):
        assert _sanitize_alias("my class") == "my_class"

    def test_replaces_dots(self):
        assert _sanitize_alias("my.module") == "my_module"

    def test_plain_name(self):
        assert _sanitize_alias("CalculatorEngine") == "CalculatorEngine"


# ── _visibility_prefix ─────────────────────────────────────────────────────


class TestVisibilityPrefix:
    def test_public(self):
        assert _visibility_prefix("public") == "+"

    def test_private(self):
        assert _visibility_prefix("private") == "-"

    def test_protected(self):
        assert _visibility_prefix("protected") == "#"

    def test_empty(self):
        assert _visibility_prefix("") == "+"

    def test_unknown(self):
        assert _visibility_prefix("unknown") == "+"


# ── Export ──────────────────────────────────────────────────────────────────


class TestExportBasicStructure:
    """Tests for PlantUML export basic structure."""

    def test_startuml_enduml_wrappers(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert puml.startswith("@startuml")
        assert puml.endswith("@enduml")

    def test_namespace_as_package(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert 'package "calc"' in puml

    def test_class_with_alias(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert 'class "CalculatorEngine"' in puml
        assert "calc__CalculatorEngine" in puml

    def test_interface(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert 'interface "ICalculator"' in puml

    def test_enum(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert 'enum "Operation"' in puml

    def test_function_as_stereotype(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "<<function>>" in puml

    def test_method_inside_class(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "+add" in puml

    def test_attribute_inside_class(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "precision" in puml

    def test_enum_value_inside_enum(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "ADD" in puml

    def test_no_metadata_note_by_default(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "note as N_metadata" not in puml


class TestExportRelationships:
    """Tests for relationship arrow export."""

    def test_realizes_arrow(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "..|>" in puml or "realizes" in puml

    def test_depends_on_arrow(self):
        """DEPENDS_ON relationships should produce ..> arrows."""
        ns = NamespaceNode(name="ns", kind="namespace", qualified_name="ns", tags=["design"])
        cls_a = ClassNode(name="A", kind="class", qualified_name="ns::A", tags=["design"])
        cls_b = ClassNode(name="B", kind="class", qualified_name="ns::B", tags=["design"])
        ns_entry = CompositeEntry(
            node=ns,
            children={
                "ClassNode": {
                    "ns::A": CompositeEntry(node=cls_a),
                    "ns::B": CompositeEntry(node=cls_b),
                },
            },
        )
        a_entry = ns_entry.children["ClassNode"]["ns::A"]
        a_entry.references.append(("DEPENDS_ON", "ns::B", "ClassNode"))

        graph = LayerGraph(tags=frozenset({"design"}), entries={"ns": ns_entry})
        puml = export_plantuml(graph)
        assert "depends_on" in puml


# ── Convenience functions ──────────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_export_plantuml_function(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "@startuml" in puml

    def test_exporter_class_direct(self):
        graph = _make_simple_graph()
        exporter = PlantUMLExporter(graph, fields="all")
        puml = exporter.export()
        assert "@startuml" in puml


# ── PNG compilation ──────────────────────────────────────────────────────


@pytest.mark.skipif(not _plantuml_available(), reason="PlantUML jar or java not available")
class TestPngCompilation:
    """Tests that export PlantUML, compile it to PNG, and save to unit_test_data."""

    @classmethod
    def setup_class(cls):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def test_simple_graph_to_png(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_simple_graph.png"
        assert _compile_plantuml_to_png(puml, output)

    def test_empty_graph_to_png(self):
        graph = LayerGraph(tags=frozenset({"design"}))
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_empty_graph.png"
        assert _compile_plantuml_to_png(puml, output)

    def test_inheritance_to_png(self):
        base = ClassNode(name="Animal", kind="class",
                        qualified_name="ns::Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class",
                           qualified_name="ns::Dog", tags=["design"])
        base_entry = CompositeEntry(node=base)
        derived_entry = CompositeEntry(
            node=derived,
            references=[("INHERITS_FROM", "ns::Animal", "ClassNode")],
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={
            "ns::Animal": base_entry,
            "ns::Dog": derived_entry,
        })
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_inheritance.png"
        assert _compile_plantuml_to_png(puml, output)

    def test_enum_to_png(self):
        op_enum = EnumNode(name="Operation", kind="enum",
                          qualified_name="calc::Operation", tags=["design"])
        add_val = EnumValueNode(name="ADD", kind="enumvalue",
                               qualified_name="calc::Operation::ADD", tags=["design"])
        sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue",
                               qualified_name="calc::Operation::SUBTRACT", tags=["design"])
        op_entry = CompositeEntry(
            node=op_enum,
            children={"EnumValueNode": {
                "calc::Operation::ADD": CompositeEntry(node=add_val),
                "calc::Operation::SUBTRACT": CompositeEntry(node=sub_val),
            }},
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={"calc::Operation": op_entry})
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_enum.png"
        assert _compile_plantuml_to_png(puml, output)

    def test_namespace_with_classes_to_png(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_namespace_with_classes.png"
        assert _compile_plantuml_to_png(puml, output)


def _compile_plantuml_to_png(puml: str, output_path: Path) -> bool:
    """Compile PlantUML text to a PNG file."""
    if not _plantuml_available():
        return False
    try:
        result = subprocess.run(
            ["java", "-jar", str(PLANTUML_JAR),
             "-pipe", "-tpng", "-charset", "UTF-8"],
            input=puml.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        output_path.write_bytes(result.stdout)
        return output_path.exists() and output_path.stat().st_size > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_graph_export(self):
        graph = LayerGraph(tags=frozenset({"design"}))
        puml = export_plantuml(graph)
        assert "@startuml" in puml
        assert "@enduml" in puml

    def test_sanitize_alias_idempotent(self):
        name = "calc::CalculatorEngine"
        alias = _sanitize_alias(name)
        assert _sanitize_alias(alias) == alias