"""Test TradeoffNode model."""

import pytest

from codegraph.backends import get_backend


class TestTradeoffNode:
    """Test TradeoffNode creation and TRADES_OFF relationship."""

    def test_create_tradeoff(self, neo4j_connection):
        from codegraph_memory import TradeoffNode

        node = TradeoffNode.save_new(
            qualified_name="memory::test-tradeoff",
            name="Test Tradeoff",
            content="Accepts 2x memory for 10x read throughput.",
            tags=["design"],
            confidence=0.9,
            source="test",
        )
        assert node.qualified_name == "memory::test-tradeoff"
        assert node.content.startswith("Accepts 2x memory")

    def test_tradeoff_trades_off_code_node(self, neo4j_connection):
        from codegraph_memory import TradeoffNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="Cache", kind="class",
            qualified_name="test::Cache",
            tags=["design"], source="test",
        )
        tradeoff = TradeoffNode.save_new(
            qualified_name="memory::test-trades-off",
            name="Memory Tradeoff",
            content="2x memory for 10x speed.",
            tags=["design"], source="test",
        )
        tradeoff.trades_off_compound.connect(cls)

        linked = get_backend().memory.find_linked_code_node(tradeoff.uid)
        assert linked is not None
        assert linked["rel_type"] == "TRADES_OFF"

    def test_tradeoff_registered(self, neo4j_connection):
        from codegraph.models.tags import CodeGraphNode
        assert "TradeoffNode" in CodeGraphNode._registry

    def test_tradeoff_not_abstract(self, neo4j_connection):
        from codegraph_memory import TradeoffNode
        assert getattr(TradeoffNode, "__abstract__", True) is False
        assert TradeoffNode.__label__ == "TradeoffNode"