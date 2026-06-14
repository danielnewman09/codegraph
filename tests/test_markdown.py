"""Tests for Markdown export and import (text-based, public-only by default).

Covers export_markdown, import_markdown, qualified-name-from-heading,
inline relationship properties, round-trip, and diagnostics.
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.markdown import (
    export_markdown,
    import_markdown,
    MarkdownExporter,
    MarkdownImporter,
)
from codegraph.plantuml import PlantUMLParseError, ParseDiagnostic
from codegraph.format import export_graph, import_graph

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_simple_graph() -> LayerGraph:
    """Small graph with namespace, class, methods, attributes, interface, enum."""
    ns = NamespaceNode(name="calc", kind="namespace", qualified_name="calc",
                       tags=["design"])
    cls = ClassNode(name="CalculatorEngine", kind="class",
                    qualified_name="calc::CalculatorEngine",
                    tags=["design"], visibility="public",
                    brief_description="Core engine handling arithmetic.")
    iface = InterfaceNode(name="ICalculator", kind="interface",
                          qualified_name="calc::ICalculator",
                          tags=["design"], visibility="public",
                          brief_description="Calculator contract.")
    meth = MethodNode(name="add", kind="method",
                      qualified_name="calc::CalculatorEngine::add",
                      tags=["design"], visibility="public",
                      brief_description="Performs addition.",
                      type_signature="int", argsstring="(int a, int b)")
    meth2 = MethodNode(name="_helper", kind="method",
                       qualified_name="calc::CalculatorEngine::_helper",
                       tags=["design"], visibility="private",
                       brief_description="Internal helper.")
    attr = AttributeNode(name="precision", kind="attribute",
                         qualified_name="calc::CalculatorEngine::precision",
                         tags=["design"], visibility="public",
                         type_signature="int",
                         brief_description="Decimal precision.")
    op_enum = EnumNode(name="Operation", kind="enum",
                       qualified_name="calc::Operation",
                       tags=["design"], visibility="public",
                       brief_description="Supported operations.")
    add_val = EnumValueNode(name="ADD", kind="enumvalue",
                            qualified_name="calc::Operation::ADD",
                            tags=["design"],
                            brief_description="Addition operation.")
    sub_val = EnumValueNode(name="SUBTRACT", kind="enumvalue",
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
    return LayerGraph(tags=frozenset({"design"}), entries={"calc": ns_entry})


# ── Export ──────────────────────────────────────────────────────────────────


class TestMarkdownExport:
    """Tests for the new text-based Markdown export format."""

    def test_header_with_tags(self):
        md = export_markdown(_make_simple_graph())
        assert md.startswith("# codegraph: design\n")

    def test_namespace_heading(self):
        md = export_markdown(_make_simple_graph())
        assert "## Namespace: `calc`" in md

    def test_class_heading_with_qname(self):
        md = export_markdown(_make_simple_graph())
        assert "### Class: `calc::CalculatorEngine`" in md

    def test_interface_heading(self):
        md = export_markdown(_make_simple_graph())
        assert "### Interface: `calc::ICalculator`" in md

    def test_enum_heading(self):
        md = export_markdown(_make_simple_graph())
        assert "### Enum: `calc::Operation`" in md

    def test_class_description_as_text(self):
        md = export_markdown(_make_simple_graph())
        # Description is plain text right after heading
        idx = md.index("calc::CalculatorEngine`")
        tail = md[idx:]
        assert "Core engine handling arithmetic" in tail

    def test_public_methods_section(self):
        md = export_markdown(_make_simple_graph())
        assert "**Public methods:**" in md
        assert "`add(int a, int b): int` — Performs addition" in md

    def test_private_methods_hidden_by_default(self):
        md = export_markdown(_make_simple_graph())
        assert "`_helper" not in md  # private, should be hidden

    def test_private_methods_visible_when_public_only_false(self):
        md = export_markdown(_make_simple_graph(), public_only=False)
        assert "`_helper" in md

    def test_public_attributes_section(self):
        md = export_markdown(_make_simple_graph())
        assert "**Public attributes:**" in md
        assert "`precision: int` — Decimal precision" in md

    def test_implements_inline(self):
        md = export_markdown(_make_simple_graph())
        assert "**Implements:** `calc::ICalculator`" in md

    def test_inherits_from_inline(self):
        base = ClassNode(name="Animal", kind="class",
                        qualified_name="Animal", tags=["design"])
        derived = ClassNode(name="Dog", kind="class",
                           qualified_name="Dog", tags=["design"])
        derived_entry = CompositeEntry(
            node=derived,
            references=[("INHERITS_FROM", "Animal", "ClassNode")],
        )
        graph = LayerGraph(tags=frozenset({"design"}), entries={
            "Animal": CompositeEntry(node=base),
            "Dog": derived_entry,
        })
        md = export_markdown(graph)
        assert "**Inherits from:** `Animal`" in md

    def test_enum_values_section(self):
        md = export_markdown(_make_simple_graph())
        assert "**Values:**" in md
        assert "`ADD` — Addition operation" in md
        assert "`SUBTRACT` — Subtraction operation" in md

    def test_relationships_section(self):
        ns = NamespaceNode(name="ns", kind="namespace",
                           qualified_name="ns", tags=["design"])
        a = ClassNode(name="A", kind="class",
                      qualified_name="ns::A", tags=["design"])
        b = ClassNode(name="B", kind="class",
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
        graph = LayerGraph(tags=frozenset({"design"}), entries={"ns": ns_entry})
        md = export_markdown(graph)
        assert "## Relationships" in md
        assert "**depends_on**" in md

    def test_no_refid_in_output(self):
        md = export_markdown(_make_simple_graph(), fields="all")
        assert "refid" not in md

    def test_empty_graph(self):
        graph = LayerGraph(tags=frozenset({"design"}))
        md = export_markdown(graph)
        assert "# codegraph: design" in md
        assert "## Relationships" not in md

    def test_fields_all_shows_properties(self):
        md = export_markdown(_make_simple_graph(), fields="all")
        # fields="all" still shows signatures (same as default now)
        assert "`add(int a, int b): int`" in md
        assert "`precision: int`" in md


# ── Import ──────────────────────────────────────────────────────────────────


class TestMarkdownImport:
    """Tests for the new Markdown import format."""

    def test_import_empty(self):
        graph = import_markdown("# codegraph: design\n")
        assert isinstance(graph, LayerGraph)
        assert len(graph.entries) == 0

    def test_import_namespace(self):
        md = "## Namespace: `calc`\n"
        graph = import_markdown(md)
        assert "calc" in graph.entries
        node = graph.entries["calc"].node
        assert isinstance(node, NamespaceNode)
        assert node.qualified_name == "calc"

    def test_import_class_with_qname(self):
        md = "### Class: `calc::Engine`\n"
        graph = import_markdown(md)
        assert "calc::Engine" in graph.entries
        node = graph.entries["calc::Engine"].node
        assert isinstance(node, ClassNode)
        assert node.qualified_name == "calc::Engine"
        assert node.name == "Engine"

    def test_import_interface(self):
        md = "### Interface: `ns::IWidget`\n"
        graph = import_markdown(md)
        assert "ns::IWidget" in graph.entries
        assert isinstance(graph.entries["ns::IWidget"].node, InterfaceNode)

    def test_import_enum_with_values(self):
        md = (
            "### Enum: `Color`\n"
            "**Values:**\n"
            "- `RED`\n"
            "- `BLUE`\n"
        )
        graph = import_markdown(md)
        entry = graph.entries["Color"]
        assert isinstance(entry.node, EnumNode)
        assert "EnumValueNode" in entry.children
        vals = list(entry.children["EnumValueNode"].values())
        assert len(vals) == 2

    def test_class_inside_namespace(self):
        md = (
            "## Namespace: `calc`\n\n"
            "### Class: `calc::Engine`\n"
        )
        graph = import_markdown(md)
        pkg = graph.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0].node
        assert cls.qualified_name == "calc::Engine"
        assert cls.name == "Engine"

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

        assert "MethodNode" in widget.children
        meth = list(widget.children["MethodNode"].values())[0].node
        assert isinstance(meth, MethodNode)
        assert meth.name == "doWork"
        assert meth.type_signature == "bool"
        assert meth.argsstring == "(int x)"
        assert meth.brief_description == "Does work"
        assert meth.qualified_name == "ns::Widget::doWork"

        assert "AttributeNode" in widget.children
        attr = list(widget.children["AttributeNode"].values())[0].node
        assert isinstance(attr, AttributeNode)
        assert attr.name == "count"
        assert attr.type_signature == "int"
        assert attr.brief_description == "Item count"

    def test_member_without_description(self):
        md = (
            "### Class: `A`\n"
            "**Public methods:**\n"
            "- `start`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["A"]
        meth = list(cls.children["MethodNode"].values())[0].node
        assert meth.name == "start"
        assert meth.brief_description == ""

    def test_inline_inherits_from(self):
        md = (
            "### Class: `Animal`\n"
            "### Class: `Dog`\n"
            "**Inherits from:** `Animal`\n"
        )
        graph = import_markdown(md)
        dog = graph.entries["Dog"]
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)

    def test_inline_implements(self):
        md = (
            "### Interface: `I`\n"
            "### Class: `C`\n"
            "**Implements:** `I`\n"
        )
        graph = import_markdown(md)
        cls = graph.entries["C"]
        assert any(r[0] == "REALIZES" and r[1] == "I"
                    for r in cls.references)

    def test_relationships_section(self):
        md = (
            "### Class: `A`\n"
            "### Class: `B`\n"
            "## Relationships\n"
            "- `A` → `B` **depends_on**\n"
        )
        graph = import_markdown(md)
        a = graph.entries["A"]
        assert any(r[0] == "DEPENDS_ON" and r[1] == "B" for r in a.references)

    def test_description_becomes_brief(self):
        md = (
            "### Class: `Engine`\n"
            "Core engine class.\n"
        )
        graph = import_markdown(md)
        node = graph.entries["Engine"].node
        assert node.brief_description == "Core engine class."

    def test_file_notes(self):
        md = (
            "## File Notes\n"
            "- `widget.h`\n"
            "- `widget.cpp`\n"
        )
        graph = import_markdown(md)
        assert "widget.h" in graph.entries
        assert isinstance(graph.entries["widget.h"].node, FileNode)

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
        assert meth.visibility == "public"
        assert attr.visibility == "public"


# ── Export → Import round-trip ───────────────────────────────────────────────


class TestMarkdownRoundTrip:
    """Tests for export→import round-trip fidelity."""

    def test_round_trip_simple_graph(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        assert "calc" in restored.entries
        pkg = restored.entries["calc"]
        assert "ClassNode" in pkg.children
        assert "InterfaceNode" in pkg.children
        assert "EnumNode" in pkg.children

    def test_round_trip_public_members(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        assert "MethodNode" in cls.children
        meths = list(cls.children["MethodNode"].values())
        # Only public methods survive round-trip (public_only=True default)
        meth_names = [e.node.name for e in meths]
        assert "add" in meth_names
        assert "_helper" not in meth_names  # private, not exported

    def test_round_trip_all_members_when_public_only_false(self):
        graph = _make_simple_graph()
        md = export_markdown(graph, public_only=False)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
        meth_names = [e.node.name for e in cls.children["MethodNode"].values()]
        assert "add" in meth_names
        assert "_helper" in meth_names  # private now visible

    def test_round_trip_inline_relationships(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0]
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
        md = export_markdown(graph)
        restored = import_markdown(md)
        dog = restored.entries["Dog"]
        assert any(r[0] == "INHERITS_FROM" and r[1] == "Animal"
                    for r in dog.references)

    def test_round_trip_descriptions(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        pkg = restored.entries["calc"]
        cls = list(pkg.children["ClassNode"].values())[0].node
        assert "Core engine handling arithmetic" in (cls.brief_description or "")


# ── Unified format entry point ──────────────────────────────────────────────


class TestUnifiedFormat:
    def test_export_format_markdown(self):
        md = export_graph(_make_simple_graph(), format="markdown")
        assert "# codegraph: design" in md

    def test_export_format_md_alias(self):
        md = export_graph(_make_simple_graph(), format="md")
        assert "# codegraph: design" in md

    def test_import_format_markdown(self):
        graph = import_graph("## Namespace: `x`\n", format="markdown")
        assert "x" in graph.entries

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            export_graph(LayerGraph(tags=frozenset({"design"})), format="csv")


# ── Diagnostics ────────────────────────────────────────────────────────────


class TestMarkdownDiagnostics:
    def test_valid_document_no_diagnostics(self):
        importer = MarkdownImporter()
        md = "## Namespace: `ns`\n\n### Class: `ns::A`\n**Public methods:**\n- `x`\n"
        importer.import_markdown(md)
        assert len(importer.diagnostics) == 0

    def test_dangling_relationship_source(self):
        importer = MarkdownImporter()
        md = "### Class: `A`\n## Relationships\n- `B` → `A` **depends_on**\n"
        importer.import_markdown(md)
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) >= 1

    def test_dangling_relationship_target(self):
        importer = MarkdownImporter()
        md = "### Class: `A`\n## Relationships\n- `A` → `B` **depends_on**\n"
        importer.import_markdown(md)
        errors = [d for d in importer.diagnostics if d.severity == "error"]
        assert len(errors) >= 1

    def test_strict_mode_raises(self):
        with pytest.raises(PlantUMLParseError):
            import_markdown(
                "### Class: `A`\n## Relationships\n- `B` → `A` **depends_on**\n",
                strict=True,
            )

    def test_convenience_function_tags(self):
        md = "### Class: `A`\n"
        graph = import_markdown(md, tags=frozenset({"as-built"}))
        assert graph.entries["A"].node.has_tag("as-built")


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestMarkdownEdgeCases:
    def test_alternative_keyword_namespace(self):
        md = "## Namespace: `calc`\n"
        graph = import_markdown(md)
        assert isinstance(graph.entries["calc"].node, NamespaceNode)

    def test_tags_default(self):
        md = "### Class: `A`\n"
        graph = import_markdown(md)
        assert graph.entries["A"].node.has_tag("design")

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
        assert "AttributeNode" in cls.children

    def test_convenience_functions(self):
        graph = _make_simple_graph()
        md = export_markdown(graph)
        assert "# codegraph: design" in md
        restored = import_markdown(md)
        assert "calc" in restored.entries

    def test_fields_all_export_roundtrip(self):
        graph = _make_simple_graph()
        md = export_markdown(graph, fields="all")
        # fields="all" includes type signatures inline
        assert "`add(int a, int b): int`" in md