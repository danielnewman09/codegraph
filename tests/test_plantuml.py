"""Tests for PlantUML export and import.

Covers export_plantuml, import_plantuml, node type mapping,
relationship mapping, member formatting, stereotype mapping,
PNG compilation, nesting-based qualified name derivation, and
round-trip export→import fidelity.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.plantuml import (
    export_plantuml,
    import_plantuml,
    PlantUMLExporter,
    PlantUMLImporter,
    PlantUMLParseError,
    ParseDiagnostic,
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
                    tags=["design"], visibility="public")
    iface = InterfaceNode(name="ICalculator", kind="interface",
                          qualified_name="calc::ICalculator",
                          tags=["design"], visibility="public")
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
    sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue",
                            qualified_name="calc::Operation::SUBTRACT",
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
    sub_val_entry = CompositeEntry(node=sub_val)

    cls_entry = CompositeEntry(
        node=cls,
        children={"MethodNode": {"calc::CalculatorEngine::add": meth_entry},
                  "AttributeNode": {"calc::CalculatorEngine::precision": attr_entry}},
        references=[("REALIZES", "calc::ICalculator", "InterfaceNode")]
    )
    iface_entry = CompositeEntry(node=iface)
    op_entry = CompositeEntry(
        node=op_enum,
        children={"EnumValueNode": {
            "calc::Operation::ADD": add_val_entry,
            "calc::Operation::SUBTRACT": sub_val_entry,
        }},
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

    def test_round_trip_alias(self):
        """_sanitize_alias on a qualified name should match the exporter alias."""
        name = "calc::CalculatorEngine::add"
        assert _sanitize_alias(name) == "calc__CalculatorEngine__add"


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
        assert "SUBTRACT" in puml

    def test_no_metadata_note_by_default(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "note as N_metadata" not in puml


class TestExportRelationships:
    """Tests for relationship arrow export."""

    def test_realizes_arrow(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "realizes" in puml

    def test_depends_on_arrow(self):
        ns = NamespaceNode(name="ns", kind="namespace",
                           qualified_name="ns", tags=["design"])
        cls_a = ClassNode(name="A", kind="class",
                          qualified_name="ns::A", tags=["design"])
        cls_b = ClassNode(name="B", kind="class",
                          qualified_name="ns::B", tags=["design"])
        a_entry = CompositeEntry(
            node=cls_a,
            references=[("DEPENDS_ON", "ns::B", "ClassNode")],
        )
        b_entry = CompositeEntry(node=cls_b)
        ns_entry = CompositeEntry(
            node=ns,
            children={"ClassNode": {
                "ns::A": a_entry,
                "ns::B": b_entry,
            }},
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={"ns": ns_entry})
        puml = export_plantuml(graph)
        assert "depends_on" in puml


# ── Import ──────────────────────────────────────────────────────────────────


class TestImportBasicStructure:
    """Tests for PlantUML import basic structure."""

    def test_import_empty_diagram(self):
        puml = "@startuml\n@enduml"
        graph = import_plantuml(puml)
        assert isinstance(graph, LayerGraph)
        assert len(graph.entries) == 0

    def test_import_package(self):
        puml = '@startuml\npackage "calc" {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "calc" in graph.entries
        node = graph.entries["calc"].node
        assert isinstance(node, NamespaceNode)
        assert node.name == "calc"
        assert node.qualified_name == "calc"

    def test_import_class(self):
        puml = '@startuml\nclass "Engine" {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "Engine" in graph.entries
        node = graph.entries["Engine"].node
        assert isinstance(node, ClassNode)
        assert node.name == "Engine"
        assert node.qualified_name == "Engine"

    def test_import_interface(self):
        puml = '@startuml\ninterface "IWidget" {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "IWidget" in graph.entries
        node = graph.entries["IWidget"].node
        assert isinstance(node, InterfaceNode)

    def test_import_enum(self):
        puml = '@startuml\nenum "Color" {\n  RED\n  BLUE\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "Color" in graph.entries
        node = graph.entries["Color"].node
        assert isinstance(node, EnumNode)
        # Enum values should be children
        assert "EnumValueNode" in graph.entries["Color"].children
        vals = list(graph.entries["Color"].children["EnumValueNode"].values())
        assert len(vals) == 2
        assert isinstance(vals[0].node, EnumValueNode)

    def test_import_note_as_file(self):
        puml = '@startuml\nnote "widget.h" as widget_h\n@enduml'
        graph = import_plantuml(puml)
        assert "widget.h" in graph.entries
        node = graph.entries["widget.h"].node
        assert isinstance(node, FileNode)

    def test_import_stereotype_function(self):
        puml = '@startuml\nclass "formatResult" <<function>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "formatResult" in graph.entries
        node = graph.entries["formatResult"].node
        assert isinstance(node, FunctionNode)

    def test_import_stereotype_union(self):
        puml = '@startuml\nclass "Data" <<union>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "Data" in graph.entries
        node = graph.entries["Data"].node
        assert type(node).__name__ == "UnionNode"

    def test_import_stereotype_module(self):
        puml = '@startuml\npackage "mymod" <<module>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "mymod" in graph.entries
        node = graph.entries["mymod"].node
        assert type(node).__name__ == "ModuleNode"


class TestImportNesting:
    """Tests for nesting-based qualified name derivation."""

    def test_class_inside_package(self):
        puml = '@startuml\npackage "calc" {\n  class "Engine" {\n  }\n}\n@enduml'
        graph = import_plantuml(puml)
        # Class should be a child of the package
        assert "calc" in graph.entries
        pkg = graph.entries["calc"]
        assert "ClassNode" in pkg.children
        cls_entries = pkg.children["ClassNode"]
        assert "calc::Engine" in cls_entries
        cls = cls_entries["calc::Engine"].node
        assert cls.qualified_name == "calc::Engine"
        assert cls.name == "Engine"

    def test_method_inside_class(self):
        puml = (
            '@startuml\n'
            'class "Engine" {\n'
            '  +add(int a, int b): int\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        assert "Engine" in graph.entries
        cls = graph.entries["Engine"]
        assert "MethodNode" in cls.children
        meth = list(cls.children["MethodNode"].values())[0].node
        assert isinstance(meth, MethodNode)
        assert meth.name == "add"
        assert meth.qualified_name == "Engine::add"
        assert meth.type_signature == "int"
        assert meth.argsstring == "(int a, int b)"
        assert meth.visibility == "public"

    def test_attribute_inside_class(self):
        puml = (
            '@startuml\n'
            'class "Engine" {\n'
            '  -precision: int\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        cls = graph.entries["Engine"]
        assert "AttributeNode" in cls.children
        attr = list(cls.children["AttributeNode"].values())[0].node
        assert isinstance(attr, AttributeNode)
        assert attr.name == "precision"
        assert attr.type_signature == "int"
        assert attr.visibility == "private"

    def test_enum_values_inside_enum(self):
        puml = (
            '@startuml\n'
            'enum "Op" {\n'
            '  ADD\n'
            '  SUBTRACT\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        enum_entry = graph.entries["Op"]
        vals = enum_entry.children["EnumValueNode"]
        assert "Op::ADD" in vals
        assert "Op::SUBTRACT" in vals
        assert vals["Op::ADD"].node.name == "ADD"
        assert vals["Op::SUBTRACT"].node.name == "SUBTRACT"

    def test_deep_nesting(self):
        puml = (
            '@startuml\n'
            'package "outer" {\n'
            '  package "inner" {\n'
            '    class "Widget" {\n'
            '    }\n'
            '  }\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        outer = graph.entries["outer"]
        inner = outer.children["NamespaceNode"]["outer::inner"]
        widget = inner.children["ClassNode"]["outer::inner::Widget"]
        assert widget.node.qualified_name == "outer::inner::Widget"


class TestImportArrows:
    """Tests for relationship arrow import and resolution."""

    def test_inheritance_arrow(self):
        puml = (
            '@startuml\n'
            'class "Animal" {\n}\n'
            'class "Dog" {\n}\n'
            'Dog <|-- Animal : inherits_from\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        dog = graph.entries["Dog"]
        assert len(dog.references) >= 1
        rel = dog.references[0]
        assert rel[0] == "INHERITS_FROM"
        assert rel[1] == "Animal"

    def test_realizes_arrow(self):
        puml = (
            '@startuml\n'
            'class "Engine" {\n}\n'
            'interface "IEngine" {\n}\n'
            'Engine ..|> IEngine : realizes\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        engine = graph.entries["Engine"]
        assert any(r[0] == "REALIZES" for r in engine.references)

    def test_depends_on_arrow(self):
        puml = (
            '@startuml\n'
            'class "A" {\n}\n'
            'class "B" {\n}\n'
            'A ..> B : depends_on\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        a = graph.entries["A"]
        assert any(r[0] == "DEPENDS_ON" and r[1] == "B" for r in a.references)

    def test_arrow_label_overrides_default(self):
        """An arrow with a label should use the label-based rel type,
        not the arrow-symbol default."""
        puml = (
            '@startuml\n'
            'class "A" {\n}\n'
            'class "B" {\n}\n'
            'A ..> B : invokes\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        a = graph.entries["A"]
        assert any(r[0] == "INVOKES" for r in a.references)

    def test_arrow_without_label_uses_default(self):
        """An arrow without a label should use the arrow-symbol default."""
        puml = (
            '@startuml\n'
            'class "A" {\n}\n'
            'class "B" {\n}\n'
            'A ..> B\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        a = graph.entries["A"]
        assert any(r[0] == "DEPENDS_ON" for r in a.references)

    def test_unresolvable_arrow_skipped(self):
        """Arrows referencing unknown aliases should be silently skipped."""
        puml = (
            '@startuml\n'
            'class "A" {\n}\n'
            'A ..> nonexistent : depends_on\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        a = graph.entries["A"]
        assert len(a.references) == 0

    def test_nested_class_arrow(self):
        """Arrows between nested classes use derived aliases."""
        puml = (
            '@startuml\n'
            'package "ns" {\n'
            '  class "A" {\n  }\n'
            '  class "B" {\n  }\n'
            '}\n'
            'ns__A ..> ns__B : depends_on\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        ns = graph.entries["ns"]
        a = ns.children["ClassNode"]["ns::A"]
        assert any(r[0] == "DEPENDS_ON" and r[1] == "ns::B"
                    for r in a.references)


class TestImportTags:
    """Tests for tag application on imported nodes."""

    def test_default_tags(self):
        puml = '@startuml\nclass "A" {\n}\n@enduml'
        graph = import_plantuml(puml)
        node = graph.entries["A"].node
        assert "design" in node.tags

    def test_custom_tags(self):
        puml = '@startuml\nclass "A" {\n}\n@enduml'
        graph = import_plantuml(puml, tags=frozenset({"as-built"}))
        node = graph.entries["A"].node
        assert "as-built" in node.tags


class TestImportNoAliasParsing:
    """Tests verifying that import works without relying on `as alias` text."""

    def test_import_without_as_alias(self):
        """Element without `as alias` should still be importable."""
        puml = (
            '@startuml\n'
            'package "calc" {\n'
            '  class "Engine" {\n'
            '  }\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        assert "calc" in graph.entries
        pkg = graph.entries["calc"]
        assert "ClassNode" in pkg.children
        cls = list(pkg.children["ClassNode"].values())[0].node
        assert cls.qualified_name == "calc::Engine"

    def test_import_with_as_alias_ignored(self):
        """`as alias` is present but ignored — qname is derived from nesting."""
        puml = (
            '@startuml\n'
            'package "calc" as my_calc {\n'
            '  class "Engine" as my_engine {\n'
            '  }\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        pkg = graph.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0].node
        # Qualified name is derived from nesting, not from alias
        assert cls.qualified_name == "calc::Engine"


# ── Export → Import round-trip ───────────────────────────────────────────────


class TestExportImportRoundTrip:
    """Tests for export→import round-trip fidelity.

    Full round-trip is not expected (metadata is lost), but the core
    structure (namespaces, compounds, members, relationships) should
    survive.
    """

    def test_round_trip_simple_graph_structure(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        # Namespace preserved
        assert "calc" in restored.entries

        # Class inside namespace
        pkg = restored.entries["calc"]
        assert "ClassNode" in pkg.children
        cls_entries = list(pkg.children["ClassNode"].values())
        assert any(e.node.name == "CalculatorEngine" for e in cls_entries)

        # Interface preserved
        assert "InterfaceNode" in pkg.children

        # Enum preserved
        assert "EnumNode" in pkg.children

        # Function preserved
        assert "FunctionNode" in pkg.children

    def test_round_trip_members(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        assert "MethodNode" in cls.children
        assert "AttributeNode" in cls.children

    def test_round_trip_enum_values(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        enum_entry = list(pkg.children["EnumNode"].values())[0]
        assert "EnumValueNode" in enum_entry.children

    def test_round_trip_relationships(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        # REALIZES reference should be preserved
        assert any(r[0] == "REALIZES" for r in cls.references)

    def test_round_trip_inheritance(self):
        base = ClassNode(name="Animal", kind="class",
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class",
                           qualified_name="Dog", tags=["design"])
        base_entry = CompositeEntry(node=base)
        derived_entry = CompositeEntry(
            node=derived,
            references=[("INHERITS_FROM", "Animal", "ClassNode")],
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={
            "Animal": base_entry,
            "Dog": derived_entry,
        })
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        dog = restored.entries["Dog"]
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)


# ── Convenience functions ──────────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_export_plantuml_function(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        assert "@startuml" in puml

    def test_import_plantuml_function(self):
        puml = '@startuml\npackage "x" {\n}\n@enduml'
        graph = import_plantuml(puml)
        assert "x" in graph.entries

    def test_exporter_class_direct(self):
        graph = _make_simple_graph()
        exporter = PlantUMLExporter(graph, fields="all")
        puml = exporter.export()
        assert "@startuml" in puml

    def test_importer_class_direct(self):
        puml = '@startuml\npackage "x" {\n}\n@enduml'
        importer = PlantUMLImporter(tags=frozenset({"as-built"}))
        graph = importer.import_plantuml(puml)
        assert "x" in graph.entries
        assert graph.tags == frozenset({"as-built"})


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
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class",
                           qualified_name="Dog", tags=["design"])
        base_entry = CompositeEntry(node=base)
        derived_entry = CompositeEntry(
            node=derived,
            references=[("INHERITS_FROM", "Animal", "ClassNode")],
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={
            "Animal": base_entry,
            "Dog": derived_entry,
        })
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_inheritance.png"
        assert _compile_plantuml_to_png(puml, output)

    def test_enum_to_png(self):
        op_enum = EnumNode(name="Operation", kind="enum",
                          qualified_name="Operation", tags=["design"])
        add_val = EnumValueNode(name="ADD", kind="enumvalue",
                               qualified_name="Operation::ADD", tags=["design"])
        sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue",
                               qualified_name="Operation::SUBTRACT", tags=["design"])
        op_entry = CompositeEntry(
            node=op_enum,
            children={"EnumValueNode": {
                "Operation::ADD": CompositeEntry(node=add_val),
                "Operation::SUBTRACT": CompositeEntry(node=sub_val),
            }},
        )
        graph = LayerGraph(tags=frozenset({"design"}),
                          entries={"Operation": op_entry})
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

    def test_empty_graph_import(self):
        graph = import_plantuml("@startuml\n@enduml")
        assert isinstance(graph, LayerGraph)
        assert len(graph.entries) == 0

    def test_sanitize_alias_idempotent(self):
        name = "calc::CalculatorEngine"
        alias = _sanitize_alias(name)
        assert _sanitize_alias(alias) == alias

    def test_import_skips_skinparam(self):
        puml = (
            '@startuml\n'
            'skinparam classAttributeIconSize 0\n'
            'class "A" {\n}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        assert "A" in graph.entries

    def test_import_skips_comments(self):
        puml = (
            '@startuml\n'
            "' this is a comment\n"
            'class "A" {\n}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        assert "A" in graph.entries

    def test_import_method_no_return_type(self):
        puml = (
            '@startuml\n'
            'class "A" {\n'
            '  +doSomething()\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        cls = graph.entries["A"]
        meth = list(cls.children["MethodNode"].values())[0].node
        assert meth.name == "doSomething"
        assert meth.type_signature == ""

    def test_import_attribute_no_type(self):
        puml = (
            '@startuml\n'
            'class "A" {\n'
            '  +count\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        cls = graph.entries["A"]
        attr = list(cls.children["AttributeNode"].values())[0].node
        assert attr.name == "count"
        assert attr.type_signature == ""


# ── Diagnostics ────────────────────────────────────────────────────────────


class TestDiagnostics:
    """Tests for parse diagnostics and strict-mode error reporting."""

    def test_unmatched_closing_brace(self):
        """Extra '}' with nothing on the stack → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\nclass "A" {\n}\n}\n@enduml')
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) == 1
        assert "Unexpected '}'" in errors[0].message

    def test_unclosed_element(self):
        """Open brace never closed → warning diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\npackage "x" {\n  class "A" {\n@enduml')
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unclosed = [w for w in warnings if "Unclosed" in w.message]
        assert len(unclosed) == 2  # both package and class are unclosed

    def test_dangling_arrow_source(self):
        """Arrow with unknown source alias → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n}\n'
            'nonexistent ..> A : depends_on\n@enduml'
        )
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) == 1
        assert "source alias" in errors[0].message.lower()
        assert "nonexistent" in errors[0].message

    def test_dangling_arrow_target(self):
        """Arrow with unknown target alias → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n}\n'
            'A ..> nowhere : depends_on\n@enduml'
        )
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) == 1
        assert "target alias" in errors[0].message.lower()
        assert "nowhere" in errors[0].message

    def test_unknown_stereotype(self):
        """Unknown stereotype → warning diagnostic, falls back to default."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "X" <<mystery>> {\n}\n@enduml'
        )
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        stereo_warns = [w for w in warnings if "stereotype" in w.message.lower()]
        assert len(stereo_warns) == 1
        assert "mystery" in stereo_warns[0].message
        # Falls back to ClassNode
        assert "X" in graph.entries
        assert isinstance(graph.entries["X"].node, ClassNode)

    def test_unknown_arrow_label(self):
        """Unknown arrow label → warning, falls back to arrow default."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n}\nclass "B" {\n}\n'
            'A ..> B : made_up_relation\n@enduml'
        )
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        label_warns = [w for w in warnings if "label" in w.message.lower()]
        assert len(label_warns) == 1
        assert "made_up_relation" in label_warns[0].message
        # Falls back to DEPENDS_ON (..> default)
        assert any(r[0] == "DEPENDS_ON" for r in graph.entries["A"].references)

    def test_unrecognized_line_inside_body(self):
        """Unrecognized content inside an element → warning with context."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n  ???\n}\n@enduml'
        )
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unrec = [w for w in warnings if "Unrecognized" in w.message]
        assert len(unrec) >= 1
        assert "ClassNode" in unrec[0].message  # says which parent

    def test_unrecognized_line_at_root(self):
        """Unrecognized content at root level → warning."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\n???\n@enduml')
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unrec = [w for w in warnings if "Unrecognized" in w.message]
        assert len(unrec) >= 1

    def test_valid_diagram_has_no_diagnostics(self):
        """A well-formed diagram produces zero diagnostics."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\npackage "ns" {\n'
            '  class "A" {\n    +x: int\n  }\n}\n@enduml'
        )
        assert len(importer.diagnostics) == 0

    def test_strict_mode_raises_on_errors(self):
        """strict=True raises PlantUMLParseError on error diagnostics."""
        with pytest.raises(PlantUMLParseError) as exc_info:
            import_plantuml(
                '@startuml\nclass "A" {\n}\n}\n@enduml',
                strict=True,
            )
        assert len(exc_info.value.diagnostics) >= 1
        assert any("Unexpected" in d.message for d in exc_info.value.diagnostics)

    def test_strict_mode_ok_on_warnings_only(self):
        """strict=True does NOT raise when only warnings exist."""
        importer = PlantUMLImporter(strict=True)
        graph = importer.import_plantuml(
            '@startuml\nclass "X" <<mystery>> {\n}\n@enduml'
        )
        # Unknown stereotype is a warning, not an error
        assert any(d.severity == "warning" for d in importer.diagnostics)
        assert "X" in graph.entries  # graph still returned

    def test_strict_mode_dangling_arrow(self):
        """strict=True raises on unresolvable arrow."""
        with pytest.raises(PlantUMLParseError) as exc_info:
            import_plantuml(
                '@startuml\nclass "A" {\n}\n'
                'A ..> nowhere : depends_on\n@enduml',
                strict=True,
            )
        assert any("target alias" in d.message.lower()
                    for d in exc_info.value.diagnostics)

    def test_convenience_strict_param(self):
        """import_plantuml(text, strict=True) forwards to importer."""
        with pytest.raises(PlantUMLParseError):
            import_plantuml(
                '@startuml\nclass {\n}\n@enduml',
                strict=True,
            )

    def test_diagnostic_line_numbers(self):
        """Diagnostics include accurate 1-based line numbers."""
        importer = PlantUMLImporter()
        importer.import_plantuml(
            '@startuml\n'          # 1
            'class "A" {\n'        # 2
            '}\n'                  # 3
            '}\n'                  # 4 — unmatched
            '@enduml'              # 5
        )
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) == 1
        assert errors[0].line == 4

    def test_parse_diagnostic_str(self):
        """ParseDiagnostic has a useful string representation."""
        d = ParseDiagnostic(line=7, severity="error",
                            message="Unexpected '}'")
        s = str(d)
        assert "7" in s
        assert "error" in s
        assert "Unexpected" in s

    def test_parse_error_message(self):
        """PlantUMLParseError message lists all diagnostics."""
        diags = [
            ParseDiagnostic(line=3, severity="error",
                            message="Arrow target 'x' not found"),
            ParseDiagnostic(line=5, severity="error",
                            message="Unexpected '}'"),
        ]
        err = PlantUMLParseError(diags)
        msg = str(err)
        assert "line 3" in msg
        assert "line 5" in msg
        assert "Arrow target" in msg
        assert "Unexpected" in msg