"""Tests for markdown round-trip serialization and re-ingestion of
requirements graphs (HLR → LLR → TestNode → AssertionNode / TestStepNode
with scaffold targets).

These tests verify that:

1. A requirements graph exported to markdown can be imported back and
   persisted to Neo4j via ``to_neo4j()`` — the core round-trip.
2. Re-ingesting the same markdown is idempotent (nodes are updated, not
   duplicated) thanks to ``MERGE`` on ``uid``.
3. Re-ingesting an updated markdown (e.g. with a changed description)
   updates the existing node in place.
4. Nodes with missing required properties (e.g. a heading immediately
   followed by another heading) do not crash ``to_neo4j()``.
5. COMPOSES connections that lack a typed relationship manager (e.g.
   AttributeNode → AttributeNode) fall back to raw Cypher instead of
   raising ``ValueError``.
"""

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.export.markdown import export_markdown, import_markdown


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_full_verification_graph() -> LayerGraph:
    """Build a graph with HLR → LLR → TestNode → Assertion/TestStep
    including scaffold targets (AttributeNode, LiteralNode) and
    LEFT_OPERAND / RIGHT_OPERAND / CALLEE edges.

    Structure::

        HLR: "Round-Trip Feature"
          LLR: "RT-LLR-001"
            TestNode: "vm::rt::test_basic"
              AssertionNode: "cond::rt::pre::ready"
                LEFT_OPERAND → AttributeNode "Gen::is_ready"
                RIGHT_OPERAND → LiteralNode literal::true
              AssertionNode: "cond::rt::post::ok"
                LEFT_OPERAND → AttributeNode "Gen::output"
                RIGHT_OPERAND → LiteralNode literal::non_empty
              TestStepNode: "step::rt::invoke"
                CALLEE → AttributeNode "Gen::generate"

    Scaffold nodes (Gen::is_ready, Gen::output, Gen::generate,
    literal::true, literal::not_empty) are root entries — the same
    pattern used by ``decompose_hlr`` when serializing decomposition
    results to markdown.
    """
    import codegraph_requirements.models.requirement  # noqa: F401
    from codegraph_requirements.models.requirement import HLR, LLR
    from codegraph.models.test import TestNode, AssertionNode, TestStepNode
    from codegraph.models.member import AttributeNode
    from codegraph.models.literal import LiteralNode

    hlr = HLR(
        name="Round-Trip Feature",
        qualified_name="Round-Trip Feature",
        description="The system shall support full round-trip serialization.",
        tags=["design"],
    )
    llr = LLR(
        name="RT-LLR-001",
        qualified_name="RT-LLR-001",
        description="The generate operation returns valid output.",
        tags=["design"],
    )
    test = TestNode(
        name="",
        qualified_name="vm::rt::test_basic",
        test_name="test_generate_returns_valid",
        method="automated",
        description="Invoke generate and verify output.",
        tags=["design"],
    )
    pre = AssertionNode(
        name="",
        qualified_name="cond::rt::pre::ready",
        phase="pre",
        operator="is_true",
        tags=["design"],
    )
    post = AssertionNode(
        name="",
        qualified_name="cond::rt::post::ok",
        phase="post",
        operator="==",
        tags=["design"],
    )
    step = TestStepNode(
        name="",
        qualified_name="step::rt::invoke",
        description="Invoke the generate operation.",
        tags=["design"],
    )

    # Scaffold targets
    is_ready = AttributeNode(
        name="is_ready", qualified_name="Gen::is_ready", tags=["design"],
    )
    output = AttributeNode(
        name="output", qualified_name="Gen::output", tags=["design"],
    )
    generate = AttributeNode(
        name="generate", qualified_name="Gen::generate", tags=["design"],
    )
    lit_true = LiteralNode(
        name="true", qualified_name="literal::true",
        value="true", tags=["design"],
    )
    lit_non_empty = LiteralNode(
        name="non_empty", qualified_name="literal::not_empty",
        value="not_empty", tags=["design"],
    )

    # Build tree
    pre_entry = CompositeEntry(
        node=pre,
        references=[
            ("LEFT_OPERAND", "Gen::is_ready", "AttributeNode"),
            ("RIGHT_OPERAND", "literal::true", "LiteralNode"),
        ],
    )
    post_entry = CompositeEntry(
        node=post,
        references=[
            ("LEFT_OPERAND", "Gen::output", "AttributeNode"),
            ("RIGHT_OPERAND", "literal::not_empty", "LiteralNode"),
        ],
    )
    step_entry = CompositeEntry(
        node=step,
        references=[("CALLEE", "Gen::generate", "AttributeNode")],
    )
    test_entry = CompositeEntry(
        node=test,
        children={
            "AssertionNode": {
                "cond::rt::pre::ready": pre_entry,
                "cond::rt::post::ok": post_entry,
            },
            "TestStepNode": {"step::rt::invoke": step_entry},
        },
    )
    llr_entry = CompositeEntry(
        node=llr,
        children={"TestNode": {"vm::rt::test_basic": test_entry}},
    )
    hlr_entry = CompositeEntry(
        node=hlr,
        children={"LLR": {"RT-LLR-001": llr_entry}},
    )

    scaffold_entries = {
        "Gen::is_ready": CompositeEntry(node=is_ready),
        "Gen::output": CompositeEntry(node=output),
        "Gen::generate": CompositeEntry(node=generate),
        "literal::true": CompositeEntry(node=lit_true),
        "literal::not_empty": CompositeEntry(node=lit_non_empty),
    }

    return LayerGraph(
        tags=frozenset({"design"}),
        entries={"Round-Trip Feature": hlr_entry, **scaffold_entries},
    )


# ── Round-trip: export → import → to_neo4j ─────────────────────────────


class TestRequirementsRoundTripNeo4j:
    """Tests that a requirements graph can be exported to markdown,
    imported back, and persisted to Neo4j."""

    def test_full_round_trip_to_neo4j(self):
        """Export → import → to_neo4j succeeds for a graph with
        HLR, LLR, TestNode, AssertionNode, TestStepNode, and scaffold
        targets."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        # Should not raise
        restored.to_neo4j()

    def test_round_trip_preserves_hlr_description(self):
        """The HLR description survives the round-trip."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        hlr_entry = restored.entries["Round-Trip Feature"]
        assert hlr_entry.node.description == (
            "The system shall support full round-trip serialization."
        )

    def test_round_trip_preserves_verification_edges(self):
        """LEFT_OPERAND, RIGHT_OPERAND, and CALLEE edges survive
        the round-trip and are persisted to Neo4j."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        restored.to_neo4j()

        # Verify edges exist in Neo4j via raw Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[:LEFT_OPERAND]->(t) "
            "WHERE a.qualified_name = 'cond::rt::pre::ready' "
            "RETURN t.qualified_name"
        )
        assert results and results[0][0] == "Gen::is_ready"

        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[:RIGHT_OPERAND]->(t) "
            "WHERE a.qualified_name = 'cond::rt::pre::ready' "
            "RETURN t.qualified_name"
        )
        assert results and results[0][0] == "literal::true"

        results, _ = db.cypher_query(
            "MATCH (s:TestStepNode)-[:CALLEE]->(t) "
            "WHERE s.qualified_name = 'step::rt::invoke' "
            "RETURN t.qualified_name"
        )
        assert results and results[0][0] == "Gen::generate"

    def test_round_trip_preserves_composes_hierarchy(self):
        """The HLR → LLR → TestNode → AssertionNode COMPOSES hierarchy
        is preserved after round-trip and to_neo4j."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        restored.to_neo4j()

        from neomodel import db
        # HLR → LLR
        results, _ = db.cypher_query(
            "MATCH (h:HLR)-[:COMPOSES]->(l:LLR) "
            "WHERE h.name = 'Round-Trip Feature' "
            "RETURN l.name"
        )
        assert results and results[0][0] == "RT-LLR-001"

        # LLR → TestNode
        results, _ = db.cypher_query(
            "MATCH (l:LLR)-[:COMPOSES]->(t:TestNode) "
            "WHERE l.name = 'RT-LLR-001' "
            "RETURN t.test_name"
        )
        assert results and results[0][0] == "test_generate_returns_valid"


# ── Re-ingestion idempotency ───────────────────────────────────────────


class TestReingestionIdempotency:
    """Tests that re-ingesting the same markdown is idempotent —
    nodes are updated, not duplicated."""

    def test_reingest_same_markdown_no_duplicates(self):
        """Ingesting the same markdown twice produces the same number
        of nodes (no duplicates)."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)

        restored.to_neo4j()

        from codegraph_requirements.models.requirement import HLR, LLR
        hlr_count_before = len(HLR.nodes.all())
        llr_count_before = len(LLR.nodes.all())

        # Re-ingest
        restored2 = import_markdown(md)
        restored2.to_neo4j()

        hlr_count_after = len(HLR.nodes.all())
        llr_count_after = len(LLR.nodes.all())

        assert hlr_count_before == hlr_count_after
        assert llr_count_before == llr_count_after

    def test_reingest_updates_description(self):
        """Re-ingesting markdown with an updated description changes
        the existing node's description in Neo4j."""
        graph = _make_full_verification_graph()
        md = export_markdown(graph)
        restored = import_markdown(md)
        restored.to_neo4j()

        # Verify original description
        from codegraph_requirements.models.requirement import HLR
        original = HLR.nodes.get(name="Round-Trip Feature")
        assert "full round-trip" in original.description

        # Modify the markdown and re-ingest
        md_updated = md.replace(
            "The system shall support full round-trip serialization.",
            "The system shall support UPDATED description.",
        )
        restored2 = import_markdown(md_updated)
        restored2.to_neo4j()

        # Verify the existing node was updated
        updated = HLR.nodes.get(name="Round-Trip Feature")
        assert "UPDATED description" in updated.description

        # No duplicate
        assert len(HLR.nodes.filter(name="Round-Trip Feature")) == 1


# ── Edge cases ─────────────────────────────────────────────────────────


class TestRoundTripEdgeCases:
    """Tests for edge cases that previously caused ingestion failures."""

    def test_hlr_without_description_does_not_crash(self):
        """An HLR heading immediately followed by another heading
        (no description line) does not crash to_neo4j()."""
        md = (
            "## HLR: `Empty HLR`\n"
            "## HLR: `Second HLR`\n"
            "Second HLR description.\n"
        )
        graph = import_markdown(md)

        # Should not raise RequiredProperty
        graph.to_neo4j()

        # The empty HLR should exist in Neo4j. The description
        # is null (not set) because the markdown had no description
        # line for this heading.
        from codegraph_requirements.models.requirement import HLR
        empty_hlr = HLR.nodes.get(name="Empty HLR")
        assert empty_hlr.description in (None, "")

    def test_llr_without_description_does_not_crash(self):
        """An LLR heading without a description line does not crash."""
        md = (
            "## HLR: `Parent HLR`\n"
            "Parent requirement.\n"
            "### LLR: `No Desc LLR`\n"
            "#### Test: `vm::test`\n"
            "Test description.\n"
        )
        graph = import_markdown(md)

        # Should not raise RequiredProperty
        graph.to_neo4j()

    def test_attribute_with_attribute_child_does_not_crash(self):
        """An AttributeNode heading with a ``**Public attributes:**``
        section (creating AttributeNode → AttributeNode nesting) does
        not crash to_neo4j() — the COMPOSES connection falls back to
        raw Cypher."""
        md = (
            "## Attribute: `Parent::attr`\n"
            "Some attribute.\n"
            "**Public attributes:**\n"
            "- `child_attr`\n"
        )
        graph = import_markdown(md)

        # Should not raise ValueError about missing COMPOSES manager
        graph.to_neo4j()

    def test_reingest_preserves_existing_description(self):
        """Re-ingesting a markdown that omits the description for a
        node that already has one in Neo4j preserves the existing
        description (thanks to SET n += instead of SET n =)."""
        # First ingest with description
        md = (
            "## HLR: `Preserve Desc HLR`\n"
            "Original description text.\n"
        )
        graph = import_markdown(md)
        graph.to_neo4j()

        from codegraph_requirements.models.requirement import HLR
        node = HLR.nodes.get(name="Preserve Desc HLR")
        assert node.description == "Original description text."

        # Re-ingest with a version that has no description line
        # (heading immediately followed by end of document)
        md_no_desc = "## HLR: `Preserve Desc HLR`\n"
        graph2 = import_markdown(md_no_desc)
        graph2.to_neo4j()

        # The existing description should be preserved
        node2 = HLR.nodes.get(name="Preserve Desc HLR")
        assert node2.description == "Original description text."


# ── File-based round-trip identity ─────────────────────────────────────


class TestRequirementsFileRoundTrip:
    """Test that a real requirements markdown file can be loaded,
    deserialized, re-serialized, and produces identical output."""

    def test_requirements_md_round_trip_identical(self):
        """Load ``tests/data/requirements_roundtrip.md``, import it back
        into a LayerGraph, re-export to markdown, write the result to
        ``unit_test_data/``, and assert the two files are byte-identical.

        The fixture was generated by ``export_markdown`` so it is in
        standard codegraph markdown format — the round-trip should be
        lossless on the first pass.
        """
        from pathlib import Path

        source = Path(__file__).resolve().parent / "data" / "requirements_roundtrip.md"
        assert source.exists(), f"Fixture not found: {source}"

        original = source.read_text(encoding="utf-8")

        # 1. Deserialize (import)
        restored = import_markdown(original, tags=frozenset({"design"}))

        # 2. Serialize back to markdown
        reexported = export_markdown(restored, fields="all")

        # 3. Write to gitignored unit_test_data/ for visual inspection
        out_dir = Path(__file__).resolve().parent.parent / "unit_test_data"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / "requirements_roundtrip.md"
        out_path.write_text(reexported, encoding="utf-8")

        # 4. Assert identical
        assert reexported == original, (
            "Round-trip is not stable: export_markdown(import_markdown(text)) "
            "differs from the original. See unit_test_data/requirements_roundtrip.md "
            "for the re-exported version."
        )