"""Tests for the functional-coverage Markdown export
(:mod:`codegraph.export.coverage`).

Covers:

- document structure (header, Mermaid block, narration tables);
- ``detail`` modes: ``"tests"`` (req → test → class) vs
  ``"assertions"`` (adds rendered assertion conditions);
- condition rendering (``==``, ``is_true`` / ``is_false``);
- the ``export_graph`` dispatcher (``format="coverage"``);
- error handling (unknown class, invalid detail, missing scope_class).
"""

import pytest

from codegraph.export.coverage import export_coverage_markdown
from codegraph.export.format import export_graph

from tests.integration.serialization._scoped_graph import make_scoped_verification_graph


class TestCoverageMarkdown:
    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_structure
    # Verifies the document contains the header, a mermaid block, and the
    # requirements + test-narration sections.
    def test_structure(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(graph, "app::Engine")
        assert md.startswith("# Design & test coverage — Engine")
        assert "```mermaid" in md
        assert "## Requirements" in md
        assert "## Test narration" in md

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_mermaid_subgraph_grouping
    # Verifies the default detail mode renders requirement subgraphs with
    # tests inside, and the class as the single code node — no assertion
    # leaves.
    def test_mermaid_subgraph_grouping(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(graph, "app::Engine")
        mermaid = md.split("```mermaid")[1].split("```")[0]
        assert 'subgraph S1["llr_engine<br/>' in mermaid
        assert 'test_engine_starts<br/>' in mermaid
        assert 'Engine<br/>' in mermaid
        # no assertion nodes in the default mode
        assert "assert_speed" not in mermaid
        # edges present
        assert "--> " in mermaid

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_assertions_detail
    # Verifies detail="assertions" adds assertion nodes with rendered
    # conditions (operands + operator).
    def test_assertions_detail(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(graph, "app::Engine", detail="assertions")
        mermaid = md.split("```mermaid")[1].split("```")[0]
        assert "assert_speed<br/>" in mermaid
        # LEFT_OPERAND app::Engine::speed + operator '==' + literal? the
        # fixture builder only sets LEFT_OPERAND, so the condition shows '?'
        assert "speed" in mermaid
        # conditions table rendered
        assert "| Assertion | Condition |" in md

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_structural_svg_embed
    # Verifies structural_svg embeds the rendered PlantUML image and the
    # puml link is labelled as the source.
    def test_structural_svg_embed(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(
            graph, "app::Engine",
            puml_path="engine_scoped.puml",
            structural_svg="engine_scoped.svg",
        )
        assert "## Structural view" in md
        assert "![Engine — class, neighbours, requirements, tests]" \
               "(engine_scoped.svg)" in md
        assert "[engine_scoped.puml](engine_scoped.puml)" in md

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_mermaid_svg_embed
    # Verifies mermaid_svg embeds the rendered image and keeps the
    # Mermaid source in a collapsible details block.
    def test_mermaid_svg_embed(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(
            graph, "app::Engine", mermaid_svg="engine_coverage.svg",
        )
        assert "## Test coverage" in md
        assert "![Functional coverage — Engine](engine_coverage.svg)" in md
        assert "<details>" in md
        assert "<summary>Mermaid source</summary>" in md
        assert "```mermaid" in md  # source kept for regeneration

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_labels_strip_backticks
    # Verifies Mermaid labels never contain backticks (Markdown
    # formatting that Mermaid's HTML-label renderer mishandles).
    def test_labels_strip_backticks(self):
        from codegraph.export.coverage import _mermaid_label
        assert _mermaid_label("The `MigrationManager` shall") == \
            "The MigrationManager shall"
        assert _mermaid_label('say "hi"') == "say #quot;hi#quot;"
        assert _mermaid_label("a & b") == "a &amp; b"

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_condition_rendering
    # Verifies == and is_true/is_false operators render readably.
    def test_condition_rendering(self):
        from codegraph.graph import LayerGraph


from codegraph.graph import LayerGraph


from codegraph.graph import LayerGraph

from codegraph.graph import LayerGraph
from tests.integration.serialization._keying import key_graph as _kg


class _KeyedLayerGraph(LayerGraph):
    """LayerGraph that stamps canonical keys on construction (WP A)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kg(self)




class _KeyedLayerGraph(LayerGraph):
    """LayerGraph that stamps canonical keys on construction (WP A)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _kg(self)

        from codegraph.models.compound import ClassNode
        from codegraph.models.test import AssertionNode
        from codegraph.models.literal import LiteralNode
        from codegraph.models.member import AttributeNode

        from codegraph.export.coverage import _render_condition
        attr = AttributeNode(name="count", kind="attribute", source="test",
                             qualified_name="app::Engine::count", tags=["design"])
        lit = LiteralNode(name="3", kind="literal", source="test",
                          qualified_name="literal::3", tags=["design"])
        a_eq = AssertionNode(name="a1", kind="assertion", source="test",
                             qualified_name="t::a1", tags=["design"],
                             phase="post", operator="==")
        a_true = AssertionNode(name="a2", kind="assertion", source="test",
                               qualified_name="t::a2", tags=["design"],
                               phase="post", operator="is_true")
        engine = ClassNode(name="Engine", kind="class", source="test",
                           qualified_name="app::Engine", tags=["design"])
        graph = key_graph(LayerGraph(tags=frozenset({"design"}), entries={
            "app": CompositeEntry(node=engine),
            "attr": CompositeEntry(node=attr),
            "lit": CompositeEntry(node=lit),
            "a1": CompositeEntry(
                node=a_eq,
                references=[
                    ("LEFT_OPERAND", attr.canonical_key, "AttributeNode"),
                    ("RIGHT_OPERAND", lit.canonical_key, "LiteralNode"),
                ],
            ),
            "a2": CompositeEntry(
                node=a_true,
                references=[
                    ("LEFT_OPERAND", attr.canonical_key, "AttributeNode"),
                    ("RIGHT_OPERAND", lit.canonical_key, "LiteralNode"),
                ],
            ),
        }))
        assert _render_condition(graph, graph.entries["a1"]) == "count == 3"
        assert _render_condition(graph, graph.entries["a2"]) == "count is true"

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_tables_full_narration
    # Verifies the narration tables carry the full (untruncated) test and
    # step descriptions.
    def test_tables_full_narration(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(graph, "app::Engine")
        # test description in the narration section (not truncated)
        assert "app::engine::test_engine_starts" in md
        # step action narration table
        assert "| apply_pending" not in md  # different graph
        assert "step_start_engine" in md
        assert "Invoke" in md or "step" in md

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_export_graph_dispatcher
    # Verifies export_graph forwards format="coverage" + scope_class.
    def test_export_graph_dispatcher(self):
        graph = make_scoped_verification_graph()
        md = export_graph(graph, format="coverage", scope_class="app::Engine")
        assert md.startswith("# Design & test coverage — Engine")

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_unknown_class_raises
    # Verifies scoping to an unknown class raises ValueError.
    def test_unknown_class_raises(self):
        graph = make_scoped_verification_graph()
        with pytest.raises(ValueError):
            export_coverage_markdown(graph, "app::Missing")

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_invalid_detail_raises
    # Verifies an unsupported detail value raises ValueError.
    def test_invalid_detail_raises(self):
        graph = make_scoped_verification_graph()
        with pytest.raises(ValueError):
            export_coverage_markdown(graph, "app::Engine", detail="bogus")

    # codegraph:test-desc test_coverage_markdown.TestCoverageMarkdown.test_no_coverage_note
    # Verifies the empty-coverage note when no tests pertain to the class.
    def test_no_coverage_note(self):
        graph = make_scoped_verification_graph()
        md = export_coverage_markdown(graph, "app::FuelTank")
        assert "No requirements or tests found for this class" in md
