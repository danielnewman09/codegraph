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
6. Full COMPOSES hierarchy (HLR→LLR→Test→Assertion, Test→Step) is
   correctly persisted to Neo4j after round-trip ingestion — no
   orphaned nodes, no missing edges.
7. Heading labels use human-readable ``qualified_name`` values, not
   hash-based uid prefixes.
"""

import re
from pathlib import Path

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


# ── Full COMPOSES hierarchy verification ────────────────────────────────


class TestFullComposesHierarchy:
    """Verify that the complete COMPOSES hierarchy is persisted to Neo4j
    after round-trip ingestion of a properly-formatted requirements.md.

    The fixture file ``tests/data/requirements_roundtrip.md`` has::

        ## HLR: `Diagram Generator`           (depth 2)
        ### LLR: `DG-LLR-001`                   (depth 3, nested under HLR)
        #### Test: `vm::generate::test_valid`   (depth 4, nested under LLR)
        ##### Assertion: `cond::...`             (depth 5, nested under Test)
        ##### TestStep: `step::...`              (depth 5, nested under Test)

    The importer uses heading depth for nesting, so the depth hierarchy
    is critical: if LLRs are at depth 2 (same as HLR) instead of depth 3,
    no HLR→LLR COMPOSES edges are created.
    """

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_headings(text: str) -> list[tuple[int, str, str]]:
        """Extract (depth, keyword, label) tuples from markdown headings."""
        headings = []
        for line in text.splitlines():
            m = re.match(
                r'^(#{2,6})\s+(HLR|LLR|Test|Assertion|TestStep):\s+`([^`]+)`',
                line,
            )
            if m:
                headings.append((len(m.group(1)), m.group(2), m.group(3)))
        return headings

    @staticmethod
    def _fixture_text() -> str:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent
            / "data"
            / "requirements_roundtrip.md"
        )
        assert source.exists(), f"Fixture not found: {source}"
        return source.read_text(encoding="utf-8")

    # ── Heading-depth checks (no Neo4j needed) ───────────────────────

    def test_fixture_has_proper_heading_depths(self):
        """The fixture file must have HLR at ##, LLR at ###, Test at ####,
        and Assertion/TestStep at #####.  This is the format that produces
        correct COMPOSES nesting on import."""
        headings = self._extract_headings(self._fixture_text())
        assert len(headings) > 0, "No requirement headings found in fixture"

        # HLR must be at depth 2
        hlr_headings = [h for h in headings if h[1] == "HLR"]
        assert len(hlr_headings) >= 1
        assert all(h[0] == 2 for h in hlr_headings), \
            f"HLR headings must be at depth 2, got: {hlr_headings}"

        # LLRs must be at depth 3 (nested under HLR)
        llr_headings = [h for h in headings if h[1] == "LLR"]
        assert len(llr_headings) >= 1
        assert all(h[0] == 3 for h in llr_headings), \
            f"LLR headings must be at depth 3, got: {llr_headings}"

        # Tests must be at depth 4 (nested under LLR)
        test_headings = [h for h in headings if h[1] == "Test"]
        assert len(test_headings) >= 1
        assert all(h[0] == 4 for h in test_headings), \
            f"Test headings must be at depth 4, got: {test_headings}"

        # Assertions and TestSteps must be at depth 5 (nested under Test)
        assertion_headings = [h for h in headings if h[1] == "Assertion"]
        assert len(assertion_headings) >= 1
        assert all(h[0] == 5 for h in assertion_headings), \
            f"Assertion headings must be at depth 5, got: {assertion_headings}"

        step_headings = [h for h in headings if h[1] == "TestStep"]
        assert len(step_headings) >= 1
        assert all(h[0] == 5 for h in step_headings), \
            f"TestStep headings must be at depth 5, got: {step_headings}"

    def test_fixture_labels_are_human_readable(self):
        """Heading labels in the fixture must be human-readable
        ``qualified_name`` values, not hash-based uid prefixes like
        ``hlr_792dc341``."""
        headings = self._extract_headings(self._fixture_text())

        # HLR label should be a human-readable name, not a hash
        hlr_labels = [label for kw, label in headings if kw == "HLR"]
        assert len(hlr_labels) >= 1
        assert hlr_labels[0] == "Diagram Generator", \
            f"HLR label should be 'Diagram Generator', got: {hlr_labels[0]!r}"
        # Must NOT match the hash-based pattern
        assert not re.match(r'^hlr_[a-f0-9]{8}$', hlr_labels[0]), \
            f"HLR label looks like a uid hash: {hlr_labels[0]!r}"

        # LLR labels should be human-readable identifiers
        llr_labels = [label for kw, label in headings if kw == "LLR"]
        for label in llr_labels:
            assert not re.match(r'^llr_[a-f0-9]{8}$', label), \
                f"LLR label looks like a uid hash: {label!r}"

    # ── Neo4j ingestion checks ───────────────────────────────────────

    def test_full_composes_hierarchy_in_neo4j(self):
        """After importing the fixture and persisting to Neo4j, verify
        the complete COMPOSES chain: HLR→LLR→Test→Assertion and
        Test→Step.

        This is the core round-trip ingestion test — every level of the
        hierarchy must be connected via COMPOSES edges in the database.
        """
        graph = import_markdown(
            self._fixture_text(), tags=frozenset({"design"})
        )
        graph.to_neo4j()

        from neomodel import db

        # HLR → LLR: every LLR must have an incoming COMPOSES from the HLR
        results, _ = db.cypher_query(
            "MATCH (h:HLR)-[:COMPOSES]->(l:LLR) "
            "WHERE h.qualified_name = 'Diagram Generator' "
            "RETURN l.qualified_name ORDER BY l.qualified_name"
        )
        llr_qnames = [r[0] for r in results]
        assert len(llr_qnames) == 3, \
            f"Expected 3 LLRs under HLR, got {len(llr_qnames)}: {llr_qnames}"
        assert "DG-LLR-001" in llr_qnames
        assert "DG-LLR-002" in llr_qnames
        assert "DG-LLR-003" in llr_qnames

        # LLR → TestNode: every Test must have an incoming COMPOSES from its LLR
        results, _ = db.cypher_query(
            "MATCH (l:LLR)-[:COMPOSES]->(t:TestNode) "
            "WHERE l.qualified_name = 'DG-LLR-001' "
            "RETURN t.qualified_name ORDER BY t.qualified_name"
        )
        test_qnames = [r[0] for r in results]
        assert len(test_qnames) >= 1, \
            f"Expected at least 1 Test under DG-LLR-001, got {test_qnames}"
        assert "vm::generate::test_valid" in test_qnames

        # TestNode → AssertionNode
        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(a:AssertionNode) "
            "WHERE t.qualified_name = 'vm::generate::test_valid' "
            "RETURN a.qualified_name ORDER BY a.qualified_name"
        )
        assertion_qnames = [r[0] for r in results]
        assert len(assertion_qnames) >= 2, \
            f"Expected at least 2 Assertions under test_valid, got: {assertion_qnames}"

        # TestNode → TestStepNode
        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(s:TestStepNode) "
            "WHERE t.qualified_name = 'vm::generate::test_valid' "
            "RETURN s.qualified_name ORDER BY s.qualified_name"
        )
        step_qnames = [r[0] for r in results]
        assert len(step_qnames) >= 1, \
            f"Expected at least 1 TestStep under test_valid, got: {step_qnames}"

    def test_no_orphaned_nodes_after_ingestion(self):
        """After round-trip ingestion, every LLR must have a parent HLR,
        every Test must have a parent LLR, and every Assertion/TestStep
        must have a parent Test — no orphaned nodes in the database.
        """
        graph = import_markdown(
            self._fixture_text(), tags=frozenset({"design"})
        )
        graph.to_neo4j()

        from neomodel import db

        # Orphaned LLRs: LLRs with no incoming COMPOSES from any HLR
        results, _ = db.cypher_query(
            "MATCH (l:LLR) WHERE NOT (l)<-[:COMPOSES]-(:HLR) "
            "RETURN l.qualified_name"
        )
        orphaned_llrs = [r[0] for r in results]
        assert len(orphaned_llrs) == 0, \
            f"Orphaned LLRs (no parent HLR): {orphaned_llrs}"

        # Orphaned TestNodes: Tests with no incoming COMPOSES from any LLR
        results, _ = db.cypher_query(
            "MATCH (t:TestNode) WHERE NOT (t)<-[:COMPOSES]-(:LLR) "
            "RETURN t.qualified_name"
        )
        orphaned_tests = [r[0] for r in results]
        assert len(orphaned_tests) == 0, \
            f"Orphaned TestNodes (no parent LLR): {orphaned_tests}"

        # Orphaned AssertionNodes
        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode) WHERE NOT (a)<-[:COMPOSES]-(:TestNode) "
            "RETURN a.qualified_name"
        )
        orphaned_assertions = [r[0] for r in results]
        assert len(orphaned_assertions) == 0, \
            f"Orphaned AssertionNodes (no parent Test): {orphaned_assertions}"

        # Orphaned TestStepNodes
        results, _ = db.cypher_query(
            "MATCH (s:TestStepNode) WHERE NOT (s)<-[:COMPOSES]-(:TestNode) "
            "RETURN s.qualified_name"
        )
        orphaned_steps = [r[0] for r in results]
        assert len(orphaned_steps) == 0, \
            f"Orphaned TestStepNodes (no parent Test): {orphaned_steps}"

    def test_hlr_has_human_readable_name_in_neo4j(self):
        """After ingestion, the HLR node in Neo4j must have a
        human-readable ``name`` and ``qualified_name``, not a hash-based
        identifier."""
        graph = import_markdown(
            self._fixture_text(), tags=frozenset({"design"})
        )
        graph.to_neo4j()

        from codegraph_requirements.models.requirement import HLR
        hlr = HLR.nodes.get(qualified_name="Diagram Generator")
        assert hlr.name == "Diagram Generator"
        assert hlr.qualified_name == "Diagram Generator"
        # Must NOT look like a hash
        assert not re.match(r'^hlr_[a-f0-9]+$', hlr.name), \
            f"HLR name looks like a uid hash: {hlr.name!r}"


# ── Decompose output format validation ──────────────────────────────────


class TestDecomposeOutputFormat:
    """Validate that decompose-generated requirements.md conforms to the
    same format standards as the test fixture.

    The decompose agent (via ``serialize_decomposition_to_markdown`` or
    the bridge's ``_export_decomposition_markdown``) must produce:

    1. Human-readable heading labels (``qualified_name``), not uid hashes.
    2. Proper heading depth hierarchy (HLR at ##, LLR at ###, etc.).

    If the decompose output doesn't conform, the importer won't create
    COMPOSES edges and the ingested graph will have orphaned nodes.
    """

    @staticmethod
    def _decompose_output_path() -> Path:
        from pathlib import Path

        return (
            Path(__file__).resolve().parent.parent
            / "codegraph" / "requirements"
            / "architecture-diagram-generator" / "requirements.md"
        )

    @staticmethod
    def _extract_headings(text: str) -> list[tuple[int, str, str]]:
        """Extract (depth, keyword, label) tuples from markdown headings."""
        headings = []
        for line in text.splitlines():
            m = re.match(
                r'^(#{2,6})\s+(HLR|LLR|Test|Assertion|TestStep):\s+`([^`]+)`',
                line,
            )
            if m:
                headings.append((len(m.group(1)), m.group(2), m.group(3)))
        return headings

    # ── Heading-label checks (no Neo4j needed) ───────────────────────

    def test_decompose_output_has_human_readable_hlr_label(self):
        """The HLR heading in a decompose-generated file should use a
        human-readable name, not a hash-based identifier like
        ``hlr_792dc341``."""
        path = self._decompose_output_path()
        if not path.exists():
            pytest.skip("No decompose output file found")

        text = path.read_text(encoding="utf-8")

        hlr_match = re.search(r'^## HLR:\s+`([^`]+)`', text, re.MULTILINE)
        assert hlr_match, "No HLR heading found in decompose output"
        hlr_label = hlr_match.group(1)

        # Must NOT be a hash-based identifier
        assert not re.match(r'^hlr_[a-f0-9]+$', hlr_label), \
            (f"HLR label is a hash-based uid, not human-readable: "
             f"{hlr_label!r}. Expected a human-readable name like "
             f"'Architecture Diagram Generator'.")

    def test_decompose_output_llr_labels_are_human_readable(self):
        """LLR heading labels should be human-readable identifiers, not
        hash-based uid prefixes like ``llr_5e3e51b0``."""
        path = self._decompose_output_path()
        if not path.exists():
            pytest.skip("No decompose output file found")

        text = path.read_text(encoding="utf-8")

        for line in text.splitlines():
            m = re.match(r'^#{2,6}\s+LLR:\s+`([^`]+)`', line)
            if m:
                label = m.group(1)
                assert not re.match(r'^llr_[a-f0-9]+$', label), \
                    f"LLR label is a hash-based uid, not human-readable: {label!r}"

    # ── Heading-depth checks (no Neo4j needed) ───────────────────────

    def test_decompose_output_llrs_nested_under_hlr(self):
        """LLR headings in decompose output must be at depth 3 (###),
        nested under the HLR at depth 2 (##).  If LLRs are at depth 2
        (same as HLR), the importer won't create HLR→LLR COMPOSES edges.
        """
        path = self._decompose_output_path()
        if not path.exists():
            pytest.skip("No decompose output file found")

        text = path.read_text(encoding="utf-8")
        headings = self._extract_headings(text)

        # HLR must be at depth 2
        hlr_headings = [h for h in headings if h[1] == "HLR"]
        assert len(hlr_headings) >= 1, "No HLR heading found"
        assert all(h[0] == 2 for h in hlr_headings), \
            f"HLR must be at depth 2, got depths: {[(h[0], h[2]) for h in hlr_headings]}"

        # LLRs must be at depth 3 — NOT depth 2
        llr_headings = [h for h in headings if h[1] == "LLR"]
        assert len(llr_headings) >= 1, "No LLR headings found"
        assert all(h[0] == 3 for h in llr_headings), \
            (f"LLRs must be at depth 3 (###) to nest under HLR. "
             f"Got depths: {[(h[0], h[2]) for h in llr_headings]}. "
             f"LLRs at depth 2 (##) are siblings of the HLR, not children — "
             f"the importer won't create HLR→LLR COMPOSES edges.")

    # ── Neo4j ingestion check ────────────────────────────────────────

    def test_decompose_output_produces_composes_edges_on_ingestion(self):
        """Importing the decompose-generated file and persisting to Neo4j
        must produce HLR→LLR COMPOSES edges.  If LLRs are at the wrong
        heading depth, the importer won't create these edges and the
        LLRs will be orphaned.
        """
        path = self._decompose_output_path()
        if not path.exists():
            pytest.skip("No decompose output file found")

        text = path.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db

        # Count HLR→LLR COMPOSES edges
        results, _ = db.cypher_query(
            "MATCH (h:HLR)-[:COMPOSES]->(l:LLR) RETURN count(*)"
        )
        hlr_to_llr_count = results[0][0]

        # Count total LLRs
        llr_count_in_file = sum(
            1 for line in text.splitlines()
            if re.match(r'^#{2,6}\s+LLR:', line)
        )
        assert hlr_to_llr_count == llr_count_in_file, \
            (f"Expected {llr_count_in_file} HLR→LLR COMPOSES edges, "
             f"got {hlr_to_llr_count}. The importer failed to create "
             f"COMPOSES edges — LLRs are likely at the wrong heading depth.")

        # Verify no orphaned LLRs
        results, _ = db.cypher_query(
            "MATCH (l:LLR) WHERE NOT (l)<-[:COMPOSES]-(:HLR) "
            "RETURN l.qualified_name"
        )
        orphaned = [r[0] for r in results]
        assert len(orphaned) == 0, \
            f"Orphaned LLRs (no parent HLR via COMPOSES): {orphaned}"


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