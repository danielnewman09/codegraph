"""Test memory lookup tools."""

import pytest


@pytest.fixture
def populated_data(neo4j_connection):
    """Create test data for tool tests."""
    from codegraph_memory import DecisionNode, ConstraintNode, InsightNode
    from codegraph.models.compound import ClassNode

    cls = ClassNode.save_new(
        name="MyService", kind="class",
        qualified_name="test::MyService",
        tags=["design"], source="test",
    )

    old = DecisionNode.save_new(
        qualified_name="memory::test-old-dec",
        name="Old Decision",
        content="Use HTTP/1.1",
        tags=["design"], source="test",
    )
    old.motivates.connect(cls)

    new = DecisionNode.save_new(
        qualified_name="memory::test-new-dec",
        name="New Decision",
        content="Use HTTP/2 for multiplexing",
        tags=["design"], source="test",
    )
    new.motivates.connect(cls)
    new.supersedes.connect(old)

    constraint = ConstraintNode.save_new(
        qualified_name="memory::test-constraint",
        name="Throughput",
        content="Must support 10k req/sec",
        tags=["design"], source="test",
    )
    constraint.constrains.connect(cls)

    insight = InsightNode.save_new(
        qualified_name="memory::test-insight",
        name="Production Learning",
        content="HTTP/2 multiplexing reduced connection overhead by 40%",
        tags=["as-built"], source="test",
    )
    insight.insight_into.connect(cls)

    return {"class": cls, "old_dec": old, "new_dec": new, "constraint": constraint, "insight": insight}


class TestLookupTools:
    """Test lookup tool functions."""

    def test_memory_of(self, populated_data):
        """memory_of returns all memory nodes for a code node."""
        from codegraph_memory.tools.lookup import memory_of

        results = memory_of("test::MyService")
        assert len(results) >= 4
        types = {r["type"] for r in results}
        assert "DecisionNode" in types
        assert "ConstraintNode" in types
        assert "InsightNode" in types

    def test_constraints_for(self, populated_data):
        """constraints_for returns constraints for a code node."""
        from codegraph_memory.tools.lookup import constraints_for

        results = constraints_for("test::MyService")
        assert len(results) == 1
        assert results[0]["qualified_name"] == "memory::test-constraint"

    def test_decision_chain(self, populated_data):
        """decision_chain returns decisions with supersession chain."""
        from codegraph_memory.tools.lookup import decision_chain

        results = decision_chain("test::MyService")
        assert len(results) >= 2

        # Find the new decision (which supersedes the old one)
        new_result = next(r for r in results if r["qualified_name"] == "memory::test-new-dec")
        assert "supersession_chain" in new_result
        # The chain should include the old decision
        chain_qnames = [item["qualified_name"] for item in new_result["supersession_chain"]]
        assert "memory::test-old-dec" in chain_qnames

    def test_insights_for(self, populated_data):
        """insights_for returns insights for a code node."""
        from codegraph_memory.tools.lookup import insights_for

        results = insights_for("test::MyService")
        assert len(results) == 1
        assert results[0]["qualified_name"] == "memory::test-insight"

    def test_affected_decisions(self, populated_data):
        """affected_decisions returns memories for a code node and children."""
        from codegraph_memory.tools.lookup import affected_decisions

        results = affected_decisions("test::MyService")
        assert len(results) >= 1