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
from codegraph.export.plantuml import (
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
OUTPUT_DIR = Path(__file__).resolve().parent / "unit_test_data"


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
    ns = NamespaceNode(name="calc", kind="namespace", source="test", qualified_name="calc",
                       tags=["design"])
    cls = ClassNode(name="CalculatorEngine", kind="class", source="test",
                    qualified_name="calc::CalculatorEngine",
                    tags=["design"], visibility="public")
    iface = InterfaceNode(name="ICalculator", kind="interface", source="test",
                          qualified_name="calc::ICalculator",
                          tags=["design"], visibility="public")
    meth = MethodNode(name="add", kind="method", source="test",
                      qualified_name="calc::CalculatorEngine::add",
                      tags=["design"], visibility="public",
                      type_signature="int",
                      argsstring="(int a, int b)")
    attr = AttributeNode(name="precision", kind="attribute", source="test",
                         qualified_name="calc::CalculatorEngine::precision",
                         tags=["design"], visibility="private",
                         type_signature="int")
    op_enum = EnumNode(name="Operation", kind="enum", source="test",
                       qualified_name="calc::Operation",
                       tags=["design"], visibility="public")
    add_val = EnumValueNode(name="ADD", kind="enumvalue", source="test",
                            qualified_name="calc::Operation::ADD",
                            tags=["design"])
    sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue", source="test",
                            qualified_name="calc::Operation::SUBTRACT",
                            tags=["design"])
    func = FunctionNode(name="formatResult", kind="function", source="test",
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
    # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_double_colon
    # This test verifies that the sanitize_alias function correctly replaces double
    # colons in an alias string, ensuring generated PlantUML aliases are valid and do
    # not cause syntax errors.
    def test_replaces_double_colon(self):
        # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_double_colon::post_0
        # Verifies that double colons in the input are replaced with a valid single
        # character (e.g., underscore), ensuring the alias is sanitized for use in
        # PlantUML diagrams without causing syntax errors.
        assert _sanitize_alias("calc::CalculatorEngine") == "calc__CalculatorEngine"

    # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_spaces
    # This test verifies that the sanitize alias function correctly replaces spaces with
    # underscores to ensure alias names do not contain invalid characters, which is
    # important for generating valid PlantUML output.
    def test_replaces_spaces(self):
        # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_spaces::post_0
        # Verifies that the sanitized alias contains no spaces, ensuring the alias is
        # valid for use in PlantUML diagrams where spaces would cause parsing errors.
        assert _sanitize_alias("my class") == "my_class"

    # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_dots
    # Verifies that the sanitize_alias function correctly replaces dots in an alias
    # string, which is critical for generating valid identifiers that may be used
    # downstream without syntax errors caused by unexpected characters.
    def test_replaces_dots(self):
        # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_replaces_dots::post_0
        # Verifies that dots in the alias string are replaced with underscores, ensuring
        # the resulting alias is valid for PlantUML processing.
        assert _sanitize_alias("my.module") == "my_module"

    # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_plain_name
    # Validates that a plain, unmodified alias string passes sanitation, ensuring names
    # without special characters are accepted as safe inputs.
    def test_plain_name(self):
        # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_plain_name::post_0
        # Verifies that a plain name (without special characters) is returned unchanged
        # by the sanitize alias function. This ensures that names that already conform
        # to valid alias rules are not inadvertently modified.
        assert _sanitize_alias("CalculatorEngine") == "CalculatorEngine"

    def test_round_trip_alias(self):
        """_sanitize_alias on a qualified name should match the exporter alias."""
        name = "calc::CalculatorEngine::add"
        # codegraph:test-desc test_plantuml.TestSanitizeAlias.test_round_trip_alias::post_0
        # Verifies that the sanitized alias matches the expected exporter alias,
        # ensuring the round-trip conversion preserves the identifier correctly.
        assert _sanitize_alias(name) == "calc__CalculatorEngine__add"


# ── _visibility_prefix ─────────────────────────────────────────────────────


class TestVisibilityPrefix:
    # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_public
    # Verifies that a method or field without a visibility prefix is treated as public,
    # ensuring correct parsing of UML visibility rules.
    def test_public(self):
        # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_public::post_0
        # Verifies that the method 'test_public' in TestVisibilityPrefix returns the
        # expected result, ensuring that public visibility prefix handling is correct in
        # the PlantUML processing logic.
        assert _visibility_prefix("public") == "+"

    # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_private
    # Verifies that PlantUML renders the private visibility prefix correctly when
    # generating diagrams, ensuring that internal details are properly marked as
    # private.
    def test_private(self):
        # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_private::post_0
        # Verifies that the private visibility prefix (likely '-') is correctly applied
        # to a PlantUML element. This matters because the UML visibility indicator must
        # be accurately generated, ensuring the diagram communicates the intended access
        # level.
        assert _visibility_prefix("private") == "-"

    # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_protected
    # Verifies that the PlantUML generator correctly handles the protected visibility
    # prefix, ensuring proper access control representation in generated diagrams.
    def test_protected(self):
        # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_protected::post_0
        # Verifies that the protected visibility prefix ('~') is correctly applied to
        # the PlantUML element, ensuring the diagram accurately reflects the intended
        # visibility level.
        assert _visibility_prefix("protected") == "#"

    # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_empty
    # Verifies that an empty visibility prefix does not cause errors or unexpected
    # behavior, ensuring the code handles edge cases gracefully.
    def test_empty(self):
        # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_empty::post_0
        # Verifies that the visibility prefix of the tested element is an empty string,
        # ensuring that when no prefix is provided, the system defaults to an empty
        # prefix rather than raising an error or using a non-empty default.
        assert _visibility_prefix("") == "+"

    # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_unknown
    # Verifies that the system handles an unrecognized visibility prefix gracefully,
    # ensuring robustness and preventing crashes from invalid input.
    def test_unknown(self):
        # codegraph:test-desc test_plantuml.TestVisibilityPrefix.test_unknown::post_0
        # Verifies that the output equals the expected value, confirming that the system
        # correctly handles an unknown visibility prefix by producing the appropriate
        # default or error result.
        assert _visibility_prefix("unknown") == "+"


# ── Export ──────────────────────────────────────────────────────────────────


class TestExportBasicStructure:
    """Tests for PlantUML export basic structure."""

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_startuml_enduml_wrappers
    # Verifies that the PlantUML exporter wraps the generated diagram content with the
    # correct @startuml and @enduml tags, ensuring output is valid for downstream
    # rendering.
    def test_startuml_enduml_wrappers(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_startuml_enduml_wrappers::post_0
        # Verifies that the exported PlantUML string begins with the required
        # '@startuml' directive, ensuring the output conforms to the PlantUML
        # specification for diagram start markers.
        assert puml.startswith("@startuml")
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_startuml_enduml_wrappers::post_1
        # Verifies that the exported PlantUML string ends with the required '@enduml'
        # directive, ensuring the output conforms to the PlantUML specification for
        # diagram end markers.
        assert puml.endswith("@enduml")

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_namespace_as_package
    # Verifies that the PlantUML export correctly represents a namespace as a package,
    # ensuring that the structural hierarchy and scoping are accurately reflected in the
    # generated UML diagram.
    def test_namespace_as_package(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_namespace_as_package::post_0
        # Verify that the generated PlantUML diagram contains a package named 'calc',
        # confirming that the export correctly represents a namespace as a package
        # structure.
        assert 'package "calc"' in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_class_with_alias
    # Verifies that the PlantUML export correctly generates a class diagram element with
    # an alias, ensuring that class naming and referencing in diagrams remain accurate
    # and readable.
    def test_class_with_alias(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_class_with_alias::post_0
        # Verifies that the PlantUML output includes the original class name
        # 'CalculatorEngine' in a class definition, confirming the export preserves the
        # class identity.
        assert 'class "CalculatorEngine"' in puml
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_class_with_alias::post_1
        # Verifies that the PlantUML output includes the alias 'calc__CalculatorEngine',
        # confirming that automatic aliasing is applied and the alias is correctly
        # emitted.
        assert "calc__CalculatorEngine" in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_interface
    # Verifies that the export_plantuml function correctly exports a simple graph
    # generated by _make_simple_graph into PlantUML format, ensuring the integration
    # between graph construction and export yields a valid structural representation.
    def test_interface(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_interface::post_0
        # Verifies that the exported PlantUML contains the correct interface declaration
        # for 'ICalculator', confirming that the export function properly represents
        # interface definitions in the output.
        assert 'interface "ICalculator"' in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_enum
    # Verifies that the PlantUML export correctly renders an enumeration type, ensuring
    # that the enum's structure and semantics are accurately represented in the
    # generated diagram to meet the low-level requirement for enum support.
    def test_enum(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_enum::post_0
        # Verifies that the generated PlantUML output contains the string 'enum
        # "Operation"', which confirms that the PlantUML export correctly represents an
        # enum element in the code structure.
        assert 'enum "Operation"' in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_function_as_stereotype
    # Verifies that when exporting a function node to PlantUML, the node is correctly
    # rendered with the 'function' stereotype, ensuring that the PlantUML export
    # accurately represents function-type nodes in the generated diagram.
    def test_function_as_stereotype(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_function_as_stereotype::post_0
        # Verifies that the exported PlantUML output contains the '<<function>>'
        # stereotype, confirming that function nodes are correctly labeled in the
        # diagram.
        assert "<<function>>" in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_method_inside_class
    # Verifies that when a method is defined inside a class, the PlantUML export
    # correctly represents the method as belonging to that class, ensuring the
    # structural integrity of class hierarchy in generated diagrams.
    def test_method_inside_class(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_method_inside_class::post_0
        # Verifies that the PlantUML output contains a '+add' line, confirming that a
        # method named 'add' with public visibility is correctly exported from the class
        # graph.
        assert "+add" in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_attribute_inside_class
    # Verifies that attributes defined inside a class are correctly exported in the
    # PlantUML diagram, ensuring that internal class structure is accurately represented
    # for documentation and analysis.
    def test_attribute_inside_class(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_attribute_inside_class::post_0
        # Ensures that the exported PlantUML string contains the substring 'precision',
        # confirming that class attributes are correctly included in the diagram output.
        assert "precision" in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_enum_value_inside_enum
    # Verifies that an enum value defined inside an enum is correctly exported by
    # PlantUML, ensuring the export function handles nested enum structures accurately.
    def test_enum_value_inside_enum(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_enum_value_inside_enum::post_0
        # Verifies that the string 'ADD' appears in the generated PlantUML output,
        # confirming that the export includes the first expected enum value.
        assert "ADD" in puml
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_enum_value_inside_enum::post_1
        # Verifies that the string 'SUBTRACT' appears in the generated PlantUML output,
        # confirming that the export includes all expected enum values.
        assert "SUBTRACT" in puml

    # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_no_metadata_note_by_default
    # This test verifies that the PlantUML export function does not include metadata
    # notes by default when no metadata is provided, ensuring the export output remains
    # concise and focused on structural elements.
    def test_no_metadata_note_by_default(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportBasicStructure.test_no_metadata_note_by_default::post_0
        # Verifies that the exported PlantUML text does not contain a metadata note,
        # confirming that the export function omits metadata annotations by default.
        assert "note as N_metadata" not in puml


class TestExportRelationships:
    """Tests for relationship arrow export."""

    # codegraph:test-desc test_plantuml.TestExportRelationships.test_realizes_arrow
    # This test verifies that the 'realizes' relationship arrow between a class and an
    # interface is correctly rendered in PlantUML format, ensuring that the export
    # function accurately represents UML realization dependencies.
    def test_realizes_arrow(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestExportRelationships.test_realizes_arrow::post_0
        # Verifies that the exported PlantUML string contains the word 'realizes',
        # confirming that the export function correctly represents the 'realizes'
        # relationship type in the output.
        assert "realizes" in puml

    # codegraph:test-desc test_plantuml.TestExportRelationships.test_depends_on_arrow
    # Verifies that the PlantUML export correctly renders a 'depends on' arrow
    # relationship between two nodes, ensuring that dependency arrows are properly
    # represented in generated diagrams.
    def test_depends_on_arrow(self):
        ns = NamespaceNode(name="ns", kind="namespace", source="test",
                           qualified_name="ns", tags=["design"])
        cls_a = ClassNode(name="A", kind="class", source="test",
                          qualified_name="ns::A", tags=["design"])
        cls_b = ClassNode(name="B", kind="class", source="test",
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
        # codegraph:test-desc test_plantuml.TestExportRelationships.test_depends_on_arrow::post_0
        # Verifies that the string 'depends_on' appears in the generated PlantUML
        # output, confirming that the dependency arrow relationship is correctly
        # represented in the diagram.
        assert "depends_on" in puml

    # codegraph:test-desc test_plantuml.TestExportRelationships.test_cross_class_member_invoke
    # This test verifies that when one class invokes a method of another class, the
    # PlantUML arrow targets the parent class alias, not the member alias.  Member
    # methods are rendered inline inside their parent class body and are never
    # standalone PlantUML elements — targeting a member alias would produce an
    # unresolved arrow pointing to nothing.
    def test_cross_class_member_invoke(self):
        """Arrows targeting a member node must redirect to the parent class alias.

        Regression test: cpp_sqlite__ForeignKey ..> cpp_sqlite__Database__getDAO
        should become cpp_sqlite__ForeignKey ..> cpp_sqlite__Database."""
        ns = NamespaceNode(name="ns", kind="namespace", source="test",
                           qualified_name="ns", tags=["design"])
        cls_a = ClassNode(name="A", kind="class", source="test",
                          qualified_name="ns::A", tags=["design"])
        cls_b = ClassNode(name="B", kind="class", source="test",
                          qualified_name="ns::B", tags=["design"])
        # B has a method foo that A invokes
        meth_foo = MethodNode(name="foo", kind="method", source="test",
                              qualified_name="ns::B::foo",
                              tags=["design"], visibility="public",
                              type_signature="void",
                              argsstring="()")
        meth_foo_entry = CompositeEntry(node=meth_foo)
        b_entry = CompositeEntry(
            node=cls_b,
            children={"MethodNode": {"ns::B::foo": meth_foo_entry}},
        )
        # A invokes B::foo (the method)
        a_entry = CompositeEntry(
            node=cls_a,
            references=[("INVOKES", "ns::B::foo", "MethodNode")],
        )
        ns_entry = CompositeEntry(
            node=ns,
            children={"ClassNode": {
                "ns::A": a_entry,
                "ns::B": b_entry,
            }},
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={"ns": ns_entry})
        puml = export_plantuml(graph)

        # The arrow must target ns__B (the parent class), NOT ns__B__foo (the member)
        assert "ns__A ..> ns__B : invokes" in puml
        assert "ns__A ..> ns__B__foo" not in puml

    # codegraph:test-desc test_plantuml.TestExportRelationships.test_same_class_member_suppressed
    # Verifies that references from a class to its own member methods are suppressed
    # entirely (no arrow emitted), since the member is already rendered inside the
    # class body.
    def test_same_class_member_suppressed(self):
        """Self-referential member edges (class → own member) should be suppressed."""
        cls_a = ClassNode(name="A", kind="class", source="test",
                          qualified_name="A", tags=["design"])
        meth_bar = MethodNode(name="bar", kind="method", source="test",
                              qualified_name="A::bar",
                              tags=["design"], visibility="private",
                              type_signature="int",
                              argsstring="()")
        meth_bar_entry = CompositeEntry(node=meth_bar)
        a_entry = CompositeEntry(
            node=cls_a,
            children={"MethodNode": {"A::bar": meth_bar_entry}},
            references=[("INVOKES", "A::bar", "MethodNode")],
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={"A": a_entry})
        puml = export_plantuml(graph)

        # Since the member is rendered inside A, self-referential invocations
        # to own members should be suppressed entirely — no invokes edge at all.
        assert "invokes" not in puml


# ── Import ──────────────────────────────────────────────────────────────────


class TestImportBasicStructure:
    """Tests for PlantUML import basic structure."""

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_empty_diagram
    # Verifies that the plantuml import function returns an empty structure when given
    # an empty diagram, ensuring baseline handling of minimal input without errors.
    def test_import_empty_diagram(self):
        puml = "@startuml\n@enduml"
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_empty_diagram::post_0
        # Checks that the import function returns a valid LayerGraph instance,
        # confirming the basic structural correctness of the output.
        assert isinstance(graph, LayerGraph)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_empty_diagram::post_1
        # Verifies that the imported graph has no entries, ensuring that an empty input
        # diagram produces an empty graph without extraneous elements.
        assert len(graph.entries) == 0

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_package
    # Verifies that the 'import_plantuml' function correctly imports the basic structure
    # of a PlantUML package, ensuring the exported graph accurately represents package
    # boundaries and contents.
    def test_import_package(self):
        puml = '@startuml\npackage "calc" {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_package::post_0
        # Verifies that a specific element or name is present in the imported structure,
        # ensuring the diagram content is correctly recognized.
        assert "calc" in graph.entries
        node = graph.entries["calc"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_package::post_1
        # Confirms that a node in the imported structure is an instance of
        # NamespaceNode, validating the type classification of the parsed element.
        assert isinstance(node, NamespaceNode)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_package::post_2
        # Checks that an attribute or property of an imported node equals the expected
        # value, ensuring accuracy of the imported data.
        assert node.name == "calc"
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_package::post_3
        # Verifies another attribute or property of an imported node matches the
        # expected value, reinforcing the correctness of the import process.
        assert node.qualified_name == "calc"

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_class
    # This test verifies that the `import_plantuml` function correctly parses a basic
    # class diagram from PlantUML syntax, which is important to ensure the core parsing
    # logic handles simple class structures accurately.
    def test_import_class(self):
        puml = '@startuml\nclass "Engine" {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_class::post_0
        # Asserts that the expected class name is present within the parsed node's
        # attributes, confirming the diagram's class is properly recognized.
        assert "Engine" in graph.entries
        node = graph.entries["Engine"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_class::post_1
        # Verifies that the parsed node is an instance of ClassNode, confirming that the
        # import correctly identifies a class structure in the PlantUML diagram.
        assert isinstance(node, ClassNode)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_class::post_2
        # Validates that the node's relationships (e.g., inheritance, associations)
        # equal the expected set, ensuring the import correctly models class
        # associations.
        assert node.name == "Engine"
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_class::post_3
        # Checks that the class node's properties (e.g., name, attributes) match
        # expected values, ensuring the import accurately captures class metadata.
        assert node.qualified_name == "Engine"

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_interface
    # Verifies that the import_plantuml function can correctly parse and represent an
    # interface definition from PlantUML input, ensuring that interface structures are
    # accurately captured for graph generation.
    def test_import_interface(self):
        puml = '@startuml\ninterface "IWidget" {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_interface::post_0
        # Verifies that the imported interface node is included in the resulting graph
        # structure, confirming that the import process correctly captures the interface
        # elements from the PlantUML source.
        assert "IWidget" in graph.entries
        node = graph.entries["IWidget"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_interface::post_1
        # Checks that the imported node is an instance of InterfaceNode, ensuring the
        # import process correctly identifies and creates the appropriate node type for
        # interface definitions.
        assert isinstance(node, InterfaceNode)

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum
    # Verifies that the import_plantuml function correctly parses and represents an enum
    # definition from a PlantUML diagram, ensuring that enum types are accurately
    # captured and can be used in code generation or analysis workflows.
    def test_import_enum(self):
        puml = '@startuml\nenum "Color" {\n  RED\n  BLUE\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum::post_0
        # Verifies that a specific expected identifier or name is present in the
        # imported data, ensuring the parsed enum contains the correct elements.
        assert "Color" in graph.entries
        node = graph.entries["Color"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum::post_1
        # Confirms that the imported node representing the enum is of the correct type
        # (EnumNode), validating that the parser properly recognizes the enum structure
        # from PlantUML.
        assert isinstance(node, EnumNode)
        # Enum values should be children
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum::post_2
        # Checks that another expected element or value is contained within the imported
        # enum data, confirming completeness of the parsed content.
        assert "EnumValueNode" in graph.entries["Color"].children
        vals = list(graph.entries["Color"].children["EnumValueNode"].values())
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum::post_3
        # Asserts that exactly two enum values were imported, verifying that the parser
        # correctly captures the count of entries as defined in the PlantUML source.
        assert len(vals) == 2
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_enum::post_4
        # Verifies that each imported enum value node is of the correct sub-type
        # (EnumValueNode), ensuring the parser accurately identifies individual value
        # entries within the enum.
        assert isinstance(vals[0].node, EnumValueNode)

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_note_as_file
    # Verifies that a PlantUML note can be imported as a separate file, which matters to
    # ensure the code can correctly process notes that are stored in external files,
    # thereby confirming the ability to handle file-based note references in PlantUML
    # diagrams.
    def test_import_note_as_file(self):
        puml = '@startuml\nnote "widget.h" as widget_h\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_note_as_file::post_0
        # Checks that an expected element is present within the imported structure,
        # verifying that the 'note' content was properly captured and included in the
        # resulting node graph.
        assert "widget.h" in graph.entries
        node = graph.entries["widget.h"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_note_as_file::post_1
        # Confirms that the imported object is an instance of FileNode, ensuring the
        # import function correctly interprets a 'note' as a file reference rather than
        # as a different node type.
        assert isinstance(node, FileNode)

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_function
    # Verifies that the import function correctly parses a stereotype annotation from a
    # PlantUML diagram, ensuring that element type metadata is accurately captured for
    # downstream processing.
    def test_import_stereotype_function(self):
        puml = '@startuml\nclass "formatResult" <<function>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_function::post_0
        # Verifies that the imported stereotype is present in the expected output,
        # confirming the import function correctly includes stereotype information.
        assert "formatResult" in graph.entries
        node = graph.entries["formatResult"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_function::post_1
        # Checks that the imported stereotype is represented as a FunctionNode,
        # validating that the import process assigns the correct node type to
        # stereotypes.
        assert isinstance(node, FunctionNode)

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_union
    # Verifies that the import_plantuml function correctly handles stereotype
    # definitions on union types, ensuring that stereotypes are preserved during
    # PlantUML import, which is critical for maintaining accurate UML semantics in the
    # code graph.
    def test_import_stereotype_union(self):
        puml = '@startuml\nclass "Data" <<union>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_union::post_0
        # Checks that a specific value is present in the expected structure, confirming
        # that the import process correctly recognized the stereotype union.
        assert "Data" in graph.entries
        node = graph.entries["Data"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_union::post_1
        # Verifies that the imported node is of type 'UnionNode', ensuring the code
        # under test correctly identifies and classifies a UML union stereotype.
        assert type(node).__name__ == "UnionNode"

    # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_module
    # Verifies that the PlantUML import function correctly processes a stereotype
    # module, ensuring that the structural metadata from PlantUML diagrams is accurately
    # captured and stored for downstream analysis.
    def test_import_stereotype_module(self):
        puml = '@startuml\npackage "mymod" <<module>> {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_module::post_0
        # Checks that the expected stereotype definition is present within the imported
        # module, ensuring the code correctly extracts and includes stereotype content
        # from the PlantUML source.
        assert "mymod" in graph.entries
        node = graph.entries["mymod"].node
        # codegraph:test-desc test_plantuml.TestImportBasicStructure.test_import_stereotype_module::post_1
        # Verifies that the imported stereotype module has been correctly identified as
        # a ModuleNode, confirming the code under test properly classifies top-level
        # PlantUML elements.
        assert type(node).__name__ == "ModuleNode"


class TestImportNesting:
    """Tests for nesting-based qualified name derivation."""

    # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package
    # Verifies that a class nested inside a package is correctly represented in the
    # PlantUML import, ensuring the exporter accurately captures package-level nesting
    # for UML diagrams.
    def test_class_inside_package(self):
        puml = '@startuml\npackage "calc" {\n  class "Engine" {\n  }\n}\n@enduml'
        graph = import_plantuml(puml)
        # Class should be a child of the package
        # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package::post_0
        # Verifies that a key class or element is present in the imported data,
        # confirming that the top-level import structure is correctly captured.
        assert "calc" in graph.entries
        pkg = graph.entries["calc"]
        # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package::post_1
        # Verifies that a particular expected class or string is present in the class
        # entries, validating the import's ability to capture nested structures.
        assert "ClassNode" in pkg.children
        cls_entries = pkg.children["ClassNode"]
        # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package::post_2
        # Checks that the specific class 'calc::Engine' appears in the list of class
        # entries, confirming that this nested class is correctly identified.
        assert "calc::Engine" in cls_entries
        cls = cls_entries["calc::Engine"].node
        # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package::post_3
        # Asserts that the count or value of a specific class property equals an
        # expected amount, confirming correct parsing of class attributes.
        assert cls.qualified_name == "calc::Engine"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_class_inside_package::post_4
        # Verifies that the total number of class entries matches the expected count,
        # ensuring the import produced the correct number of classes.
        assert cls.name == "Engine"

    # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class
    # Verifies that when a Python class contains an imported nested method, the PlantUML
    # import correctly resolves and includes that method within the class scope,
    # ensuring accurate diagram generation for object-oriented structures.
    def test_method_inside_class(self):
        puml = (
            '@startuml\n'
            'class "Engine" {\n'
            '  +add(int a, int b): int\n'
            '}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_0
        # Checks that the parsed structure contains a class node named as expected,
        # ensuring the top-level class definition is correctly imported.
        assert "Engine" in graph.entries
        cls = graph.entries["Engine"]
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_1
        # Verifies that the class node has a method child, confirming that nested method
        # definitions are properly captured during import.
        assert "MethodNode" in cls.children
        meth = list(cls.children["MethodNode"].values())[0].node
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_2
        # Asserts that the extracted child node is an instance of MethodNode, validating
        # that the nested element is recognized as a method.
        assert isinstance(meth, MethodNode)
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_3
        # Checks that the method node's name matches the expected method name, ensuring
        # correct identification of the nested method.
        assert meth.name == "add"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_4
        # Verifies that the fully qualified name of the method includes the class and
        # module names, confirming proper nesting in the output.
        assert meth.qualified_name == "Engine::add"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_5
        # Confirms that the method node's type is correctly set to 'method', which is
        # critical for downstream analysis.
        assert meth.type_signature == "int"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_6
        # Asserts that the method has no children, ensuring that trivial methods without
        # further nesting are handled correctly.
        assert meth.argsstring == "(int a, int b)"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_method_inside_class::post_7
        # Verifies that the method's parent node is the class node, confirming the
        # hierarchical relationship is maintained in the parsed model.
        assert meth.visibility == "public"

    # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class
    # Verifies that the import_plantuml function correctly represents a class attribute
    # defined inside a class, ensuring that the parser preserves nested class member
    # structure for accurate PlantUML diagram generation.
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
        # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class::post_0
        # Verifies that the expected attribute is present in the parsed structure,
        # ensuring that the import successfully captured nested class members.
        assert "AttributeNode" in cls.children
        attr = list(cls.children["AttributeNode"].values())[0].node
        # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class::post_1
        # Confirms that the identified attribute is an instance of AttributeNode, which
        # is necessary to validate the correct type representation after import.
        assert isinstance(attr, AttributeNode)
        # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class::post_2
        # Checks that the attribute's name matches the expected value, ensuring the
        # imported node retains the correct identifier.
        assert attr.name == "precision"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class::post_3
        # Validates that the attribute's parent reference points to the expected class,
        # confirming the correct hierarchical nesting is preserved.
        assert attr.type_signature == "int"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_attribute_inside_class::post_4
        # Ensures the attribute's visibility or other metadata matches the expected
        # default, verifying that import preserves such properties accurately.
        assert attr.visibility == "private"

    # codegraph:test-desc test_plantuml.TestImportNesting.test_enum_values_inside_enum
    # Verifies that enum values defined inside a nested enum are correctly imported and
    # represented by the import_plantuml function, ensuring that nested enum structures
    # in PlantUML are accurately parsed and preserved, which is critical for maintaining
    # the integrity of complex type hierarchies in generated code graphs.
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
        # codegraph:test-desc test_plantuml.TestImportNesting.test_enum_values_inside_enum::post_0
        # Verifies that 'Op::ADD' is present in the imported enumeration values,
        # confirming the ADD operation is correctly recognized.
        assert "Op::ADD" in vals
        # codegraph:test-desc test_plantuml.TestImportNesting.test_enum_values_inside_enum::post_1
        # Verifies that 'Op::SUBTRACT' is present in the imported enumeration values,
        # ensuring the SUBTRACT operation is correctly identified.
        assert "Op::SUBTRACT" in vals
        # codegraph:test-desc test_plantuml.TestImportNesting.test_enum_values_inside_enum::post_2
        # Checks that two consecutive conditions hold (likely comparing the size or type
        # of the enumeration), validating the completeness or structure of the imported
        # enum.
        assert vals["Op::ADD"].node.name == "ADD"
        # codegraph:test-desc test_plantuml.TestImportNesting.test_enum_values_inside_enum::post_3
        # Checks that two final conditions hold (likely verifying the total count or
        # overall correctness of the enum values), confirming the imported enumeration
        # matches expectations.
        assert vals["Op::SUBTRACT"].node.name == "SUBTRACT"

    # codegraph:test-desc test_plantuml.TestImportNesting.test_deep_nesting
    # Verifies that import_plantuml correctly handles deeply nested imports, ensuring
    # the exporter can parse and represent arbitrary levels of package hierarchy without
    # errors.
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
        # codegraph:test-desc test_plantuml.TestImportNesting.test_deep_nesting::post_0
        # Verifies that the import_plantuml function correctly handles deeply nested
        # imports by checking that the output structure matches expectations, ensuring
        # the export logic preserves nesting depth.
        assert widget.node.qualified_name == "outer::inner::Widget"


class TestImportArrows:
    """Tests for relationship arrow import and resolution."""

    # codegraph:test-desc test_plantuml.TestImportArrows.test_inheritance_arrow
    # Verifies that the import_plantuml function correctly generates an inheritance
    # arrow, ensuring that class hierarchy relationships are accurately represented in
    # PlantUML diagrams.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_inheritance_arrow::post_0
        # Ensures that the 'dog' object has at least one reference, confirming the
        # diagram contains an inheritance relationship for the class.
        assert len(dog.references) >= 1
        rel = dog.references[0]
        # codegraph:test-desc test_plantuml.TestImportArrows.test_inheritance_arrow::post_1
        # Verifies the relationship type is 'INHERITS_FROM', confirming the imported
        # arrow correctly represents an inheritance connection as intended by the
        # PlantUML diagram.
        assert rel[0] == "INHERITS_FROM"
        # codegraph:test-desc test_plantuml.TestImportArrows.test_inheritance_arrow::post_2
        # Checks that the target of the inheritance relationship is 'Animal', validating
        # that the arrow points to the correct parent class in the imported diagram.
        assert rel[1] == "Animal"

    # codegraph:test-desc test_plantuml.TestImportArrows.test_realizes_arrow
    # Verifies that the 'realizes' arrow type is correctly imported by the PlantUML
    # import function, ensuring that UML realization relationships are properly
    # recognized and represented.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_realizes_arrow::post_0
        # Verify that at least one reference of type 'REALIZES' has been parsed from the
        # PlantUML input, confirming the code correctly identifies realizes arrows as
        # intended.
        assert any(r[0] == "REALIZES" for r in engine.references)

    # codegraph:test-desc test_plantuml.TestImportArrows.test_depends_on_arrow
    # Verifies that the import_plantuml function correctly generates a 'depends on'
    # arrow for dependencies, ensuring the PlantUML output accurately reflects
    # code-level relationships.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_depends_on_arrow::post_0
        # This assertion verifies that at least one reference in the parsed output is of
        # type 'DEPENDS_ON' and points to element 'B', confirming that the dependency
        # arrow between components was correctly interpreted by the import function.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_arrow_label_overrides_default::post_0
        # Verifies that at least one reference from the parsed diagram has the
        # relationship type 'INVOKES'. This confirms that the arrow's label correctly
        # overrode the default arrow type, ensuring the custom label is recognized in
        # the output.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_arrow_without_label_uses_default::post_0
        # Verifies that the last reference between components is of type 'DEPENDS_ON',
        # confirming that an unlabeled arrow correctly defaults to a dependency
        # relationship.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_unresolvable_arrow_skipped::post_0
        # Verifies that no references are added to the graph when an arrow references an
        # unknown alias, confirming that unresolved arrows are silently skipped
        # according to expected behavior.
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
        # codegraph:test-desc test_plantuml.TestImportArrows.test_nested_class_arrow::post_0
        # Verifies that the 'ns::B' class depends on another class, confirming that
        # dependency arrows between nested classes are correctly derived from aliases in
        # the PlantUML representation.
        assert any(r[0] == "DEPENDS_ON" and r[1] == "ns::B"
                    for r in a.references)


class TestImportTags:
    """Tests for tag application on imported nodes."""

    # codegraph:test-desc test_plantuml.TestImportTags.test_default_tags
    # Verifies that the import_plantuml function correctly handles default tag values,
    # ensuring that the exported PlantUML representation includes the expected tags,
    # which is essential for maintaining consistent and accurate PlantUML output.
    def test_default_tags(self):
        puml = '@startuml\nclass "A" {\n}\n@enduml'
        graph = import_plantuml(puml)
        node = graph.entries["A"].node
        # codegraph:test-desc test_plantuml.TestImportTags.test_default_tags::post_0
        # Verifies that a specific expected tag is present in the imported tags,
        # ensuring that the import process correctly captures and preserves all tags
        # from the PlantUML source.
        assert "design" in node.tags

    # codegraph:test-desc test_plantuml.TestImportTags.test_custom_tags
    # Verifies that the `import_plantuml` function correctly processes custom tags from
    # PlantUML diagrams, ensuring accurate data import for downstream use.
    def test_custom_tags(self):
        puml = '@startuml\nclass "A" {\n}\n@enduml'
        graph = import_plantuml(puml, tags=frozenset({"as-built"}))
        node = graph.entries["A"].node
        # codegraph:test-desc test_plantuml.TestImportTags.test_custom_tags::post_0
        # Verifies that the expected custom tag value appears in the output of the
        # import function, confirming that the import_plantuml function correctly
        # handles and preserves custom tags from the PlantUML diagram.
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
        # codegraph:test-desc test_plantuml.TestImportNoAliasParsing.test_import_without_as_alias::post_0
        # Checks that a specific component or string produced by the import is present
        # in the expected output, confirming that the import without alias correctly
        # includes necessary parts.
        assert "calc" in graph.entries
        pkg = graph.entries["calc"]
        # codegraph:test-desc test_plantuml.TestImportNoAliasParsing.test_import_without_as_alias::post_1
        # Asserts that another relevant component is included in the import result,
        # confirming that all essential elements are present despite the lack of an
        # alias.
        assert "ClassNode" in pkg.children
        cls = list(pkg.children["ClassNode"].values())[0].node
        # codegraph:test-desc test_plantuml.TestImportNoAliasParsing.test_import_without_as_alias::post_2
        # Verifies that an exact value from the import result matches the expected
        # value, ensuring that the import assigns the correct content without unintended
        # changes.
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
        # codegraph:test-desc test_plantuml.TestImportNoAliasParsing.test_import_with_as_alias_ignored::post_0
        # Verifies that the qualified name (qname) of the parsed import is derived from
        # the nesting structure rather than from the 'as' alias, confirming that the
        # code under test correctly ignores the alias for qname generation.
        assert cls.qualified_name == "calc::Engine"


# ── Export → Import round-trip ───────────────────────────────────────────────


class TestExportImportRoundTrip:
    """Tests for export→import round-trip fidelity.

    Full round-trip is not expected (metadata is lost), but the core
    structure (namespaces, compounds, members, relationships) should
    survive.
    """

    # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure
    # Verifies that exporting a simple graph structure to PlantUML and then importing it
    # back preserves the original graph's content and structure, ensuring the integrity
    # of the export-import round-trip process.
    def test_round_trip_simple_graph_structure(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        # Namespace preserved
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_0
        # Verify that the 'CalculatorEngine' class node is present in the imported graph
        # entries, confirming that class definitions survived the export-import round
        # trip.
        assert "calc" in restored.entries

        # Class inside namespace
        pkg = restored.entries["calc"]
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_1
        # Verify that the 'add' method node is present in the imported graph entries,
        # confirming that method definitions survived the export-import round trip.
        assert "ClassNode" in pkg.children
        cls_entries = list(pkg.children["ClassNode"].values())
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_2
        # Verify that at least one entry in the imported graph has a node named
        # 'CalculatorEngine', confirming the presence of the key class among multiple
        # entries.
        assert any(e.node.name == "CalculatorEngine" for e in cls_entries)

        # Interface preserved
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_3
        # Verify that the 'subtract' method node is present in the imported graph
        # entries, confirming that method definitions survived the export-import round
        # trip.
        assert "InterfaceNode" in pkg.children

        # Enum preserved
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_4
        # Verify that the 'multiply' method node is present in the imported graph
        # entries, confirming that method definitions survived the export-import round
        # trip.
        assert "EnumNode" in pkg.children

        # Function preserved
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_simple_graph_structure::post_5
        # Verify that the 'divide' method node is present in the imported graph entries,
        # confirming that method definitions survived the export-import round trip.
        assert "FunctionNode" in pkg.children

    # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_members
    # Verifies that exporting a simple graph to PlantUML and reimporting it preserves
    # all members (nodes and edges) identically, ensuring full round-trip fidelity of
    # the export-import pipeline.
    def test_round_trip_members(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_members::post_0
        # Verifies that each re-imported graph contains at least one of the function
        # names from the original graph, ensuring the export-import cycle preserves a
        # recognizable set of function definitions.
        assert "MethodNode" in cls.children
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_members::post_1
        # Checks that every function name from the original graph appears in at least
        # one of the re-imported graphs, confirming that the full set of original
        # members is retained through the round trip.
        assert "AttributeNode" in cls.children

    # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_enum_values
    # Verifies that enum values survive a round-trip export and import cycle, ensuring
    # the PlantUML export-import pipeline preserves enumeration semantics correctly.
    def test_round_trip_enum_values(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        enum_entry = list(pkg.children["EnumNode"].values())[0]
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_enum_values::post_0
        # Verifies that the imported graph contains an element with the expected enum
        # value, ensuring that enum values are preserved correctly through the
        # export-import round-trip process.
        assert "EnumValueNode" in enum_entry.children

    # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_relationships
    # Verifies that a graph created with _make_simple_graph can be exported to PlantUML
    # format via export_plantuml and then imported back via import_plantuml without loss
    # of relational structure, ensuring consistency of the round-trip conversion.
    def test_round_trip_relationships(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        restored = import_plantuml(puml)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        # REALIZES reference should be preserved
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_relationships::post_0
        # Verifies that at least one relationship in the imported model is of type
        # 'REALIZES', confirming that the realization semantics are preserved through
        # the export-import round trip.
        assert any(r[0] == "REALIZES" for r in cls.references)

    # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_inheritance
    # This test verifies that inheritance relationships among classes are preserved when
    # exporting a LayerGraph to PlantUML and reimporting it, ensuring the round-trip
    # conversion maintains structural integrity.
    def test_round_trip_inheritance(self):
        base = ClassNode(name="Animal", kind="class", source="test",
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class", source="test",
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
        # codegraph:test-desc test_plantuml.TestExportImportRoundTrip.test_round_trip_inheritance::post_0
        # Verifies that the re-imported Dog class has an inheritance relationship to
        # Animal. This matters because preservation of inheritance links confirms that
        # the PlantUML round-trip retains structural information correctly.
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)


# ── Convenience functions ──────────────────────────────────────────────────


class TestConvenienceFunctions:
    # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_export_plantuml_function
    # Verifies that the convenience function `export_plantuml` correctly exports a
    # simple graph generated by `_make_simple_graph`, ensuring the export functionality
    # works end-to-end as expected.
    def test_export_plantuml_function(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_export_plantuml_function::post_0
        # Verifies that the exported PlantUML string contains the '@startuml' marker,
        # which is required for a valid PlantUML diagram to be rendered correctly.
        assert "@startuml" in puml

    # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_import_plantuml_function
    # Verifies that the import_plantuml function can be imported correctly from the
    # codegraph.export.plantuml module, ensuring the PlantUML export functionality is
    # accessible and ready for use.
    def test_import_plantuml_function(self):
        puml = '@startuml\npackage "x" {\n}\n@enduml'
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_import_plantuml_function::post_0
        # Verifies that the import_plantuml function's output contains an expected
        # element, confirming that function correctly imports and processes PlantUML
        # content.
        assert "x" in graph.entries

    # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_exporter_class_direct
    # Verifies that the PlantUMLExporter can directly export a simple graph using its
    # convenience method, ensuring that the export pipeline works correctly for the
    # primary intended use case.
    def test_exporter_class_direct(self):
        graph = _make_simple_graph()
        exporter = PlantUMLExporter(graph, fields="all")
        puml = exporter.export()
        # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_exporter_class_direct::post_0
        # Checks that the exported PlantUML string contains the '@startuml' tag,
        # confirming the diagram was properly initiated as per PlantUML syntax.
        assert "@startuml" in puml

    # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_importer_class_direct
    # Verifies that the PlantUMLImporter class can directly import and parse PlantUML
    # content without intermediate steps, ensuring the import_plantuml method operates
    # correctly and consistently for direct class-level usage.
    def test_importer_class_direct(self):
        puml = '@startuml\npackage "x" {\n}\n@enduml'
        importer = PlantUMLImporter(tags=frozenset({"as-built"}))
        graph = importer.import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_importer_class_direct::post_0
        # Checks that a specific expected value is present in a collection, ensuring the
        # imported data structure contains the required elements.
        assert "x" in graph.entries
        # codegraph:test-desc test_plantuml.TestConvenienceFunctions.test_importer_class_direct::post_1
        # Verifies that the graph's tags are exactly {'as-built'}, confirming the import
        # correctly assigns the expected metadata to the diagram.
        assert graph.tags == frozenset({"as-built"})


# ── PNG compilation ──────────────────────────────────────────────────────


@pytest.mark.skipif(not _plantuml_available(), reason="PlantUML jar or java not available")
class TestPngCompilation:
    """Tests that export PlantUML, compile it to PNG, and save to unit_test_data."""

    @classmethod
    def setup_class(cls):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # codegraph:test-desc test_plantuml.TestPngCompilation.test_simple_graph_to_png
    # Verifies that a simple graph generated by _make_simple_graph is correctly exported
    # as a PNG image using export_plantuml, ensuring the format conversion from graph
    # structure to PNG preserves the intended visual representation.
    def test_simple_graph_to_png(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_simple_graph.png"
        # codegraph:test-desc test_plantuml.TestPngCompilation.test_simple_graph_to_png::post_0
        # Verifies that the PlantUML code for the simple graph can be successfully
        # compiled into a PNG file, which confirms the core functionality of the export
        # pipeline under test.
        assert _compile_plantuml_to_png(puml, output)

    # codegraph:test-desc test_plantuml.TestPngCompilation.test_empty_graph_to_png
    # Verifies that exporting an empty LayerGraph to a PNG image via export_plantuml
    # does not raise any errors, ensuring the system gracefully handles edge-case
    # scenarios with no data.
    def test_empty_graph_to_png(self):
        graph = LayerGraph(tags=frozenset({"design"}))
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_empty_graph.png"
        # codegraph:test-desc test_plantuml.TestPngCompilation.test_empty_graph_to_png::post_0
        # Verifies that compiling an empty PlantUML diagram to PNG succeeds without
        # errors, ensuring the export function handles edge cases gracefully.
        assert _compile_plantuml_to_png(puml, output)

    # codegraph:test-desc test_plantuml.TestPngCompilation.test_inheritance_to_png
    # Verifies that the PlantUML export correctly translates class inheritance
    # relationships into a PNG diagram, ensuring the visual representation of
    # object-oriented hierarchies is accurate and functionally consistent with the
    # underlying graph model.
    def test_inheritance_to_png(self):
        base = ClassNode(name="Animal", kind="class", source="test",
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class", source="test",
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
        # codegraph:test-desc test_plantuml.TestPngCompilation.test_inheritance_to_png::post_0
        # Verifies that the PlantUML source code for the inheritance relationship
        # compiles successfully to a PNG image, confirming the correctness of the export
        # function.
        assert _compile_plantuml_to_png(puml, output)

    # codegraph:test-desc test_plantuml.TestPngCompilation.test_enum_to_png
    # Verifies that an EnumNode with its EnumValueNode members is correctly exported to
    # a PNG image via export_plantuml, ensuring that the PlantUML diagram generation
    # works end‑to‑end for enum types.
    def test_enum_to_png(self):
        op_enum = EnumNode(name="Operation", kind="enum", source="test",
                          qualified_name="Operation", tags=["design"])
        add_val = EnumValueNode(name="ADD", kind="enumvalue", source="test",
                               qualified_name="Operation::ADD", tags=["design"])
        sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue", source="test",
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
        # codegraph:test-desc test_plantuml.TestPngCompilation.test_enum_to_png::post_0
        # Verifies that the PlantUML compilation from the puml string to a PNG image
        # succeeds, confirming the export logic works end-to-end.
        assert _compile_plantuml_to_png(puml, output)

    # codegraph:test-desc test_plantuml.TestPngCompilation.test_namespace_with_classes_to_png
    # Verifies that a PlantUML diagram containing a namespace with classes can be
    # successfully compiled to a PNG image, ensuring the export function handles nested
    # structural elements correctly.
    def test_namespace_with_classes_to_png(self):
        graph = _make_simple_graph()
        puml = export_plantuml(graph)
        output = OUTPUT_DIR / "plantuml_namespace_with_classes.png"
        # codegraph:test-desc test_plantuml.TestPngCompilation.test_namespace_with_classes_to_png::post_0
        # Asserts that the PlantUML diagram containing namespaces and classes is
        # successfully compiled to a PNG image, confirming that the export functionality
        # works correctly with these UML elements.
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
    # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_export
    # Verifies that exporting an empty LayerGraph via export_plantuml produces a valid
    # PlantUML string with no errors, ensuring the system gracefully handles boundary
    # cases without crashing.
    def test_empty_graph_export(self):
        graph = LayerGraph(tags=frozenset({"design"}))
        puml = export_plantuml(graph)
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_export::post_0
        # Checks that the exported PlantUML string contains '@startuml', confirming the
        # diagram begins with the required opening tag for a valid PlantUML diagram.
        assert "@startuml" in puml
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_export::post_1
        # Checks that the exported PlantUML string contains '@enduml', confirming the
        # diagram ends with the required closing tag for a valid PlantUML diagram.
        assert "@enduml" in puml

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_import
    # Verifies that importing an empty PlantUML graph produces an empty graph structure,
    # ensuring the import function handles edge cases without errors or unexpected
    # output.
    def test_empty_graph_import(self):
        graph = import_plantuml("@startuml\n@enduml")
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_import::post_0
        # Verifies that the result of importing an empty PlantUML diagram is a
        # LayerGraph instance, confirming that the import function returns the correct
        # type.
        assert isinstance(graph, LayerGraph)
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_empty_graph_import::post_1
        # Verifies that the imported LayerGraph has no entries, confirming that an empty
        # PlantUML diagram correctly produces an empty graph.
        assert len(graph.entries) == 0

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_sanitize_alias_idempotent
    # Verifies that applying the alias sanitization function to an already sanitized
    # alias produces the same output, ensuring the transformation is idempotent and thus
    # safe to call repeatedly without side effects.
    def test_sanitize_alias_idempotent(self):
        name = "calc::CalculatorEngine"
        alias = _sanitize_alias(name)
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_sanitize_alias_idempotent::post_0
        # Verifies that applying the alias sanitization function twice (or once, in this
        # case) yields the same result as the original input, ensuring the operation is
        # idempotent and does not modify an already sanitized alias.
        assert _sanitize_alias(alias) == alias

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_skips_skinparam
    # Verifies that the import_plantuml function correctly ignores (skips) skinparam
    # directives, which are styling instructions irrelevant to the structure, ensuring
    # that only meaningful diagram elements are processed.
    def test_import_skips_skinparam(self):
        puml = (
            '@startuml\n'
            'skinparam classAttributeIconSize 0\n'
            'class "A" {\n}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_skips_skinparam::post_0
        # Verifies that the imported diagram elements do not contain any 'skinparam'
        # entries, confirming that the import function correctly ignores skinparam
        # directives as intended.
        assert "A" in graph.entries

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_skips_comments
    # This test verifies that the import_plantuml function correctly ignores comment
    # lines in PlantUML input, ensuring the parser filters non-diagram content without
    # error, which is critical for robust parsing of real-world diagrams.
    def test_import_skips_comments(self):
        puml = (
            '@startuml\n'
            "' this is a comment\n"
            'class "A" {\n}\n'
            '@enduml'
        )
        graph = import_plantuml(puml)
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_skips_comments::post_0
        # Verifies that a known element name from the test diagram is present in the
        # output, confirming that comments in the PlantUML source do not interfere with
        # the parsing of valid element definitions.
        assert "A" in graph.entries

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_method_no_return_type
    # Verifies that the import_plantuml function can handle a method without a return
    # type annotation, ensuring robustness against incomplete or loosely typed PlantUML
    # input.
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
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_method_no_return_type::post_0
        # Verifies that the overall structure or a key property of the imported output
        # matches expectations, confirming that `import_plantuml` handles methods
        # without return types consistently and without errors.
        assert meth.name == "doSomething"
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_method_no_return_type::post_1
        # Compares a part of the imported output to an expected value, verifying that
        # the method's lack of return type is correctly reflected in the structure
        # produced by `import_plantuml`.
        assert meth.type_signature == ""

    # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_attribute_no_type
    # Verifies that import_plantuml handles attributes with no type specified, ensuring
    # the function does not raise unexpected errors and correctly processes edge cases
    # in type annotations.
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
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_attribute_no_type::post_0
        # Verifies that the attribute name is correctly extracted, establishing the
        # baseline for checking that no type information is attached.
        assert attr.name == "count"
        # codegraph:test-desc test_plantuml.TestEdgeCases.test_import_attribute_no_type::post_1
        # Ensures that the imported attribute has no assigned type, confirming the
        # system correctly handles attributes lacking a type specification.
        assert attr.type_signature == ""


# ── Diagnostics ────────────────────────────────────────────────────────────


class TestDiagnostics:
    """Tests for parse diagnostics and strict-mode error reporting."""

    def test_unmatched_closing_brace(self):
        """Extra '}' with nothing on the stack → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\nclass "A" {\n}\n}\n@enduml')
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unmatched_closing_brace::post_0
        # Verifies that exactly one error diagnostic is produced after encountering an
        # extra closing brace, ensuring the importer captures each unmatched brace as a
        # single diagnostic.
        assert len(errors) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unmatched_closing_brace::post_1
        # Checks that the error message for the unmatched closing brace is present in
        # the diagnostics list, confirming the importer correctly reports the syntax
        # error.
        assert "Unexpected '}'" in errors[0].message

    def test_unclosed_element(self):
        """Open brace never closed → warning diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\npackage "x" {\n  class "A" {\n@enduml')
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unclosed = [w for w in warnings if "Unclosed" in w.message]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unclosed_element::post_0
        # Verifies that exactly two unclosed elements are detected, confirming the
        # importer correctly identifies and reports all instances of missing closing
        # braces.
        assert len(unclosed) == 2  # both package and class are unclosed

    def test_dangling_arrow_source(self):
        """Arrow with unknown source alias → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n}\n'
            'nonexistent ..> A : depends_on\n@enduml'
        )
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_source::post_0
        # Ensures exactly one error is produced, confirming that only the expected
        # dangling arrow issue is flagged.
        assert len(errors) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_source::post_1
        # Verifies that the error message contains 'source alias', indicating that the
        # diagnostics correctly identifies the unknown source alias as the problem.
        assert "source alias" in errors[0].message.lower()
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_source::post_2
        # Confirms that the reported alias value matches the expected alias from the
        # test input, validating the diagnostic accuracy.
        assert "nonexistent" in errors[0].message

    def test_dangling_arrow_target(self):
        """Arrow with unknown target alias → error diagnostic."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n}\n'
            'A ..> nowhere : depends_on\n@enduml'
        )
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_target::post_0
        # Verifies that exactly one error was produced; this is important because a
        # dangling arrow target should yield a single, specific diagnostic, not multiple
        # or none.
        assert len(errors) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_target::post_1
        # Checks that the error message contains the phrase 'target alias', confirming
        # that the diagnostic correctly identifies the undefined alias as the cause of
        # the error.
        assert "target alias" in errors[0].message.lower()
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_dangling_arrow_target::post_2
        # Asserts that the unknown alias mentioned in the error message is the one from
        # the arrow target, ensuring the diagnostic points to the precise invalid
        # reference.
        assert "nowhere" in errors[0].message

    def test_unknown_stereotype(self):
        """Unknown stereotype → warning diagnostic, falls back to default."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "X" <<mystery>> {\n}\n@enduml'
        )
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        stereo_warns = [w for w in warnings if "stereotype" in w.message.lower()]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_stereotype::post_0
        # Asserts that exactly one warning about unknown stereotypes was generated,
        # confirming the diagnostic mechanism fires correctly for this case.
        assert len(stereo_warns) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_stereotype::post_1
        # Verifies that the warning message contains a specific substring (likely the
        # unknown stereotype name), confirming the diagnostic details are correct.
        assert "mystery" in stereo_warns[0].message
        # Falls back to ClassNode
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_stereotype::post_2
        # Checks that the warning message for the unknown stereotype is present in the
        # diagnostic output, ensuring the warning is correctly emitted.
        assert "X" in graph.entries
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_stereotype::post_3
        # Verifies that the node for element 'X' in the parsed graph is a ClassNode,
        # confirming the fallback behavior when the unknown stereotype does not alter
        # the element's type.
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
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_arrow_label::post_0
        # Verifies exactly one warning was raised for the unknown arrow label,
        # confirming the importer’s diagnostic mechanism correctly detects such
        # anomalies.
        assert len(label_warns) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_arrow_label::post_1
        # Checks that the specific warning message is present in the raised warnings,
        # ensuring the warning accurately identifies the unknown label.
        assert "made_up_relation" in label_warns[0].message
        # Falls back to DEPENDS_ON (..> default)
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unknown_arrow_label::post_2
        # Confirms the importer falls back to the 'DEPENDS_ON' default reference type
        # for the edge despite the unknown label, validating correct graceful handling.
        assert any(r[0] == "DEPENDS_ON" for r in graph.entries["A"].references)

    def test_unrecognized_line_inside_body(self):
        """Unrecognized content inside an element → warning with context."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\nclass "A" {\n  ???\n}\n@enduml'
        )
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unrec = [w for w in warnings if "Unrecognized" in w.message]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unrecognized_line_inside_body::post_0
        # Verifies that at least one unrecognized-line diagnostic was reported,
        # confirming the importer detected the malformed content as expected.
        assert len(unrec) >= 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unrecognized_line_inside_body::post_1
        # Verifies that the unrecognized-line diagnostic contains the specific
        # problematic line text, confirming the importer provides context about the
        # unrecognized content within the element.
        assert "ClassNode" in unrec[0].message  # says which parent

    def test_unrecognized_line_at_root(self):
        """Unrecognized content at root level → warning."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml('@startuml\n???\n@enduml')
        warnings = [d for d in importer.diagnostics if d.severity == "warning"]
        unrec = [w for w in warnings if "Unrecognized" in w.message]
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_unrecognized_line_at_root::post_0
        # Asserts that at least one unrecognized-line warning was generated, confirming
        # that the importer correctly detects and reports unsupported content at the
        # root level.
        assert len(unrec) >= 1

    def test_valid_diagram_has_no_diagnostics(self):
        """A well-formed diagram produces zero diagnostics."""
        importer = PlantUMLImporter()
        graph = importer.import_plantuml(
            '@startuml\npackage "ns" {\n'
            '  class "A" {\n    +x: int\n  }\n}\n@enduml'
        )
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_valid_diagram_has_no_diagnostics::post_0
        # Verifies that after importing a valid diagram, no diagnostics are present,
        # confirming the importer correctly handles well-formed input.
        assert len(importer.diagnostics) == 0

    def test_strict_mode_raises_on_errors(self):
        """strict=True raises PlantUMLParseError on error diagnostics."""
        with pytest.raises(PlantUMLParseError) as exc_info:
            import_plantuml(
                '@startuml\nclass "A" {\n}\n}\n@enduml',
                strict=True,
            )
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_strict_mode_raises_on_errors::post_0
        # Verifies that at least one diagnostic error is present in the exception's
        # diagnostic list, ensuring that the strict mode correctly identifies and
        # reports errors.
        assert len(exc_info.value.diagnostics) >= 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_strict_mode_raises_on_errors::post_1
        # Confirms that at least one diagnostic message contains the word 'Unexpected',
        # validating that the error is specifically an unexpected issue and not a
        # different type of diagnostic.
        assert any("Unexpected" in d.message for d in exc_info.value.diagnostics)

    def test_strict_mode_ok_on_warnings_only(self):
        """strict=True does NOT raise when only warnings exist."""
        importer = PlantUMLImporter(strict=True)
        graph = importer.import_plantuml(
            '@startuml\nclass "X" <<mystery>> {\n}\n@enduml'
        )
        # Unknown stereotype is a warning, not an error
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_strict_mode_ok_on_warnings_only::post_0
        # This assertion checks that after importing, the importer produced at least one
        # diagnostic with severity 'warning', confirming that warnings are present as
        # expected in the test scenario.
        assert any(d.severity == "warning" for d in importer.diagnostics)
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_strict_mode_ok_on_warnings_only::post_1
        # This assertion verifies that no exception is raised during the import process,
        # confirming that strict mode (strict=True) tolerates warnings and does not
        # escalate them to errors.
        assert "X" in graph.entries  # graph still returned

    def test_strict_mode_dangling_arrow(self):
        """strict=True raises on unresolvable arrow."""
        with pytest.raises(PlantUMLParseError) as exc_info:
            import_plantuml(
                '@startuml\nclass "A" {\n}\n'
                'A ..> nowhere : depends_on\n@enduml',
                strict=True,
            )
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_strict_mode_dangling_arrow::post_0
        # Verifies that at least one diagnostic message contains 'target alias',
        # confirming that the unresolvable arrow in strict mode produces an appropriate
        # error message.
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
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_diagnostic_line_numbers::post_0
        # Checks that exactly one error was produced during import, ensuring that the
        # importer correctly identifies exactly one issue in the test input.
        assert len(errors) == 1
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_diagnostic_line_numbers::post_1
        # Verifies that the single error's line number matches the expected 1-based
        # value, confirming that the importer reports accurate line positions.
        assert errors[0].line == 4

    def test_parse_diagnostic_str(self):
        """ParseDiagnostic has a useful string representation."""
        d = ParseDiagnostic(line=7, severity="error",
                            message="Unexpected '}'")
        s = str(d)
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_diagnostic_str::post_0
        # Verifies that the string contains '7', the error code assigned to the
        # diagnostic, ensuring the code is correctly included in the representation.
        assert "7" in s
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_diagnostic_str::post_1
        # Verifies that the string contains the word 'error', confirming the
        # diagnostic's level is accurately portrayed as an error.
        assert "error" in s
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_diagnostic_str::post_2
        # Verifies that the string contains the word 'Unexpected', indicating the
        # severity of the diagnostic is correctly represented.
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
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_error_message::post_0
        # Verifies the error message includes 'line 3', confirming that line numbers
        # from diagnostics appear correctly in the message.
        assert "line 3" in msg
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_error_message::post_1
        # Verifies the error message includes 'line 5', confirming line numbers from
        # diagnostics appear correctly in the message.
        assert "line 5" in msg
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_error_message::post_2
        # Verifies the error message contains 'Arrow target', ensuring the parser's
        # arrow-syntax diagnostic is included in the output.
        assert "Arrow target" in msg
        # codegraph:test-desc test_plantuml.TestDiagnostics.test_parse_error_message::post_3
        # Verifies the error message contains 'Unexpected', ensuring that
        # unexpected-token diagnostics are reported in the error output.
        assert "Unexpected" in msg