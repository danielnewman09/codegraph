"""Tests for Markdown export and import (text-based, public-only by default).

Covers export_markdown, import_markdown, qualified-name-from-heading,
inline relationship properties, round-trip, and diagnostics.
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from tests.integration.serialization._keying import key_graph as _kg


class _KeyedLayerGraph(LayerGraph):
    """LayerGraph that stamps canonical keys on construction (WP A)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kg(self), CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.export.markdown import (
    export_markdown,
    import_markdown,
    MarkdownExporter,
    MarkdownImporter,
)
from codegraph.export.plantuml import PlantUMLParseError, ParseDiagnostic
from codegraph.export.format import export_graph, import_graph

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_simple_graph() -> LayerGraph:
    """Small graph with namespace, class, methods, attributes, interface, enum."""
    ns = NamespaceNode(name="calc", kind="namespace", source="test", qualified_name="calc",
                       tags=["design"])
    cls = ClassNode(name="CalculatorEngine", kind="class", source="test",
                    qualified_name="calc::CalculatorEngine",
                    tags=["design"], visibility="public",
                    brief_description="Core engine handling arithmetic.")
    iface = InterfaceNode(name="ICalculator", kind="interface", source="test",
                          qualified_name="calc::ICalculator",
                          tags=["design"], visibility="public",
                          brief_description="Calculator contract.")
    meth = MethodNode(name="add", kind="method", source="test",
                      qualified_name="calc::CalculatorEngine::add",
                      tags=["design"], visibility="public",
                      brief_description="Performs addition.",
                      type_signature="int", argsstring="(int a, int b)")
    meth2 = MethodNode(name="_helper", kind="method", source="test",
                       qualified_name="calc::CalculatorEngine::_helper",
                       tags=["design"], visibility="private",
                       brief_description="Internal helper.")
    attr = AttributeNode(name="precision", kind="attribute", source="test",
                         qualified_name="calc::CalculatorEngine::precision",
                         tags=["design"], visibility="public",
                         type_signature="int",
                         brief_description="Decimal precision.")
    op_enum = EnumNode(name="Operation", kind="enum", source="test",
                       qualified_name="calc::Operation",
                       tags=["design"], visibility="public",
                       brief_description="Supported operations.")
    add_val = EnumValueNode(name="ADD", kind="enumvalue", source="test",
                            qualified_name="calc::Operation::ADD",
                            tags=["design"],
                            brief_description="Addition operation.")
    sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue", source="test",
                            qualified_name="calc::Operation::SUBTRACT",
                            tags=["design"],
                            brief_description="Subtraction operation.")

    meth_entry = CompositeEntry(node=meth)
    meth2_entry = CompositeEntry(node=meth2)
    attr_entry = CompositeEntry(node=attr)
    add_val_entry = CompositeEntry(node=add_val)
    sub_val_entry = CompositeEntry(node=sub_val)

    cls_entry = CompositeEntry(
        node=cls,
        children={
            "MethodNode": {
                "calc::CalculatorEngine::add": meth_entry,
                "calc::CalculatorEngine::_helper": meth2_entry,
            },
            "AttributeNode": {"calc::CalculatorEngine::precision": attr_entry},
        },
        references=[("REALIZES", "calc::ICalculator", "InterfaceNode")],
    )
    iface_entry = CompositeEntry(node=iface)
    op_entry = CompositeEntry(
        node=op_enum,
        children={"EnumValueNode": {
            "calc::Operation::ADD": add_val_entry,
            "calc::Operation::SUBTRACT": sub_val_entry,
        }},
    )
    ns_entry = CompositeEntry(
        node=ns,
        children={
            "ClassNode": {"calc::CalculatorEngine": cls_entry},
            "InterfaceNode": {"calc::ICalculator": iface_entry},
            "EnumNode": {"calc::Operation": op_entry},
        },
    )
    return _KeyedLayerGraph(tags=frozenset({"design"}), entries={"calc": ns_entry})


# ── Export ──────────────────────────────────────────────────────────────────


class TestMarkdownExport:
    """Tests for the new text-based Markdown export format."""

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_header_with_tags
    # Verifies that when a graph with header tags is exported to Markdown, the tags are
    # correctly included in the output, ensuring the export function handles metadata
    # faithfully.
    def test_header_with_tags(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_header_with_tags::step_0
        # Set up the test by creating a simple graph and exporting it to Markdown using
        # the export_markdown function, preparing the Markdown output for verification.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_header_with_tags::post_0
        # Verify that the exported Markdown begins with the expected header ' #
        # codegraph: design ', ensuring the export correctly generates the top-level
        # heading with the design tag.
        assert md.startswith("# codegraph: design\n")

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_namespace_heading
    # Verifies that the markdown export includes appropriate heading levels for
    # namespace nodes, ensuring correct structural hierarchy in the generated
    # documentation.
    def test_namespace_heading(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_namespace_heading::step_0
        # Sets up a simple graph with a 'calc' namespace and calls export_markdown to
        # generate markdown output, preparing the test for validation.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_namespace_heading::post_0
        # Verifies that the exported markdown contains a heading for the 'calc'
        # namespace, confirming that namespaces are correctly rendered as markdown
        # headings.
        assert "## Namespace: `calc`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_heading_with_qname
    # Verifies that a class node with a qualified name is exported as a Markdown
    # heading, ensuring correct heading generation for structured code representation.
    def test_class_heading_with_qname(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_heading_with_qname::step_0
        # Sets up the minimal graph and invokes the Markdown export to generate the
        # output string that will be checked.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_heading_with_qname::post_0
        # Verifies that the exported Markdown contains a level-3 heading with the fully
        # qualified class name 'calc::CalculatorEngine', confirming that the export
        # function correctly includes qualified names in heading text.
        assert "### Class: `calc::CalculatorEngine`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_interface_heading
    # Verifies that the markdown export function correctly generates an Interface
    # heading for a simple graph, ensuring the heading is present and properly
    # formatted.
    def test_interface_heading(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_interface_heading::step_0
        # Sets up the test by creating a simple graph structure and exporting it to
        # markdown, which generates the markdown string to be validated.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_interface_heading::post_0
        # Verifies that the exported markdown contains the expected heading for the
        # interface 'calc::ICalculator', ensuring the export correctly formats interface
        # definitions with their qualified name.
        assert "### Interface: `calc::ICalculator`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_heading
    # Verifies that the Markdown export function handles enumeration-style headings
    # correctly, ensuring that any heading with a numeric prefix is formatted as
    # intended in the exported output.
    def test_enum_heading(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_heading::step_0
        # Sets up the test by building a simple graph and exporting it to markdown,
        # preparing the output that will be checked for correct enum formatting.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_heading::post_0
        # Verifies that the generated markdown includes the expected heading '### Enum:
        # `calc::Operation`', confirming that enum types are properly rendered with
        # their full type name and a consistent heading structure.
        assert "### Enum: `calc::Operation`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_description_as_text
    # Verifies that the markdown export correctly renders a class description as plain
    # text, ensuring that the export functionality preserves textual documentation
    # accurately.
    def test_class_description_as_text(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_description_as_text::step_0
        # Sets up the test by creating a graph with a class node, ensuring the test has
        # the necessary data structure before export.
        md = export_markdown(_make_simple_graph())
        # Description is plain text right after heading
        idx = md.index("calc::CalculatorEngine`")
        tail = md[idx:]
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_class_description_as_text::post_0
        # Verifies that the exported markdown includes the class description 'Core
        # engine handling arithmetic', confirming the export correctly preserves textual
        # class metadata.
        assert "Core engine handling arithmetic" in tail

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_methods_section
    # This test verifies that the public methods section is correctly generated in the
    # markdown export by using a simple graph, ensuring that the export functionality
    # accurately represents the public API of the code under test.
    def test_public_methods_section(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_methods_section::step_0
        # Set up the initial environment or test fixtures required to generate the
        # Markdown export of the code graph, ensuring the test has the necessary data to
        # proceed.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_methods_section::post_0
        # Verify that the exported Markdown contains the header '**Public methods:**' to
        # confirm that the export function correctly includes a section title for public
        # methods, which is essential for a well-structured documentation output.
        assert "**Public methods:**" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_methods_section::post_1
        # Check that the exported Markdown includes a specific method signature and its
        # description in the public methods section, ensuring that individual method
        # details are accurately represented in the output.
        assert "`add(int a, int b): int` — Performs addition" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_hidden_by_default
    # This test verifies that the markdown export function and its helper graph builder
    # do not include private methods by default, ensuring that exported documentation
    # respects encapsulation and only exposes intended public interfaces.
    def test_private_methods_hidden_by_default(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_hidden_by_default::step_0
        # Sets up the test by creating a simple call graph and exporting it to a
        # Markdown string, preparing the output to be checked for private method
        # visibility.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_hidden_by_default::post_0
        # Verifies that the Markdown export does not contain the private method
        # '_helper', ensuring that private methods are hidden from the exported
        # documentation by default.
        assert "`_helper" not in md  # private, should be hidden

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_visible_when_public_only_false
    # Verifies that when public_only is set to false, private methods are included in
    # the exported markdown, ensuring the export function correctly respects the
    # visibility configuration.
    def test_private_methods_visible_when_public_only_false(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_visible_when_public_only_false::step_0
        # Sets up the test environment by creating a simple graph with the
        # `_make_simple_graph` helper, preparing the data structure to be exported via
        # the markdown exporter.
        md = export_markdown(_make_simple_graph(), public_only=False)
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_private_methods_visible_when_public_only_false::post_0
        # Verifies that the exported markdown contains the private method name
        # `_helper`, confirming that private methods are included when public_only is
        # set to false.
        assert "`_helper" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_attributes_section
    # Verifies that the public attributes section is correctly generated in the Markdown
    # export, ensuring the completeness and accuracy of exported documentation for code
    # under test.
    def test_public_attributes_section(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_attributes_section::step_0
        # Executes the markdown export function on a simple graph to produce a Markdown
        # string for subsequent validation.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_attributes_section::post_0
        # Confirms that the exported Markdown includes the '**Public attributes:**'
        # section header, verifying the section is generated when attributes are
        # present.
        assert "**Public attributes:**" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_public_attributes_section::post_1
        # Verifies that a specific public attribute, 'precision: int' with its
        # description 'Decimal precision', appears correctly formatted in the Markdown
        # output, ensuring attribute details are properly exported.
        assert "`precision: int` — Decimal precision" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_implements_inline
    # Verifies that the markdown export correctly handles inline code elements to ensure
    # inline formatting is preserved in the exported output.
    def test_implements_inline(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_implements_inline::step_0
        # Calls the export function with a simple test graph to generate the Markdown
        # string that will be verified in the assertions.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_implements_inline::post_0
        # Confirms that the exported Markdown correctly lists the implemented interface
        # `ICalculator` under the 'Implements' section, ensuring the code's contractual
        # relationships are documented as expected.
        assert "**Implements:** `calc::ICalculator`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_inherits_from_inline
    # Verifies that the Markdown export correctly handles a class node that inherits
    # from an inline-syntax class, ensuring the generated documentation reflects proper
    # inheritance relationships for non-composite nodes.
    def test_inherits_from_inline(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_inherits_from_inline::step_0
        # Executes the markdown export function on the graph and stores the result,
        # advancing the test from setup to the point of generating output for assertion.
        base = ClassNode(name="Animal", kind="class", source="test",
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class", source="test",
                           qualified_name="Dog", tags=["design"])
        derived_entry = CompositeEntry(
            node=derived,
            references=[("INHERITS_FROM", "Animal", "ClassNode")],
        )
        graph = _KeyedLayerGraph(tags=frozenset({"design"}), entries={
            "Animal": CompositeEntry(node=base),
            "Dog": derived_entry,
        })
        md = export_markdown(graph)
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_inherits_from_inline::post_0
        # Checks that the exported markdown contains the string '**Inherits from:**
        # `Animal`', ensuring inheritance relationships are correctly rendered in the
        # markdown output.
        assert "**Inherits from:** `Animal`" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_values_section
    # Verifies that the export_markdown function correctly processes the
    # enum_values_section within a simple graph, ensuring enum values are accurately
    # rendered.
    def test_enum_values_section(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_values_section::step_0
        # Sets up the test environment by initializing the necessary state or calling
        # the code under test, typically by invoking the function that generates
        # Markdown from a graph containing an enum type.
        md = export_markdown(_make_simple_graph())
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_values_section::post_0
        # Checks that the Markdown output contains the section header '**Values:**',
        # ensuring that the enum values subsection is present in the generated
        # documentation.
        assert "**Values:**" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_values_section::post_1
        # Verifies that the Markdown output includes the documentation comment for the
        # 'ADD' enum value, confirming that each enum member's description is properly
        # exported in the values list.
        assert "`ADD` — Addition operation" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_enum_values_section::post_2
        # Asserts that the Markdown output includes the description for the 'SUBTRACT'
        # enum value, validating that both enum members are correctly listed with their
        # respective comments in the export.
        assert "`SUBTRACT` — Subtraction operation" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_relationships_section
    # Validates that the 'relationships' section of a Markdown export correctly renders
    # dependencies between code elements, ensuring generated documentation accurately
    # represents the codebase's architecture for downstream users.
    def test_relationships_section(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_relationships_section::step_0
        # Performs the setup of the graph with all necessary nodes and entries, then
        # calls export_markdown to generate the Markdown string, preparing the output
        # for assertion checks.
        ns = NamespaceNode(name="ns", kind="namespace", source="test",
                           qualified_name="ns", tags=["design"])
        a = ClassNode(name="A", kind="class", source="test",
                      qualified_name="ns::A", tags=["design"])
        b = ClassNode(name="B", kind="class", source="test",
                      qualified_name="ns::B", tags=["design"])
        a_entry = CompositeEntry(
            node=a,
            references=[("DEPENDS_ON", "ns::B", "ClassNode")],
        )
        ns_entry = CompositeEntry(
            node=ns,
            children={"ClassNode": {
                "ns::A": a_entry,
                "ns::B": CompositeEntry(node=b),
            }},
        )
        graph = _KeyedLayerGraph(tags=frozenset({"design"}), entries={"ns": ns_entry})
        md = export_markdown(graph)
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_relationships_section::post_0
        # Verifies that the exported Markdown includes a '## Relationships' heading,
        # confirming that the relationships section is present and correctly structured.
        assert "## Relationships" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_relationships_section::post_1
        # Verifies that the exported Markdown contains the '**depends_on**' bold text,
        # ensuring that dependency relationships are correctly formatted and included in
        # the relationships section.
        assert "**depends_on**" in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_no_refid_in_output
    # This test verifies that the generated markdown does not contain any 'refid'
    # attributes, ensuring that the export function produces clean, reference-free
    # output for correct downstream processing.
    def test_no_refid_in_output(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_no_refid_in_output::step_0
        # Sets up the test environment by creating a simple graph and exporting it to
        # Markdown, which provides the output that will be inspected.
        md = export_markdown(_make_simple_graph(), fields="all")
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_no_refid_in_output::post_0
        # Verifies that the exported Markdown output contains no 'refid' attribute,
        # ensuring that the export function does not leak internal identifiers into the
        # final document.
        assert "refid" not in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_empty_graph
    # Verifies that exporting an empty LayerGraph via export_markdown produces correct
    # output (likely an empty or minimal markdown string) and handles the edge case of
    # no layers or content, ensuring robustness and stability of the markdown export
    # functionality.
    def test_empty_graph(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_empty_graph::step_0
        # Executes the export_markdown function with the empty graph, producing the
        # markdown string that will be validated in the subsequent assertions.
        graph = _KeyedLayerGraph(tags=frozenset({"design"}))
        md = export_markdown(graph)
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_empty_graph::post_0
        # Confirms that the markdown output includes the '# codegraph: design' header,
        # verifying that the export function correctly generates the expected document
        # structure even for an empty graph.
        assert "# codegraph: design" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_empty_graph::post_1
        # Verifies that the '## Relationships' section is absent from the output,
        # ensuring that the export correctly omits relationship content when the graph
        # has no connections.
        assert "## Relationships" not in md

    # codegraph:test-desc test_markdown.TestMarkdownExport.test_fields_all_shows_properties
    # This test verifies that the markdown export function produces all relevant fields
    # and properties from a simple graph, ensuring the exported content is complete and
    # correctly represents the graph structure.
    def test_fields_all_shows_properties(self):
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_fields_all_shows_properties::step_0
        # Sets up the test by creating a simple graph with 'add' and 'precision' fields,
        # preparing the data for markdown export.
        md = export_markdown(_make_simple_graph(), fields="all")
        # fields="all" still shows signatures (same as default now)
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_fields_all_shows_properties::post_0
        # Checks that the exported markdown contains the function signature 'add(int a,
        # int b): int', confirming that function definitions are properly included in
        # the output.
        assert "`add(int a, int b): int`" in md
        # codegraph:test-desc test_markdown.TestMarkdownExport.test_fields_all_shows_properties::post_1
        # Verifies that the exported markdown includes the property precision field,
        # ensuring that object properties are correctly rendered alongside functions.
        assert "`precision: int`" in md


# ── Import ──────────────────────────────────────────────────────────────────


class TestMarkdownImport:
    """Tests for the new Markdown import format."""

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_empty
    # Verifies that the `import_markdown` function correctly handles an empty input,
    # returning an empty result or appropriate default, which is important to ensure the
    # function does not raise errors and behaves robustly when no content is provided.
    def test_import_empty(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_empty::step_0
        # Sets up the test by calling import_markdown with an empty input to ensure the
        # function can handle and successfully process an empty Markdown document
        # without errors.
        graph = import_markdown("# codegraph: design\n")
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_empty::post_0
        # Verifies that the output of import_markdown is a LayerGraph object, confirming
        # the function returns the expected data structure for an empty input.
        assert isinstance(graph, LayerGraph)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_empty::post_1
        # Checks that the LayerGraph returned contains no entries, ensuring that an
        # empty Markdown document is correctly parsed into an empty graph structure.
        assert len(graph.entries) == 0

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace
    # Verifies that importing Markdown correctly creates the expected namespace
    # structure, ensuring that the import function reliably organizes and groups
    # Markdown content into a usable format.
    def test_import_namespace(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace::step_0
        # Sets up the initial conditions for the test, likely creating or preparing the
        # markdown content and import structure needed for namespace extraction.
        md = "## Namespace: `calc`\n"
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace::post_0
        # Checks that a specific key or identifier is present within the namespace,
        # ensuring the imported markdown correctly includes the expected named elements.
        assert "calc" in graph.entries
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace::step_1
        # Executes the core action of importing markdown content, invoking the
        # `import_markdown` function to process the prepared data and produce the
        # resulting node structure.
        node = graph.entries["calc"].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace::post_1
        # Verifies that the returned object is a `NamespaceNode`, confirming that the
        # markdown import correctly interprets the structure as defining a namespace
        # rather than a simple function or class.
        assert isinstance(node, NamespaceNode)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_namespace::post_2
        # Validates that the imported namespace node contains exactly the expected set
        # of attributes or children, confirming the full and correct interpretation of
        # the markdown content.
        assert node.qualified_name == "calc"

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname
    # Verifies that the import_markdown function correctly processes a Markdown file
    # containing a class with a fully qualified name, ensuring the output accurately
    # reflects the class's qualified name for proper code documentation generation.
    def test_import_class_with_qname(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::step_0
        # Sets up the test environment by importing a class from a Markdown file with a
        # fully qualified name, preparing the data needed for subsequent assertions.
        md = "### Class: `calc::Engine`\n"
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::post_0
        # Verifies that the imported node's qualified name contains the expected string
        # component, confirming correct namespace resolution.
        assert "calc::Engine" in graph.entries
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::step_1
        # Calls the import_markdown function to import a class specified by its
        # qualified name, advancing the test by executing the code under test.
        node = graph.entries["calc::Engine"].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::post_1
        # Asserts that the imported object is an instance of ClassNode, ensuring the
        # import function correctly represents the class as a ClassNode in the code
        # graph.
        assert isinstance(node, ClassNode)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::post_2
        # Checks that the node's name attribute equals the expected class name, ensuring
        # the class is correctly identified.
        assert node.qualified_name == "calc::Engine"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_class_with_qname::post_3
        # Verifies that the node's module attribute points to the correct module,
        # confirming the import maps the class to its proper source module.
        assert node.name == "Engine"

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_interface
    # Verifies that the import_markdown function correctly converts a Markdown file into
    # its expected internal interface, ensuring the exported format can be reliably
    # parsed back into the code graph data structure.
    def test_import_interface(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_interface::step_0
        # Sets up the test by preparing any necessary data or context for importing a
        # markdown file that describes an interface, ensuring that the import function
        # can be executed correctly.
        md = "### Interface: `ns::IWidget`\n"
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_interface::post_0
        # Checks that the identifier 'ns::IWidget' exists as an entry in the imported
        # graph, ensuring that the markdown import process successfully registers
        # interface elements.
        assert "ns::IWidget" in graph.entries
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_interface::post_1
        # Verifies that the imported markdown correctly represents an interface node
        # (InterfaceNode) for 'IWidget' in the namespace 'ns', confirming that the
        # import function properly identifies and structures interface definitions.
        assert isinstance(graph.entries["ns::IWidget"].node, InterfaceNode)

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values
    # Verifies that the import_markdown function correctly processes markdown containing
    # enumerated values, ensuring that mappings between labels and values are accurately
    # imported and represented in the generated code graph.
    def test_import_enum_with_values(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values::step_0
        # Sets up the necessary test environment or data structures (e.g., imports or
        # initializes the markdown content) so that the import operation can be
        # performed on a valid input.
        md = (
            "### Enum: `Color`\n"
            "**Values:**\n"
            "- `RED`\n"
            "- `BLUE`\n"
        )
        graph = import_markdown(md)
        entry = graph.entries["Color"]
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values::post_0
        # Confirms that each node in the imported result is an instance of `EnumNode`,
        # ensuring the markdown parser correctly interprets enum definitions as the
        # expected node type.
        assert isinstance(entry.node, EnumNode)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values::post_1
        # Checks that specific expected values (e.g., enum member names) appear in the
        # parsed output, verifying that the enum values from the markdown are correctly
        # extracted and stored.
        assert "EnumValueNode" in entry.children
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values::step_1
        # Executes the core import operation by calling `import_markdown` with the
        # prepared markdown content, producing the parsed result that will be verified
        # by subsequent assertions.
        vals = list(entry.children["EnumValueNode"].values())
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_import_enum_with_values::post_2
        # Verifies the total number of values extracted equals 2, confirming that the
        # markdown import handles the exact count of enum entries without missing or
        # duplicating any.
        assert len(vals) == 2

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_class_inside_namespace
    # Verifies that a class defined inside a namespace is correctly parsed and
    # represented when importing markdown, ensuring that namespace scoping is not lost
    # during the import process.
    def test_class_inside_namespace(self):
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_class_inside_namespace::step_0
        # Prepares the initial state by setting up necessary inputs or environment for
        # importing markdown content that contains a class inside a namespace.
        md = (
            "## Namespace: `calc`\n\n"
            "### Class: `calc::Engine`\n"
        )
        graph = import_markdown(md)
        pkg = graph.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_class_inside_namespace::post_0
        # Verifies that the first expected attribute or structure of the imported class
        # inside the namespace is correct, ensuring the parser correctly handles
        # namespace nesting.
        assert cls.qualified_name == "calc::Engine"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_class_inside_namespace::post_1
        # Verifies that a second key attribute or structure of the imported class inside
        # the namespace matches expectations, confirming the complete and accurate
        # import of scoped class definitions.
        assert cls.name == "Engine"

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes
    # Verifies that the import_markdown function correctly processes markdown content to
    # produce expected methods and attributes on the resulting code object.
    def test_methods_and_attributes(self):
        md = (
            "## Namespace: `ns`\n\n"
            "### Class: `ns::Widget`\n"
            "**Public methods:**\n"
            "- `doWork(int x): bool` — Does work\n"
            "**Public attributes:**\n"
            "- `count: int` — Item count\n"
        )
        graph = import_markdown(md)
        pkg = graph.entries["ns"]
        widget = list(pkg.children["ClassNode"].values())[0]

        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_0
        # Validates that a particular method or attribute name is present in the
        # imported results, ensuring the Markdown importer correctly identifies all
        # expected elements.
        assert "MethodNode" in widget.children
        meth = list(widget.children["MethodNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_1
        # Asserts that the imported element from the Markdown is an instance of
        # MethodNode, confirming that methods are correctly classified as such during
        # import.
        assert isinstance(meth, MethodNode)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_2
        # Verifies that a property of the first imported method (e.g., its name) equals
        # the expected value, ensuring the method's basic identity is correct.
        assert meth.name == "doWork"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_3
        # Checks that a method property (e.g., multiplicity or return type) matches the
        # expected value, verifying the method's complete specification was imported
        # correctly.
        assert meth.type_signature == "bool"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_4
        # Checks that a property of one of the imported methods (e.g., its name or
        # signature) matches the expected value, confirming the method was properly
        # extracted from the Markdown.
        assert meth.argsstring == "(int x)"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_5
        # Confirms that another property of the imported method or attribute equals the
        # expected value, further validating the accuracy of the Markdown importer.
        assert meth.brief_description == "Does work"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_6
        # Verifies that a property of a method (e.g., its binding or access level)
        # matches the expected value, ensuring the method's metadata is accurately
        # imported.
        assert meth.qualified_name == "ns::Widget::doWork"

        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_7
        # Confirms that a specific value (e.g., an attribute name) is contained in the
        # set of imported attributes, verifying that the attribute was successfully
        # extracted.
        assert "AttributeNode" in widget.children
        attr = list(widget.children["AttributeNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_8
        # Asserts that the imported element is an instance of AttributeNode, ensuring
        # attributes are correctly identified as such by the import process.
        assert isinstance(attr, AttributeNode)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_9
        # Verifies that a specific attribute property (e.g., value, name) matches an
        # expected value, ensuring the markdown import correctly parses and represents
        # attributes as AttributeNode objects.
        assert attr.name == "count"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_10
        # Ensures that a final attribute property (e.g., a string field) matches the
        # expected value, completing the verification of the attribute's correct
        # reconstruction.
        assert attr.type_signature == "int"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_methods_and_attributes::post_11
        # Checks that a further attribute property (e.g., a boolean flag) equals the
        # expected value, confirming detailed attribute metadata is correctly parsed.
        assert attr.brief_description == "Item count"

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_member_without_description
    # Verifies that `import_markdown` correctly handles members without descriptions,
    # ensuring that the export process does not fail or produce unexpected output for
    # such members, which is important for the robustness of markdown import
    # functionality.
    def test_member_without_description(self):
        md = (
            "### Class: `A`\n"
            "**Public methods:**\n"
            "- `start`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["A"]
        meth = list(cls.children["MethodNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_member_without_description::post_0
        # Verifies that the import process correctly captures the member’s name,
        # ensuring that the member is recognized even when it lacks a description.
        assert meth.name == "start"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_member_without_description::post_1
        # Verifies that the import process assigns an appropriate default or empty
        # description to the member, confirming that missing descriptions are handled
        # gracefully without causing errors.
        assert meth.brief_description == ""

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_inline_inherits_from
    # Verifies that inline inheritance relationships within markdown content are
    # correctly parsed by import_markdown, ensuring the integrity of dependency mapping
    # for exported graph structures.
    def test_inline_inherits_from(self):
        md = (
            "### Class: `Animal`\n"
            "### Class: `Dog`\n"
            "**Inherits from:** `Animal`\n"
        )
        graph = import_markdown(md)
        dog = graph.entries["Dog"]
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_inline_inherits_from::post_0
        # Verifies that the imported dog object correctly records an 'INHERITS_FROM'
        # relationship to 'Animal', confirming that inline inheritance relationships in
        # the Markdown source are properly extracted.
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_inline_implements
    # Verifies that the import_markdown function correctly interprets inline code
    # elements when importing markdown, ensuring that code blocks and inline code are
    # properly parsed and represented in the resulting structure.
    def test_inline_implements(self):
        md = (
            "### Interface: `I`\n"
            "### Class: `C`\n"
            "**Implements:** `I`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["C"]
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_inline_implements::post_0
        # Verifies that at least one reference in the imported class is a 'REALIZES'
        # relation to interface 'I', ensuring the markdown correctly captured the
        # implementation relationship.
        assert any(r[0] == "REALIZES" and r[1] == "I"
                    for r in cls.references)

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_relationships_section
    # This test validates that the `import_markdown` function correctly processes and
    # imports the 'Relationships' section from a Markdown file, ensuring that important
    # relationship data between code elements is accurately captured and made available
    # for further analysis.
    def test_relationships_section(self):
        md = (
            "### Class: `A`\n"
            "### Class: `B`\n"
            "## Relationships\n"
            "- `A` → `B` **depends_on**\n"
        )
        graph = import_markdown(md)
        a = graph.entries["A"]
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_relationships_section::post_0
        # Verifies that at least one reference from element 'a' is a 'DEPENDS_ON'
        # relationship targeting element 'B', confirming that the import correctly
        # captures explicit code dependencies from the markdown.
        assert any(r[0] == "DEPENDS_ON" and r[1] == "B" for r in a.references)

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_description_becomes_brief
    # Verifies that the import_markdown function correctly sets the description field of
    # a test node to its brief form, which is crucial for ensuring that the metadata
    # extraction preserves the intended level of detail.
    def test_description_becomes_brief(self):
        md = (
            "### Class: `Engine`\n"
            "Core engine class.\n"
        )
        graph = import_markdown(md)
        node = graph.entries["Engine"].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_description_becomes_brief::post_0
        # Verifies that after importing the Markdown file, the description attribute in
        # the resulting code graph object matches the expected brief string, ensuring
        # that the import process correctly translates Markdown descriptions into the
        # code graph representation.
        assert node.brief_description == "Core engine class."

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_file_notes
    # Verifies that the import_markdown function correctly imports file-level notes from
    # a Markdown file, ensuring that metadata is preserved and accessible for downstream
    # processing.
    def test_file_notes(self):
        md = (
            "## File Notes\n"
            "- `widget.h`\n"
            "- `widget.cpp`\n"
        )
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_file_notes::post_0
        # Checks that 'widget.h' is present in the graph entries, confirming the import
        # operation successfully parsed and added the file reference.
        assert "widget.h" in graph.entries
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_file_notes::post_1
        # Verifies that the imported markdown file 'widget.h' is recognized as a
        # FileNode, ensuring the parser correctly identifies file entries.
        assert isinstance(graph.entries["widget.h"].node, FileNode)

    # codegraph:test-desc test_markdown.TestMarkdownImport.test_all_members_imported_as_public
    # Verifies that all expected members are correctly imported as public when using the
    # import_markdown function, ensuring completeness and correctness of the import
    # operation.
    def test_all_members_imported_as_public(self):
        md = (
            "### Class: `A`\n"
            "**Public methods:**\n"
            "- `foo`\n"
            "**Public attributes:**\n"
            "- `bar`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["A"]
        meth = list(cls.children["MethodNode"].values())[0].node
        attr = list(cls.children["AttributeNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_all_members_imported_as_public::post_0
        # Checks that the imported module's public members list has the expected size,
        # confirming that all intended members are accounted for during import.
        assert meth.visibility == "public"
        # codegraph:test-desc test_markdown.TestMarkdownImport.test_all_members_imported_as_public::post_1
        # Verifies that a specific public member from the markdown module is correctly
        # recognized as imported, ensuring the import logic behaves as expected.
        assert attr.visibility == "public"


# ── Export → Import round-trip ───────────────────────────────────────────────


class TestMarkdownRoundTrip:
    """Tests for export→import round-trip fidelity."""

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_simple_graph
    # Verifies that a simple graph created by _make_simple_graph can be exported to
    # Markdown and then re-imported without any loss of structure or content, ensuring
    # that the import and export functions are consistent and reliable.
    def test_round_trip_simple_graph(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_simple_graph::post_0
        # Verifies that the first expected element or relationship from the original
        # graph is present in the imported result, ensuring that key data survives the
        # round trip.
        assert "calc" in restored.entries
        pkg = restored.entries["calc"]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_simple_graph::post_1
        # Verifies that the second expected element or relationship from the original
        # graph is present in the imported result, checking that the round-trip process
        # does not lose intermediate data.
        assert "ClassNode" in pkg.children
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_simple_graph::post_2
        # Verifies that the third expected element or relationship from the original
        # graph is present in the imported result, confirming that the round-trip
        # preserves this piece of information.
        assert "InterfaceNode" in pkg.children
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_simple_graph::post_3
        # Verifies that the fourth expected element or relationship from the original
        # graph is present in the imported result, ensuring complete fidelity of the
        # round-trip for this test case.
        assert "EnumNode" in pkg.children

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_public_members
    # Verifies that exporting a simple graph to Markdown and importing it back preserves
    # the graph's structure and public member data, ensuring the Markdown serialization
    # round-trip is lossless and reliable for data integrity.
    def test_round_trip_public_members(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_public_members::post_0
        # Verifies that a method named 'add' is present in the list of public members
        # after the round trip, confirming that public members are correctly exported
        # and reimported.
        assert "MethodNode" in cls.children
        meths = list(cls.children["MethodNode"].values())
        # Only public methods survive round-trip (public_only=True default)
        meth_names = [e.node.name for e in meths]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_public_members::post_1
        # Asserts that the method 'add' appears in the imported method names, ensuring
        # that this specific public member is retained through the export-import
        # process.
        assert "add" in meth_names
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_public_members::post_2
        # Checks that a private helper method '_helper' is not included in the imported
        # method names, verifying that the round-trip correctly filters out non-public
        # members.
        assert "_helper" not in meth_names  # private, not exported

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_all_members_when_public_only_false
    # Verifies that exporting and re-importing all members (including private ones) of a
    # simple graph preserves the original graph structure, ensuring the round-trip
    # conversion works correctly with public_only set to False.
    def test_round_trip_all_members_when_public_only_false(self):
        graph = _make_simple_graph()
        md = export_markdown(graph, public_only=False)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        meth_names = [e.node.name for e in cls.children["MethodNode"].values()]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_all_members_when_public_only_false::post_0
        # Verifies that the public method 'add' is present in the imported member names,
        # confirming that public functions are not omitted during export and import.
        assert "add" in meth_names
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_all_members_when_public_only_false::post_1
        # Verifies that the private method '_helper' is present in the imported member
        # names, confirming that when public_only is false, private functions are also
        # preserved during round-trip conversion.
        assert "_helper" in meth_names  # private now visible

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_inline_relationships
    # Verifies that exporting a simple graph to Markdown and then importing it back
    # produces the same graph, ensuring the export and import functions are inverse
    # operations.
    def test_round_trip_inline_relationships(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_inline_relationships::post_0
        # Verifies that the imported graph contains at least one 'REALIZES'
        # relationship, ensuring that the export and import process correctly handles
        # and retains inline relationship types.
        assert any(r[0] == "REALIZES" for r in cls.references)

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_inheritance
    # Verifies that exporting and then importing a class hierarchy containing
    # inheritance relationships preserves the structure, ensuring the round-trip
    # conversion maintains the correctness of the object model.
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
        graph = _KeyedLayerGraph(tags=frozenset({"design"}), entries={
            "Animal": base_entry,
            "Dog": derived_entry,
        })
        md = export_markdown(graph)
        restored = import_markdown(md)
        dog = restored.entries["Dog"]
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_inheritance::post_0
        # Verifies that after the round-trip, the derived class node (dog) retains an
        # 'INHERITS_FROM' reference to the base class (Animal). This confirms that
        # inheritance metadata is correctly preserved through markdown serialization and
        # deserialization.
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)

    # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_descriptions
    # Verifies that exporting a graph to Markdown and then re-importing it yields the
    # original graph data, ensuring the export and import functions are consistent and
    # trustworthy for preserving structural integrity.
    def test_round_trip_descriptions(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0].node
        # codegraph:test-desc test_markdown.TestMarkdownRoundTrip.test_round_trip_descriptions::post_0
        # Verifies that the brief description 'Core engine handling arithmetic' is
        # preserved after the round-trip export/import, confirming that description
        # fields are correctly transferred through the Markdown serialization process.
        assert "Core engine handling arithmetic" in (cls.brief_description or "")


# ── Unified format entry point ──────────────────────────────────────────────


class TestUnifiedFormat:
    # codegraph:test-desc test_markdown.TestUnifiedFormat.test_export_format_markdown
    # Verifies that exporting a simple graph as Markdown produces output in the expected
    # unified format, ensuring the Markdown exporter functions correctly for basic graph
    # structures.
    def test_export_format_markdown(self):
        md = export_graph(_make_simple_graph(), format="markdown")
        # codegraph:test-desc test_markdown.TestUnifiedFormat.test_export_format_markdown::post_0
        # Verifies that the exported markdown contains a heading for the code graph
        # design, ensuring the export function correctly formats the graph structure.
        assert "# codegraph: design" in md

    # codegraph:test-desc test_markdown.TestUnifiedFormat.test_export_format_md_alias
    # Verifies that the 'export_graph' function correctly handles the Markdown format
    # alias (e.g., 'md' instead of 'markdown') and exports a simple graph as expected,
    # ensuring flexibility in format specification.
    def test_export_format_md_alias(self):
        md = export_graph(_make_simple_graph(), format="md")
        # codegraph:test-desc test_markdown.TestUnifiedFormat.test_export_format_md_alias::post_0
        # Verifies that the exported Markdown contains the expected header '# codegraph:
        # design', ensuring the export format correctly uses the specified alias to
        # produce valid Markdown output.
        assert "# codegraph: design" in md

    # codegraph:test-desc test_markdown.TestUnifiedFormat.test_import_format_markdown
    # Verifies that the import_graph function correctly produces markdown-formatted
    # output, ensuring the export functionality generates valid and consistent markdown
    # for downstream consumption.
    def test_import_format_markdown(self):
        graph = import_graph("## Namespace: `x`\n", format="markdown")
        # codegraph:test-desc test_markdown.TestUnifiedFormat.test_import_format_markdown::post_0
        # Verifies that the imported graph contains a specific key, confirming that the
        # Markdown import format correctly parsed and stored the expected structural
        # element.
        assert "x" in graph.entries

    # codegraph:test-desc test_markdown.TestUnifiedFormat.test_unknown_format_raises
    # Verifies that the export_graph function raises an error when given an unsupported
    # format, ensuring proper error handling in the LayerGraph export process.
    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            export_graph(_KeyedLayerGraph(tags=frozenset({"design"})), format="csv")


# ── Diagnostics ────────────────────────────────────────────────────────────


class TestMarkdownDiagnostics:
    # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_valid_document_no_diagnostics
    # This test verifies that importing a valid Markdown document via
    # MarkdownImporter.import_markdown produces no diagnostic warnings or errors,
    # ensuring correct import behavior and data integrity.
    def test_valid_document_no_diagnostics(self):
        importer = MarkdownImporter()
        md = "## Namespace: `ns`\n\n### Class: `ns::A`\n**Public methods:**\n- `x`\n"
        importer.import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_valid_document_no_diagnostics::post_0
        # Verifies that no diagnostics were generated after importing a valid Markdown
        # document, confirming the importer correctly identifies well-formed content and
        # does not raise false alarms.
        assert len(importer.diagnostics) == 0

    # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_dangling_relationship_source
    # Verifies that the MarkdownImporter correctly identifies and reports a relationship
    # referencing a nonexistent source node, ensuring diagnostics accurately flag
    # structural integrity issues in imported relationships.
    def test_dangling_relationship_source(self):
        importer = MarkdownImporter()
        md = "### Class: `A`\n## Relationships\n- `B` → `A` **depends_on**\n"
        importer.import_markdown(md)
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_dangling_relationship_source::post_0
        # Verifies that at least one diagnostic error was produced, confirming the
        # importer correctly identifies dangling (unresolvable) relationship sources in
        # the markdown.
        assert len(errors) >= 1

    # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_dangling_relationship_target
    # Verifies that the MarkdownImporter correctly detects and reports a dangling
    # relationship target, ensuring import failures are properly diagnosed.
    def test_dangling_relationship_target(self):
        importer = MarkdownImporter()
        md = "### Class: `A`\n## Relationships\n- `A` → `B` **depends_on**\n"
        importer.import_markdown(md)
        errors = [d for d in importer.diagnostics if d.severity == "warning"]
        # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_dangling_relationship_target::post_0
        # Ensures that at least one diagnostic warning is reported when a dangling
        # relationship target exists, validating that the importer correctly identifies
        # broken references (now stored as warnings so cross-document references can
        # be resolved at Neo4j persist time).
        assert len(errors) >= 1

    # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_strict_mode_raises
    # Verifies that the import_markdown function raises an error when started in strict
    # mode, which is important to ensure the code correctly enforces input validation
    # constraints.
    def test_strict_mode_raises(self):
        with pytest.raises(PlantUMLParseError):
            import_markdown(
                "### Class: `A`\n## Relationships\n- `B` → `A` **depends_on**\n",
                strict=True,
            )

    # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_convenience_function_tags
    # Verifies that convenience function tags within markdown are correctly recognized
    # during import, ensuring accurate metadata extraction for downstream code graph
    # analysis.
    def test_convenience_function_tags(self):
        md = "### Class: `A`\n"
        graph = import_markdown(md, tags=frozenset({"as-built"}))
        # codegraph:test-desc test_markdown.TestMarkdownDiagnostics.test_convenience_function_tags::post_0
        # Verifies that the node representing entry 'A' in the graph has the expected
        # 'as-built' tag, confirming that the markdown import correctly assigned that
        # tag.
        assert graph.entries["A"].node.has_tag("as-built")


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestMarkdownEdgeCases:
    # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_alternative_keyword_namespace
    # Verifies that when an alternative keyword (e.g., 'namespace') is provided during
    # import, the system can correctly parse and represent code with that keyword,
    # ensuring flexibility in handling different programming language syntaxes.
    def test_alternative_keyword_namespace(self):
        md = "## Namespace: `calc`\n"
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_alternative_keyword_namespace::post_0
        # Verifies that the 'calc' entry in the parsed graph is correctly identified as
        # a namespace node, ensuring that alternative keyword namespaces are properly
        # recognized and structured according to the markdown import logic.
        assert isinstance(graph.entries["calc"].node, NamespaceNode)

    # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_tags_default
    # Verifies that the import_markdown function correctly handles default tag values
    # when no tags are specified, ensuring proper default behavior for edge cases.
    def test_tags_default(self):
        md = "### Class: `A`\n"
        graph = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_tags_default::post_0
        # Verifies that the node 'A' in the imported graph has been correctly assigned
        # the 'design' tag, ensuring that tag propagation from markdown to graph nodes
        # works as intended.
        assert graph.entries["A"].node.has_tag("design")

    # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_empty_sections
    # Verifies that the import_markdown function correctly handles markdown inputs where
    # a heading has no subsequent content, ensuring that the parser does not crash or
    # produce erroneous nodes when encountering empty sections.
    def test_empty_sections(self):
        md = (
            "### Class: `A`\n"
            "**Public methods:**\n"
            "\n"
            "**Public attributes:**\n"
            "- `x`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["A"]
        # Attributes should parse even though methods section is empty
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_empty_sections::post_0
        # Verifies that the output of import_markdown contains an empty section,
        # ensuring the function correctly processes and preserves empty Markdown
        # sections without error.
        assert "AttributeNode" in cls.children

    # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_convenience_functions
    # Validates that the convenience functions import_markdown and export_markdown, when
    # used together with _make_simple_graph, correctly handle edge cases by preserving
    # the graph structure and data, ensuring the round-trip conversion is lossless for
    # boundary inputs.
    def test_convenience_functions(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_convenience_functions::post_0
        # Checks that the exported Markdown contains the expected heading '# codegraph:
        # design', confirming the graph structure is correctly serialized with its
        # design label.
        assert "# codegraph: design" in md
        restored = import_markdown(md)
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_convenience_functions::post_1
        # Verifies that the imported graph contains the node from the original simple
        # graph, ensuring that round-trip conversion preserves the graph's content
        # without loss.
        assert "calc" in restored.entries

    # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_fields_all_export_roundtrip
    # This test verifies that exporting a simple graph to markdown and then reimporting
    # it preserves all fields correctly, ensuring data integrity in the roundtrip
    # conversion process.
    def test_fields_all_export_roundtrip(self):
        graph = _make_simple_graph()
        md = export_markdown(graph, fields="all")
        # fields="all" includes type signatures inline
        # codegraph:test-desc test_markdown.TestMarkdownEdgeCases.test_fields_all_export_roundtrip::post_0
        # Verifies that the exported Markdown contains the string '`add(int a, int b):
        # int`', confirming accurate field representation. This ensures that the export
        # function correctly includes function signatures with their parameters and
        # return types.
        assert "`add(int a, int b): int`" in md