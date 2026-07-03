"""Tests for Markdown serialization of requirements and components.

Verifies that Component, HLR, and LLR nodes can be fully exported to
Markdown and imported back, preserving structure, descriptions,
properties, and composition hierarchy.
"""

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.export.markdown import export_markdown, import_markdown


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_requirements_graph() -> LayerGraph:
    """Build a small Component → HLR → LLR graph.

    Structure::

        Component: "Calculation Engine"
          HLR: "Requirements for Addition"
            LLR: "Addition LLR-1"
            LLR: "Addition LLR-2"
          HLR: "Requirements for Subtraction"
            LLR: "Subtraction LLR-1"
    """
    # Import here so that the models are registered in the CodeGraphNode
    # registry before any deserialization happens.
    import codegraph_requirements.models.requirement  # noqa: F401
    import codegraph_project.models.component  # noqa: F401
    from codegraph_requirements.models.requirement import HLR, LLR
    from codegraph_project.models.component import Component

    comp = Component(
        name="Calculation Engine",
        description="The calculation engine shall provide arithmetic operations.",
        namespace="calc.engine",
        tags=["design"],
    )
    hlr1 = HLR(
        name="Requirements for Addition",
        description="The system shall support addition of two numbers.",
        tags=["design"],
    )
    hlr2 = HLR(
        name="Requirements for Subtraction",
        description="The system shall support subtraction of two numbers.",
        tags=["design"],
    )
    llr1 = LLR(
        name="Addition LLR-1",
        description="The add function shall return the sum of two integers.",
        tags=["design"],
    )
    llr2 = LLR(
        name="Addition LLR-2",
        description="The add function shall handle negative numbers.",
        tags=["design"],
    )
    llr3 = LLR(
        name="Subtraction LLR-1",
        description="The subtract function shall return the difference.",
        tags=["design"],
    )

    llr1_entry = CompositeEntry(node=llr1)
    llr2_entry = CompositeEntry(node=llr2)
    llr3_entry = CompositeEntry(node=llr3)

    hlr1_entry = CompositeEntry(
        node=hlr1,
        children={
            "LLR": {
                "Addition LLR-1": llr1_entry,
                "Addition LLR-2": llr2_entry,
            },
        },
    )
    hlr2_entry = CompositeEntry(
        node=hlr2,
        children={"LLR": {"Subtraction LLR-1": llr3_entry}},
    )

    comp_entry = CompositeEntry(
        node=comp,
        children={
            "HLR": {
                "Requirements for Addition": hlr1_entry,
                "Requirements for Subtraction": hlr2_entry,
            },
        },
    )

    return LayerGraph(
        tags=frozenset({"design"}),
        entries={"Calculation Engine": comp_entry},
    )


# ── Export tests ────────────────────────────────────────────────────────────


class TestRequirementsExport:
    """Tests for exporting requirements and components to Markdown."""

    def test_component_heading(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "## Component: `Calculation Engine`" in md

    def test_component_description(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "The calculation engine shall provide arithmetic operations." in md

    def test_component_namespace_property(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "- namespace: calc.engine" in md

    def test_hlr_heading(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "### HLR: `Requirements for Addition`" in md

    def test_hlr_description(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "The system shall support addition of two numbers." in md

    def test_llr_heading(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "#### LLR: `Addition LLR-1`" in md

    def test_llr_description(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "The add function shall return the sum of two integers." in md

    def test_tags_property_emitted(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        assert "- tags: design" in md

    def test_no_refid_in_output(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph, fields="all")
        assert "refid" not in md


# ── Import tests ───────────────────────────────────────────────────────────


class TestRequirementsImport:
    """Tests for importing requirements and components from Markdown."""

    def test_import_component(self):
        md = "## Component: `My Component`\nDescription text.\n"
        graph = import_markdown(md)
        assert "My Component" in graph.entries
        node = graph.entries["My Component"].node
        assert node.__class__.__name__ == "Component"
        assert node.name == "My Component"

    def test_import_hlr(self):
        md = "## HLR: `Test HLR`\nSome requirement.\n"
        graph = import_markdown(md)
        assert "Test HLR" in graph.entries
        node = graph.entries["Test HLR"].node
        assert node.__class__.__name__ == "HLR"
        assert node.name == "Test HLR"

    def test_import_llr(self):
        md = "## LLR: `Test LLR`\nSome requirement.\n"
        graph = import_markdown(md)
        assert "Test LLR" in graph.entries
        node = graph.entries["Test LLR"].node
        assert node.__class__.__name__ == "LLR"
        assert node.name == "Test LLR"

    def test_import_component_with_namespace(self):
        md = (
            "## Component: `My Component`\n"
            "Description text.\n"
            "- namespace: my.namespace\n"
        )
        graph = import_markdown(md)
        node = graph.entries["My Component"].node
        assert node.namespace == "my.namespace"

    def test_import_description_restored(self):
        md = "## HLR: `Test HLR`\nThe system shall do X.\n"
        graph = import_markdown(md)
        node = graph.entries["Test HLR"].node
        assert node.description == "The system shall do X."

    def test_import_tags_restored(self):
        md = (
            "## HLR: `Test HLR`\n"
            "The system shall do X.\n"
            "- tags: design, as-built\n"
        )
        graph = import_markdown(md)
        node = graph.entries["Test HLR"].node
        assert "design" in node.tags
        assert "as-built" in node.tags

    def test_import_hlr_inside_component(self):
        md = (
            "## Component: `My Component`\n"
            "Description.\n"
            "### HLR: `Child HLR`\n"
            "Child requirement.\n"
        )
        graph = import_markdown(md)
        comp = graph.entries["My Component"]
        assert "HLR" in comp.children
        hlr_entry = list(comp.children["HLR"].values())[0]
        assert hlr_entry.node.name == "Child HLR"

    def test_import_llr_inside_hlr(self):
        md = (
            "## HLR: `Parent HLR`\n"
            "Parent requirement.\n"
            "### LLR: `Child LLR`\n"
            "Child requirement.\n"
        )
        graph = import_markdown(md)
        hlr = graph.entries["Parent HLR"]
        assert "LLR" in hlr.children
        llr_entry = list(hlr.children["LLR"].values())[0]
        assert llr_entry.node.name == "Child LLR"


# ── Round-trip tests ──────────────────────────────────────────────────────


class TestRequirementsRoundTrip:
    """Tests for export→import round-trip fidelity of requirements."""

    def test_round_trip_preserves_structure(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # Component is root
        assert "Calculation Engine" in restored.entries
        comp = restored.entries["Calculation Engine"]

        # HLRs are children of Component
        assert "HLR" in comp.children
        hlr_names = [e.node.name for e in comp.children["HLR"].values()]
        assert "Requirements for Addition" in hlr_names
        assert "Requirements for Subtraction" in hlr_names

    def test_round_trip_preserves_descriptions(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        comp = restored.entries["Calculation Engine"]
        assert comp.node.description == "The calculation engine shall provide arithmetic operations."

    def test_round_trip_preserves_namespace(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        comp = restored.entries["Calculation Engine"]
        assert comp.node.namespace == "calc.engine"

    def test_round_trip_preserves_llr_nesting(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        comp = restored.entries["Calculation Engine"]
        hlr_entries = list(comp.children["HLR"].values())
        addition_hlr = next(
            e for e in hlr_entries if e.node.name == "Requirements for Addition"
        )
        assert "LLR" in addition_hlr.children
        llr_names = [e.node.name for e in addition_hlr.children["LLR"].values()]
        assert "Addition LLR-1" in llr_names
        assert "Addition LLR-2" in llr_names

    def test_round_trip_preserves_llr_descriptions(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        comp = restored.entries["Calculation Engine"]
        hlr_entries = list(comp.children["HLR"].values())
        addition_hlr = next(
            e for e in hlr_entries if e.node.name == "Requirements for Addition"
        )
        llr_entries = list(addition_hlr.children["LLR"].values())
        llr1 = next(e for e in llr_entries if e.node.name == "Addition LLR-1")
        assert llr1.node.description == "The add function shall return the sum of two integers."

    def test_round_trip_reexport_stable(self):
        graph = _make_requirements_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        md2 = export_markdown(restored)

        assert "## Component: `Calculation Engine`" in md2
        assert "### HLR: `Requirements for Addition`" in md2
        assert "#### LLR: `Addition LLR-1`" in md2
        assert "- namespace: calc.engine" in md2