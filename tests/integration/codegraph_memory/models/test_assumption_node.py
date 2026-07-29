"""Test AssumptionNode model."""

import pytest

from codegraph.backends import get_backend


class TestAssumptionNode:
    """Test AssumptionNode creation and ASSUMES/CONTRADICTS relationships."""

    def test_create_assumption(self, neo4j_connection):
        from codegraph_memory import AssumptionNode

        node = AssumptionNode.save_new(
            qualified_name="memory::test-assumption",
            name="Test Assumption",
            content="Assumes the auth service is eventually consistent (≤ 5-second lag).",
            tags=["design"],
            confidence=0.3,  # speculative
            source="test",
        )
        assert node.qualified_name == "memory::test-assumption"
        assert node.confidence == 0.3

    def test_assumption_assumes_code_node(self, neo4j_connection):
        from codegraph_memory import AssumptionNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="AuthService", kind="class",
            qualified_name="test::AuthService",
            tags=["design"], source="test",
        )
        assumption = AssumptionNode.save_new(
            qualified_name="memory::test-assumes",
            name="Auth Assumption",
            content="Auth is eventually consistent.",
            tags=["design"], source="test",
        )
        assumption.assumes_compound.connect(cls)

        linked = get_backend().memory.find_linked_code_node(assumption.uid)
        assert linked is not None
        assert linked["rel_type"] == "ASSUMES"

    def test_assumption_contradicts(self, neo4j_connection):
        from codegraph_memory import AssumptionNode

        a1 = AssumptionNode.save_new(
            qualified_name="memory::test-assumption-1",
            name="Assumption 1",
            content="Assumes A.",
            tags=["design"], source="test",
        )
        a2 = AssumptionNode.save_new(
            qualified_name="memory::test-assumption-2",
            name="Assumption 2",
            content="Assumes NOT A.",
            tags=["design"], source="test",
        )
        a1.contradicts.connect(a2)

        assert a2 in a1.contradicts.all()
        assert a1 in a2.contradicted_by.all()

    def test_assumption_registered(self, neo4j_connection):
        from codegraph.models.tags import CodeGraphNode
        assert "AssumptionNode" in CodeGraphNode._registry

    def test_assumption_not_abstract(self, neo4j_connection):
        from codegraph_memory import AssumptionNode
        assert getattr(AssumptionNode, "__abstract__", True) is False
        assert AssumptionNode.__label__ == "AssumptionNode"