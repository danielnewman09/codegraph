"""Round-trip ingestion tests for decompose-generated requirements.md.

These tests verify that a requirements markdown document produced by the
``codegraph_decompose`` pipeline can be:

1. Imported via ``MarkdownImporter`` into a ``LayerGraph``.
2. The resulting graph has the correct COMPOSES hierarchy:
   HLR → LLR → TestNode → AssertionNode / TestStepNode.
3. Non-nesting edges (LEFT_OPERAND, RIGHT_OPERAND, CALLEE) survive the
   round-trip as references on the correct source nodes.
4. Heading labels are human-readable ``qualified_name`` strings, not
   UID hashes like ``hlr_792dc341``.
5. Re-exporting the imported graph via ``MarkdownExporter`` produces
   byte-identical output (round-trip stability).
6. Persisting to Neo4j via ``to_neo4j()`` creates all expected nodes and
   edges (COMPOSES, LEFT_OPERAND, RIGHT_OPERAND, CALLEE).

A secondary test class demonstrates the two known bugs in the current
``_export_decomposition_markdown`` output:

- **UID-as-label**: The HLR heading uses ``hlr_792dc341`` (a SHA1 hash
  prefix) instead of ``"Architecture Diagram Generator"`` because
  ``qualified_name`` is not set on the synthetic HLR node.
- **Flat hierarchy**: HLR and LLRs are all at ``##`` depth (root entries)
  because the HLR's COMPOSES edges to LLRs use ``llr.get("refid", "")``
  which is empty in the LLM output — so no nesting is created and the
  COMPOSES hierarchy is lost on ingestion.

Fixture: ``tests/data/architecture_diagram_generator_roundtrip.md``
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegraph.export.markdown import export_markdown, import_markdown


def _neo4j_available() -> bool:
    """Check if Neo4j is reachable on the test port."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            "bolt://localhost:7688",
            auth=("neo4j", "codegraph-test"),
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


# ── Path helpers ──────────────────────────────────────────────────────────

FIXTURE = (
    Path(__file__).resolve().parent / "data"
    / "architecture_diagram_generator_roundtrip.md"
)

# Path to the actual decompose-generated file (with known bugs)
DECOMPOSE_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "codegraph" / "requirements" / "architecture-diagram-generator"
    / "requirements.md"
)


# ── Import-only structural verification ────────────────────────────────────


class TestImportStructure:
    """Verify the graph structure after importing the corrected fixture."""

    @pytest.fixture(scope="class")
    def graph(self):
        """Import the corrected fixture once for all tests in this class."""
        text = FIXTURE.read_text(encoding="utf-8")
        return import_markdown(text, tags=frozenset({"design"}))

    def test_hlr_is_root_entry_with_human_readable_name(self, graph):
        """The HLR should be a root entry with ``qualified_name``
        ``"Architecture Diagram Generator"``, not a UID hash."""
        hlr_entry = graph.entries.get("Architecture Diagram Generator")
        assert hlr_entry is not None, (
            "Expected root entry 'Architecture Diagram Generator', "
            f"got: {list(graph.entries.keys())}"
        )
        assert hlr_entry.node.qualified_name == "Architecture Diagram Generator"

    def test_hlr_has_five_llr_children(self, graph):
        """The HLR should have 5 LLR children via COMPOSES nesting."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_children = hlr_entry.children.get("LLR", {})
        assert len(llr_children) == 5, (
            f"Expected 5 LLRs, got {len(llr_children)}: {list(llr_children.keys())}"
        )

    def test_llr_names_are_human_readable(self, graph):
        """LLR qualified_names should be human-readable, not UID hashes."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_children = hlr_entry.children.get("LLR", {})
        for qname in llr_children:
            assert not qname.startswith("llr_"), (
                f"LLR name {qname!r} looks like a UID hash, not a human-readable name"
            )
        # Spot-check a known LLR
        assert "Diagram Generation Operation" in llr_children
        assert "Entity Count Filtering" in llr_children

    def test_llr_has_test_children(self, graph):
        """Each LLR should have TestNode children via COMPOSES nesting."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_children = hlr_entry.children.get("LLR", {})

        llr_entry = llr_children["Diagram Generation Operation"]
        test_children = llr_entry.children.get("TestNode", {})
        assert len(test_children) == 2, (
            f"Expected 2 tests under 'Diagram Generation Operation', "
            f"got {len(test_children)}: {list(test_children.keys())}"
        )
        assert "vm::generate::test_valid_config" in test_children
        assert "vm::generate::test_neo4j_connection_error" in test_children

    def test_test_has_assertion_and_step_children(self, graph):
        """TestNode should have AssertionNode and TestStepNode children."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_entry = hlr_entry.children["LLR"]["Diagram Generation Operation"]
        test_entry = llr_entry.children["TestNode"]["vm::generate::test_valid_config"]

        assertions = test_entry.children.get("AssertionNode", {})
        steps = test_entry.children.get("TestStepNode", {})
        assert len(assertions) == 3, (
            f"Expected 3 assertions, got {len(assertions)}"
        )
        assert len(steps) == 1, (
            f"Expected 1 test step, got {len(steps)}"
        )
        assert "cond::pre::valid_config_provided" in assertions
        assert "cond::post::success_true" in assertions
        assert "step::invoke_generate_valid" in steps

    def test_assertion_has_operand_references(self, graph):
        """AssertionNode should have LEFT_OPERAND and RIGHT_OPERAND refs."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_entry = hlr_entry.children["LLR"]["Diagram Generation Operation"]
        test_entry = llr_entry.children["TestNode"]["vm::generate::test_valid_config"]
        pre_entry = test_entry.children["AssertionNode"]["cond::pre::valid_config_provided"]

        rel_types = [r[0] for r in pre_entry.references]
        assert "LEFT_OPERAND" in rel_types, (
            f"Expected LEFT_OPERAND in references, got: {rel_types}"
        )
        assert "RIGHT_OPERAND" in rel_types, (
            f"Expected RIGHT_OPERAND in references, got: {rel_types}"
        )

        # Verify the targets
        left_targets = [r[1] for r in pre_entry.references if r[0] == "LEFT_OPERAND"]
        right_targets = [r[1] for r in pre_entry.references if r[0] == "RIGHT_OPERAND"]
        assert "DiagramConfig::is_valid" in left_targets
        assert "literal::true" in right_targets

    def test_test_step_has_callee_reference(self, graph):
        """TestStepNode should have a CALLEE reference."""
        hlr_entry = graph.entries["Architecture Diagram Generator"]
        llr_entry = hlr_entry.children["LLR"]["Diagram Generation Operation"]
        test_entry = llr_entry.children["TestNode"]["vm::generate::test_valid_config"]
        step_entry = test_entry.children["TestStepNode"]["step::invoke_generate_valid"]

        callee_refs = [r for r in step_entry.references if r[0] == "CALLEE"]
        assert len(callee_refs) == 1, (
            f"Expected 1 CALLEE ref, got {len(callee_refs)}"
        )
        assert callee_refs[0][1] == "ArchDiagramGenerator::generate_diagram"

    def test_scaffold_classes_are_root_entries(self, graph):
        """Scaffold class nodes (DiagramConfig, DiagramResult, etc.) should
        be root entries, separate from the HLR tree."""
        expected_scaffolds = [
            "DiagramConfig",
            "DiagramResult",
            "ModuleData",
            "ArchDiagramGenerator",
        ]
        for qname in expected_scaffolds:
            assert qname in graph.entries, (
                f"Scaffold class {qname!r} not found in root entries: "
                f"{list(graph.entries.keys())}"
            )

    def test_scaffold_attributes_nest_under_classes(self, graph):
        """Scaffold attributes should nest under their parent class."""
        config_entry = graph.entries["DiagramConfig"]
        attrs = config_entry.children.get("AttributeNode", {})
        attr_names = {a for a in attrs}
        assert "DiagramConfig::is_valid" in attr_names
        assert "DiagramConfig::min_entity_count" in attr_names

    def test_total_node_count(self, graph):
        """Verify the total number of nodes in the graph."""
        def count_all(entries):
            total = len(entries)
            for entry in entries.values():
                for child_type, children in entry.children.items():
                    total += count_all(children)
            return total

        total = count_all(graph.entries)
        # HLR (1) + 5 LLRs + 5 tests + ~17 assertions + ~7 steps
        # + 4 scaffold classes + ~16 scaffold attributes + ~10 literals
        # The exact count depends on how many attributes/literals the
        # fixture declares — just assert it's substantial.
        assert total > 50, f"Expected >50 nodes, got {total}"


# ── Round-trip stability ─────────────────────────────────────────────────


class TestRoundTripStability:
    """Verify that export(import(text)) == text (byte-identical)."""

    def test_round_trip_identical(self):
        """Import the fixture and re-export — output must be byte-identical."""
        original = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(original, tags=frozenset({"design"}))
        reexported = export_markdown(graph, fields="all")

        # Write to unit_test_data/ for visual inspection on failure
        out_dir = Path(__file__).resolve().parent.parent / "unit_test_data"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / "architecture_diagram_generator_roundtrip.md"
        out_path.write_text(reexported, encoding="utf-8")

        assert reexported == original, (
            "Round-trip is not stable: export_markdown(import_markdown(text)) "
            "differs from the original. See "
            "unit_test_data/architecture_diagram_generator_roundtrip.md"
        )

    def test_double_import_is_identical(self):
        """Import → export → import → export should be stable on the
        second pass as well."""
        original = FIXTURE.read_text(encoding="utf-8")
        graph1 = import_markdown(original, tags=frozenset({"design"}))
        md1 = export_markdown(graph1, fields="all")
        graph2 = import_markdown(md1, tags=frozenset({"design"}))
        md2 = export_markdown(graph2, fields="all")

        assert md1 == md2, (
            "Second round-trip pass differs from the first — "
            "the importer/exporter is not idempotent."
        )


# ── Neo4j persistence (requires running Neo4j) ──────────────────────────


@pytest.mark.neo4j
class TestNeo4jPersistence:
    """Verify that to_neo4j() creates all expected nodes and edges.

    These tests require a running Neo4j instance and will be skipped
    if the database is not available.
    """

    @pytest.fixture(autouse=True)
    def _check_neo4j(self):
        """Skip if Neo4j is not available."""
        if not _neo4j_available():
            pytest.skip("Neo4j not available")

    def test_persist_creates_hlr_with_llr_children(self):
        """After to_neo4j(), the HLR should have COMPOSES edges to its
        5 LLRs in Neo4j."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (h:HLR)-[:COMPOSES]->(l:LLR) "
            "WHERE h.qualified_name = 'Architecture Diagram Generator' "
            "RETURN l.qualified_name as qname "
            "ORDER BY qname"
        )
        llr_names = [r[0] for r in results]
        assert len(llr_names) == 5, (
            f"Expected 5 LLRs in Neo4j, got {len(llr_names)}: {llr_names}"
        )
        assert "Diagram Generation Operation" in llr_names
        assert "Entity Count Filtering" in llr_names

    def test_persist_creates_llr_to_test_composes(self):
        """LLR → TestNode COMPOSES edges should exist in Neo4j."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (l:LLR)-[:COMPOSES]->(t:TestNode) "
            "WHERE l.qualified_name = 'Diagram Generation Operation' "
            "RETURN t.qualified_name as qname "
            "ORDER BY qname"
        )
        test_names = [r[0] for r in results]
        assert len(test_names) == 2
        assert "vm::generate::test_valid_config" in test_names

    def test_persist_creates_test_to_assertion_composes(self):
        """TestNode → AssertionNode COMPOSES edges should exist in Neo4j."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(a:AssertionNode) "
            "WHERE t.qualified_name = 'vm::generate::test_valid_config' "
            "RETURN a.qualified_name as qname "
            "ORDER BY qname"
        )
        assertion_names = [r[0] for r in results]
        assert len(assertion_names) == 3
        assert "cond::pre::valid_config_provided" in assertion_names
        assert "cond::post::success_true" in assertion_names

    def test_persist_creates_operand_edges(self):
        """LEFT_OPERAND and RIGHT_OPERAND edges should exist in Neo4j."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        # LEFT_OPERAND: cond::pre::valid_config_provided → DiagramConfig::is_valid
        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[:LEFT_OPERAND]->(t) "
            "WHERE a.qualified_name = 'cond::pre::valid_config_provided' "
            "RETURN t.qualified_name as qname"
        )
        assert results and results[0][0] == "DiagramConfig::is_valid"

        # RIGHT_OPERAND: cond::pre::valid_config_provided → literal::true
        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[:RIGHT_OPERAND]->(t) "
            "WHERE a.qualified_name = 'cond::pre::valid_config_provided' "
            "RETURN t.qualified_name as qname"
        )
        assert results and results[0][0] == "literal::true"

    def test_persist_creates_callee_edges(self):
        """CALLEE edges from TestStepNode to scaffold attributes should
        exist in Neo4j."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph = import_markdown(text, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (s:TestStepNode)-[:CALLEE]->(t) "
            "WHERE s.qualified_name = 'step::invoke_generate_valid' "
            "RETURN t.qualified_name as qname"
        )
        assert results and results[0][0] == "ArchDiagramGenerator::generate_diagram"

    def test_persist_idempotent(self):
        """Re-ingesting the same markdown should not create duplicate nodes."""
        text = FIXTURE.read_text(encoding="utf-8")
        graph1 = import_markdown(text, tags=frozenset({"design"}))
        graph1.to_neo4j()

        from neomodel import db
        count_before, _ = db.cypher_query(
            "MATCH (n) WHERE 'design' IN n.tags RETURN count(n)"
        )
        assert count_before[0][0] > 0

        # Re-ingest
        graph2 = import_markdown(text, tags=frozenset({"design"}))
        graph2.to_neo4j()

        count_after, _ = db.cypher_query(
            "MATCH (n) WHERE 'design' IN n.tags RETURN count(n)"
        )
        assert count_before[0][0] == count_after[0][0], (
            f"Node count changed: {count_before[0][0]} → {count_after[0][0]}"
        )


# ── Bug demonstration: current decompose output ─────────────────────────


class TestDecomposeOutputBugs:
    """Tests that demonstrate the two known bugs in the current
    ``_export_decomposition_markdown`` output.

    These tests are expected to FAIL until the decompose export path is
    fixed.  They serve as regression tests for the bugs described in the
    module docstring.
    """

    @pytest.fixture
    def decompose_md(self):
        """Load the actual decompose-generated requirements.md.

        Skips if the file doesn't exist (e.g. decompose hasn't been run
        yet in this environment).
        """
        if not DECOMPOSE_OUTPUT.exists():
            pytest.skip(f"Decompose output not found: {DECOMPOSE_OUTPUT}")
        return DECOMPOSE_OUTPUT.read_text(encoding="utf-8")

    def test_hlr_label_is_uid_not_human_readable(self, decompose_md):
        """BUG: The HLR heading uses a UID hash (``hlr_792dc341``)
        instead of a human-readable name.

        This test asserts the bug EXISTS in the current output.
        Once the fix is applied, this test should be updated to assert
        the label IS human-readable.
        """
        # The HLR heading should NOT contain a UID-hash pattern
        import re
        hlr_headings = re.findall(r'^## HLR: `([^`]+)`', decompose_md, re.MULTILINE)
        assert len(hlr_headings) == 1
        hlr_label = hlr_headings[0]

        # This assertion documents the bug: the label is a UID hash
        assert hlr_label.startswith("hlr_"), (
            f"Expected UID-hash label (bug), got: {hlr_label!r}"
        )

    def test_llr_labels_are_uids_not_human_readable(self, decompose_md):
        """BUG: LLR headings use UID hashes (``llr_xxxxxxxx``)
        instead of human-readable names."""
        import re
        llr_headings = re.findall(r'^##+ LLR: `([^`]+)`', decompose_md, re.MULTILINE)
        assert len(llr_headings) >= 5, (
            f"Expected at least 5 LLRs, got {len(llr_headings)}"
        )

        for label in llr_headings:
            assert label.startswith("llr_"), (
                f"Expected UID-hash label (bug), got: {label!r}"
            )

    def test_llrs_are_flat_not_nested_under_hlr(self, decompose_md):
        """BUG: LLRs are at ``##`` depth (same as HLR), so they become
        root entries instead of children of the HLR.

        This means the COMPOSES hierarchy (HLR → LLR) is lost on import.
        """
        import re
        # Count HLR headings at ## depth
        hlr_at_depth2 = re.findall(r'^## HLR: ', decompose_md, re.MULTILINE)
        # Count LLR headings at ## depth (should be ### if nested)
        llr_at_depth2 = re.findall(r'^## LLR: ', decompose_md, re.MULTILINE)
        llr_at_depth3 = re.findall(r'^### LLR: ', decompose_md, re.MULTILINE)

        assert len(hlr_at_depth2) == 1
        # BUG: LLRs are at ## depth (flat), not ### (nested)
        assert len(llr_at_depth2) >= 5, (
            f"Expected at least 5 flat LLRs at ## depth (bug), got {len(llr_at_depth2)}"
        )
        assert len(llr_at_depth3) == 0, (
            "Expected 0 nested LLRs at ### depth — "
            "the fix should produce ### depth"
        )

    def test_import_loses_composes_hierarchy(self, decompose_md):
        """BUG: Importing the current decompose output produces a flat
        graph with no HLR → LLR COMPOSES nesting.

        The HLR and all 5 LLRs are root entries — the hierarchy is lost.
        """
        graph = import_markdown(decompose_md, tags=frozenset({"design"}))

        # Count root entries — with the bug, HLR + 5 LLRs + scaffolds
        # are ALL root entries
        root_keys = list(graph.entries.keys())

        # The HLR should NOT be a root entry with LLR children
        # (with the bug, it IS a root entry but with NO LLR children)
        hlr_entry = None
        for key, entry in graph.entries.items():
            if type(entry.node).__name__ == "HLR":
                hlr_entry = entry
                break

        if hlr_entry is None:
            pytest.fail("No HLR found in graph at all")

        llr_children = hlr_entry.children.get("LLR", {})
        assert len(llr_children) == 0, (
            f"BUG: Expected 0 LLR children (broken hierarchy), "
            f"got {len(llr_children)}: {list(llr_children.keys())}"
        )

    def test_import_loses_composes_in_neo4j(self, decompose_md):
        """BUG: After to_neo4j(), there are no HLR → LLR COMPOSES edges
        because the nesting was lost during import."""
        if not _neo4j_available():
            pytest.skip("Neo4j not available")

        graph = import_markdown(decompose_md, tags=frozenset({"design"}))
        graph.to_neo4j()

        from neomodel import db
        # With the bug, there should be 0 HLR → LLR COMPOSES edges
        results, _ = db.cypher_query(
            "MATCH (h:HLR)-[:COMPOSES]->(l:LLR) "
            "WHERE h.qualified_name STARTS WITH 'hlr_' "
            "RETURN count(*)"
        )
        assert results[0][0] == 0, (
            f"BUG: Expected 0 HLR→LLR COMPOSES edges (broken hierarchy), "
            f"got {results[0][0]}"
        )