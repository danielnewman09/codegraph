"""Test InsightNode model."""

import pytest

from codegraph.backends import get_backend


class TestInsightNode:
    """Test InsightNode creation and INSIGHT_INTO relationship."""

    def test_create_insight(self, neo4j_connection):
        from codegraph_memory import InsightNode

        node = InsightNode.save_new(
            qualified_name="memory::test-insight",
            name="Test Insight",
            content="The batch processor was rewritten as streaming — chunking caused OOM under load.",
            tags=["as-built"],
            confidence=0.85,
            source="test",
        )
        assert node.qualified_name == "memory::test-insight"
        assert node.content.startswith("The batch processor")

    def test_insight_into_code_node(self, neo4j_connection):
        from codegraph_memory import InsightNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="BatchProcessor", kind="class",
            qualified_name="test::BatchProcessor",
            tags=["as-built"], source="test",
        )
        insight = InsightNode.save_new(
            qualified_name="memory::test-insight-into",
            name="OOM Insight",
            content="Chunking caused OOM under load.",
            tags=["as-built"], source="test",
        )
        insight.insight_into_compound.connect(cls)

        linked = get_backend().memory.find_linked_code_node(insight.uid)
        assert linked is not None
        assert linked["rel_type"] == "INSIGHT_INTO"

    def test_insight_registered(self, neo4j_connection):
        from codegraph.models.tags import CodeGraphNode
        assert "InsightNode" in CodeGraphNode._registry

    def test_insight_not_abstract(self, neo4j_connection):
        from codegraph_memory import InsightNode
        assert getattr(InsightNode, "__abstract__", True) is False
        assert getattr(InsightNode, "__label__", "InsightNode") == "InsightNode"