"""Tests for Markdown serialization of requirements and components.

Verifies that Component, HLR, and LLR nodes can be fully exported to
Markdown and imported back, preserving structure, descriptions,
properties, and composition hierarchy.
"""

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from tests.integration.serialization._keying import key_graph as _kg


class _KeyedLayerGraph(LayerGraph):
    """LayerGraph that stamps canonical keys on construction (WP A)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kg(self), CompositeEntry
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
        source="test",
        qualified_name="Calculation Engine",
        description="The calculation engine shall provide arithmetic operations.",
        namespace="calc.engine",
        tags=["design"],
    )
    hlr1 = HLR(
        name="Requirements for Addition",
        source="test",
        qualified_name="Requirements for Addition",
        description="The system shall support addition of two numbers.",
        tags=["design"],
    )
    hlr2 = HLR(
        name="Requirements for Subtraction",
        source="test",
        qualified_name="Requirements for Subtraction",
        description="The system shall support subtraction of two numbers.",
        tags=["design"],
    )
    llr1 = LLR(
        name="Addition LLR-1",
        source="test",
        qualified_name="Addition LLR-1",
        description="The add function shall return the sum of two integers.",
        tags=["design"],
    )
    llr2 = LLR(
        name="Addition LLR-2",
        source="test",
        qualified_name="Addition LLR-2",
        description="The add function shall handle negative numbers.",
        tags=["design"],
    )
    llr3 = LLR(
        name="Subtraction LLR-1",
        source="test",
        qualified_name="Subtraction LLR-1",
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

    return _KeyedLayerGraph(
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


# ── Test-node + verification-edge round-trip tests ───────────────────────


def _make_test_verification_graph() -> LayerGraph:
    """Build a graph with HLR → LLR → TestNode → AssertionNode/TestStepNode,
    including LEFT_OPERAND, RIGHT_OPERAND, and CALLEE edges to scaffold
    targets (AttributeNode, LiteralNode).

    Structure::

        HLR: "Test Feature"
          LLR: "Test LLR-001"
            TestNode: "vm::generate::test_valid"
              AssertionNode: "cond::pre::calibrated"
                LEFT_OPERAND → AttributeNode "Diagram::is_ready"
                RIGHT_OPERAND → LiteralNode literal::true
              AssertionNode: "cond::post::output_ok"
                LEFT_OPERAND → AttributeNode "Diagram::output"
                RIGHT_OPERAND → LiteralNode literal::not_empty
              TestStepNode: "step::invoke"
                CALLEE → AttributeNode "Diagram::generate"
    """
    import codegraph_requirements.models.requirement  # noqa: F401
    from codegraph_requirements.models.requirement import HLR, LLR
    from codegraph.models.test import TestNode, AssertionNode, TestStepNode
    from codegraph.models.member import AttributeNode
    from codegraph.models.literal import LiteralNode

    # ── Requirement nodes ──
    hlr = HLR(
        name="Test Feature",
        source="test",
        qualified_name="Test Feature",
        description="The system shall support test verification roundtrips.",
        tags=["design"],
    )
    llr = LLR(
        name="Test LLR-001",
        source="test",
        qualified_name="Test LLR-001",
        description="The generate operation returns valid output.",
        tags=["design"],
    )

    # ── Verification nodes ──
    test_node = TestNode(
        name="",
        source="test",
        qualified_name="vm::generate::test_valid",
        test_name="test_generate_returns_valid_output",
        method="automated",
        description="Invoke generate and verify output.",
        tags=["design"],
    )

    precond = AssertionNode(
        name="",
        source="test",
        qualified_name="cond::pre::calibrated",
        phase="pre",
        operator="is_true",
        tags=["design"],
    )

    postcond = AssertionNode(
        name="",
        source="test",
        qualified_name="cond::post::output_ok",
        phase="post",
        operator="==",
        tags=["design"],
    )

    step = TestStepNode(
        name="",
        source="test",
        qualified_name="step::invoke",
        description="Invoke the generate operation.",
        tags=["design"],
    )

    # ── Scaffold target nodes ──
    is_ready = AttributeNode(
        name="is_ready",
        source="test",
        qualified_name="Diagram::is_ready",
        tags=["design"],
    )
    output = AttributeNode(
        name="output",
        source="test",
        qualified_name="Diagram::output",
        tags=["design"],
    )
    generate_op = AttributeNode(
        name="generate",
        source="test",
        qualified_name="Diagram::generate",
        tags=["design"],
    )
    lit_true = LiteralNode(
        name="true",
        source="test",
        qualified_name="literal::true",
        value="true",
        tags=["design"],
    )
    lit_not_empty = LiteralNode(
        name="not_empty",
        source="test",
        qualified_name="literal::not_empty",
        value="not_empty",
        tags=["design"],
    )

    # ── Build CompositeEntry tree ──
    precond_entry = CompositeEntry(
        node=precond,
        references=[
            ("LEFT_OPERAND", "Diagram::is_ready", "AttributeNode"),
            ("RIGHT_OPERAND", "literal::true", "LiteralNode"),
        ],
    )
    postcond_entry = CompositeEntry(
        node=postcond,
        references=[
            ("LEFT_OPERAND", "Diagram::output", "AttributeNode"),
            ("RIGHT_OPERAND", "literal::not_empty", "LiteralNode"),
        ],
    )
    step_entry = CompositeEntry(
        node=step,
        references=[
            ("CALLEE", "Diagram::generate", "AttributeNode"),
        ],
    )

    test_entry = CompositeEntry(
        node=test_node,
        children={
            "AssertionNode": {
                "cond::pre::calibrated": precond_entry,
                "cond::post::output_ok": postcond_entry,
            },
            "TestStepNode": {
                "step::invoke": step_entry,
            },
        },
    )

    llr_entry = CompositeEntry(
        node=llr,
        children={
            "TestNode": {
                "vm::generate::test_valid": test_entry,
            },
        },
    )

    hlr_entry = CompositeEntry(
        node=hlr,
        children={
            "LLR": {
                "Test LLR-001": llr_entry,
            },
        },
    )

    # ── Include scaffold nodes as root entries (referenced but not
    #     in the COMPOSES tree).  The markdown exporter writes them
    #     as headings so the importer can find them. ──
    scaffold_entries = {
        "Diagram::is_ready": CompositeEntry(node=is_ready),
        "Diagram::output": CompositeEntry(node=output),
        "Diagram::generate": CompositeEntry(node=generate_op),
        "literal::true": CompositeEntry(node=lit_true),
        "literal::not_empty": CompositeEntry(node=lit_not_empty),
    }

    all_entries = {"Test Feature": hlr_entry, **scaffold_entries}

    return _KeyedLayerGraph(tags=frozenset({"design"}), entries=all_entries)


class TestVerificationEdgeRoundTrip:
    """Tests that verification edges (LEFT_OPERAND, RIGHT_OPERAND, CALLEE)
    survive markdown export→import round-trip."""

    def test_edges_appear_in_relationships_section(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)

        # LEFT_OPERAND edges
        assert "cond::pre::calibrated" in md
        assert "Diagram::is_ready" in md
        assert "**left_operand**" in md

        # RIGHT_OPERAND edges
        assert "literal::true" in md
        assert "**right_operand**" in md

        # CALLEE edges
        assert "step::invoke" in md
        assert "Diagram::generate" in md
        assert "**callee**" in md

    def test_round_trip_preserves_hierarchy(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # HLR → LLR
        hlr_entry = restored.entries["Test Feature"]
        assert hlr_entry.node.__class__.__name__ == "HLR"
        assert "LLR" in hlr_entry.children

        llr_entries = list(hlr_entry.children["LLR"].values())
        assert len(llr_entries) == 1
        llr_entry = llr_entries[0]
        assert llr_entry.node.__class__.__name__ == "LLR"
        assert llr_entry.node.name == "Test LLR-001"

        # LLR → TestNode
        assert "TestNode" in llr_entry.children
        test_entries = list(llr_entry.children["TestNode"].values())
        assert len(test_entries) == 1
        test_entry = test_entries[0]
        assert test_entry.node.__class__.__name__ == "TestNode"
        assert test_entry.node.test_name == "test_generate_returns_valid_output"

        # TestNode → AssertionNode children
        assert "AssertionNode" in test_entry.children
        assert len(test_entry.children["AssertionNode"]) == 2

        # TestNode → TestStepNode children
        assert "TestStepNode" in test_entry.children
        assert len(test_entry.children["TestStepNode"]) == 1

    def test_round_trip_preserves_left_operand_edges(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # Find the pre-condition AssertionNode
        hlr_entry = restored.entries["Test Feature"]
        llr_entry = list(hlr_entry.children["LLR"].values())[0]
        test_entry = list(llr_entry.children["TestNode"].values())[0]
        precond_entry = test_entry.children["AssertionNode"]["cond::pre::calibrated"]

        # Should have LEFT_OPERAND and RIGHT_OPERAND references
        rel_types = {r[0] for r in precond_entry.references}
        assert "LEFT_OPERAND" in rel_types, f"Expected LEFT_OPERAND, got {precond_entry.references}"
        assert "RIGHT_OPERAND" in rel_types, f"Expected RIGHT_OPERAND, got {precond_entry.references}"

        # Verify LEFT_OPERAND targets the correct node
        left_refs = [r for r in precond_entry.references if r[0] == "LEFT_OPERAND"]
        assert len(left_refs) == 1
        assert left_refs[0][1] == "Diagram::is_ready"
        assert left_refs[0][2] == "AttributeNode"

    def test_round_trip_preserves_right_operand_edges(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        hlr_entry = restored.entries["Test Feature"]
        llr_entry = list(hlr_entry.children["LLR"].values())[0]
        test_entry = list(llr_entry.children["TestNode"].values())[0]
        precond_entry = test_entry.children["AssertionNode"]["cond::pre::calibrated"]

        right_refs = [r for r in precond_entry.references if r[0] == "RIGHT_OPERAND"]
        assert len(right_refs) == 1
        assert right_refs[0][1] == "literal::true"
        assert right_refs[0][2] == "LiteralNode"

    def test_round_trip_preserves_callee_edges(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        hlr_entry = restored.entries["Test Feature"]
        llr_entry = list(hlr_entry.children["LLR"].values())[0]
        test_entry = list(llr_entry.children["TestNode"].values())[0]
        step_entry = test_entry.children["TestStepNode"]["step::invoke"]

        callee_refs = [r for r in step_entry.references if r[0] == "CALLEE"]
        assert len(callee_refs) == 1
        assert callee_refs[0][1] == "Diagram::generate"
        assert callee_refs[0][2] == "AttributeNode"

    def test_round_trip_preserves_assertion_properties(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        hlr_entry = restored.entries["Test Feature"]
        llr_entry = list(hlr_entry.children["LLR"].values())[0]
        test_entry = list(llr_entry.children["TestNode"].values())[0]
        precond_entry = test_entry.children["AssertionNode"]["cond::pre::calibrated"]
        postcond_entry = test_entry.children["AssertionNode"]["cond::post::output_ok"]

        assert precond_entry.node.phase == "pre"
        assert precond_entry.node.operator == "is_true"
        assert postcond_entry.node.phase == "post"
        assert postcond_entry.node.operator == "=="

    def test_round_trip_preserves_scaffold_targets(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # Scaffold nodes (AttributeNode, LiteralNode) should appear as
        # root entries since they aren't in COMPOSES hierarchy.
        assert "Diagram::is_ready" in restored.entries
        assert restored.entries["Diagram::is_ready"].node.__class__.__name__ == "AttributeNode"

        assert "literal::true" in restored.entries
        assert restored.entries["literal::true"].node.__class__.__name__ == "LiteralNode"
        assert restored.entries["literal::true"].node.value == "true"

    def test_round_trip_reexport_is_stable(self):
        graph = _make_test_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        md2 = export_markdown(restored)

        # Structure should reappear in the re-export
        assert "## HLR: `Test Feature`" in md2
        assert "### LLR: `Test LLR-001`" in md2
        assert "#### Test: `vm::generate::test_valid`" in md2
        assert "**left_operand**" in md2
        assert "**right_operand**" in md2
        assert "**callee**" in md2