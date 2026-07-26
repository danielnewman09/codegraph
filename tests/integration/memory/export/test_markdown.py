"""Test markdown export tools."""

import pytest


@pytest.fixture
def export_data(neo4j_connection):
    """Create test data for export tests."""
    from codegraph_memory import DecisionNode, RationaleNode, TradeoffNode
    from codegraph.models.compound import ClassNode

    cls = ClassNode.save_new(
        name="ExportTest", kind="class",
        qualified_name="test::ExportTest",
        tags=["design", "as-built"], source="test",
    )

    decision = DecisionNode.save_new(
        qualified_name="memory::test-export-decision",
        name="Export Decision",
        content="Use SQLAlchemy ORM over PostgreSQL for portability.",
        tags=["design", "as-built"], confidence=0.95, source="test",
    )
    decision.motivates_compound.connect(cls)

    rationale = RationaleNode.save_new(
        qualified_name="memory::test-export-rationale",
        name="CI Portability",
        content="The abstraction layer exists for CI portability with SQLite.",
        tags=["design", "as-built"], confidence=0.95, source="test",
    )
    rationale.refines.connect(decision)

    tradeoff = TradeoffNode.save_new(
        qualified_name="memory::test-export-tradeoff",
        name="ORM Overhead",
        content="SQLAlchemy adds ~20ms per query vs raw psycopg2.",
        tags=["as-built"], confidence=0.9, source="test",
    )
    tradeoff.trades_off_compound.connect(cls)

    return {"cls": cls, "decision": decision}


class TestMarkdownExport:
    """Test markdown export functions."""

    def test_export_adr(self, export_data):
        """export_adr produces a structured ADR document."""
        from codegraph_memory.export.markdown import export_adr

        adr = export_adr("memory::test-export-decision")
        assert "Decision:" in adr
        assert "SQLAlchemy" in adr
        assert "Context" in adr
        assert "Motivated Code" in adr
        assert "test::ExportTest" in adr

    def test_export_adr_not_found(self, neo4j_connection):
        """export_adr returns a comment for non-existent decisions."""
        from codegraph_memory.export.markdown import export_adr

        adr = export_adr("memory::nonexistent")
        assert "not found" in adr

    def test_export_memory_summary(self, export_data):
        """export_memory_summary produces a design context document."""
        from codegraph_memory.export.markdown import export_memory_summary

        summary = export_memory_summary("test::ExportTest")
        assert "Memory for" in summary
        assert "test::ExportTest" in summary
        assert "Decisions" in summary
        assert "Tradeoffs" in summary

    def test_export_memory_summary_empty(self, neo4j_connection):
        """export_memory_summary returns message for no memories."""
        from codegraph_memory.export.markdown import export_memory_summary
        from codegraph.models.compound import ClassNode

        ClassNode.save_new(
            name="EmptyTest", kind="class",
            qualified_name="test::EmptyTest",
            tags=["design"], source="test",
        )

        summary = export_memory_summary("test::EmptyTest")
        assert "No memory" in summary