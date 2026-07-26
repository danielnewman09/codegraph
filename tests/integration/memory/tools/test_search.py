"""Test memory search tools."""

import pytest


@pytest.fixture
def search_data(neo4j_connection):
    """Create test data for search tests."""
    from codegraph_memory import DecisionNode, ConstraintNode, InsightNode

    DecisionNode.save_new(
        qualified_name="memory::test-search-1",
        name="PostgreSQL Decision",
        content="Use PostgreSQL for relational data with ACID transactions.",
        tags=["design"], source="test",
    )
    DecisionNode.save_new(
        qualified_name="memory::test-search-2",
        name="Redis Decision",
        content="Use Redis for caching layer.",
        tags=["design", "as-built"], source="test",
    )
    ConstraintNode.save_new(
        qualified_name="memory::test-search-3",
        name="Latency Constraint",
        content="PostgreSQL query latency must be < 50ms at p99.",
        tags=["design"], source="test",
    )
    InsightNode.save_new(
        qualified_name="memory::test-search-4",
        name="Production Insight",
        content="PostgreSQL connection pooling improved throughput significantly.",
        tags=["as-built"], source="test",
    )


class TestSearchTools:
    """Test search tool functions."""

    def test_search_memory_basic(self, search_data):
        """search_memory finds memories by content keyword."""
        from codegraph_memory.tools.search import search_memory

        results = search_memory("PostgreSQL")
        assert len(results) >= 3  # decision, constraint, insight

        qnames = {r["qualified_name"] for r in results}
        assert "memory::test-search-1" in qnames
        assert "memory::test-search-3" in qnames
        assert "memory::test-search-4" in qnames

    def test_search_memory_with_tag_filter(self, search_data):
        """search_memory with tag filter returns only matching memories."""
        from codegraph_memory.tools.search import search_memory

        results = search_memory("PostgreSQL", tag="as-built")
        assert len(results) >= 1
        for r in results:
            assert "as-built" in r.get("tags", [])

    def test_search_memory_empty_query(self, search_data):
        """search_memory with empty query returns empty list."""
        from codegraph_memory.tools.search import search_memory

        results = search_memory("")
        assert results == []

    def test_search_memory_limit(self, search_data):
        """search_memory respects the limit parameter."""
        from codegraph_memory.tools.search import search_memory

        results = search_memory("memory", limit=2)
        assert len(results) <= 2