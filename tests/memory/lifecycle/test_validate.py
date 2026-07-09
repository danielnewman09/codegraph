"""Test memory lifecycle validation tools."""

import pytest


@pytest.fixture
def lifecycle_data(neo4j_connection):
    """Create test data with design/as-built tag gaps."""
    from codegraph_memory import DecisionNode, AssumptionNode
    from codegraph.models.compound import ClassNode

    # Design-tagged code node (not yet built)
    design_cls = ClassNode.save_new(
        name="DesignOnly", kind="class",
        qualified_name="test::DesignOnly",
        tags=["design"], source="test",
    )

    # Decision linked to design-only code (not implemented yet)
    decision = DecisionNode.save_new(
        qualified_name="memory::test-lifecycle-decision",
        name="Design Decision",
        content="Use PostgreSQL for DesignOnly.",
        tags=["design"], source="test",
    )
    decision.motivates.connect(design_cls)

    # As-built code node (implemented, no design tag)
    built_cls = ClassNode.save_new(
        name="AsBuiltOnly", kind="class",
        qualified_name="test::AsBuiltOnly",
        tags=["as-built"], source="test",
    )

    # Insight linked to as-built-only code (undocumented implementation)
    insight = AssumptionNode.save_new(
        qualified_name="memory::test-lifecycle-assumption",
        name="Built Assumption",
        content="Assumes the cache is warm.",
        tags=["as-built"], source="test",
    )
    insight.assumes.connect(built_cls)

    return {"design_cls": design_cls, "built_cls": built_cls, "decision": decision, "insight": insight}


class TestValidateMemories:
    """Test validate_memories and tag_gap_report."""

    def test_validate_memories_design_not_implemented(self, lifecycle_data):
        """validate_memories finds design-tagged memories without as-built code."""
        from codegraph_memory.lifecycle.validate import validate_memories

        findings = validate_memories("test")
        statuses = {f["status"] for f in findings}
        assert "design_not_implemented" in statuses

    def test_validate_memories_undocumented_impl(self, lifecycle_data):
        """validate_memories finds as-built memories without design code."""
        from codegraph_memory.lifecycle.validate import validate_memories

        findings = validate_memories("test")
        statuses = {f["status"] for f in findings}
        assert "undocumented_impl" in statuses

    def test_tag_gap_report(self, lifecycle_data):
        """tag_gap_report returns correct counts."""
        from codegraph_memory.lifecycle.validate import tag_gap_report

        report = tag_gap_report("test")
        assert "total" in report
        assert "validated" in report
        assert "design_only" in report
        assert "built_only" in report
        assert "unvalidated_decisions" in report
        assert report["total"] >= 2
        assert report["design_only"] >= 1