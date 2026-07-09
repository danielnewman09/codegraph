"""Test RationaleNode model."""

import pytest


class TestRationaleNode:
    """Test RationaleNode creation and EXPLAINS/REFINES relationships."""

    def test_create_rationale(self, neo4j_connection):
        from codegraph_memory import RationaleNode

        node = RationaleNode.save_new(
            qualified_name="memory::test-rationale",
            name="Test Rationale",
            content="This caching layer exists because the upstream API has a 100ms floor.",
            tags=["design"],
            source="test",
        )
        assert node.qualified_name == "memory::test-rationale"
        assert node.content.startswith("This caching layer")

    def test_rationale_explains_code_node(self, neo4j_connection):
        from codegraph_memory import RationaleNode
        from codegraph.models.member import MethodNode

        method = MethodNode.save_new(
            name="cacheResult", kind="method",
            qualified_name="test::Service::cacheResult",
            tags=["design"], source="test",
        )
        rationale = RationaleNode.save_new(
            qualified_name="memory::test-explains",
            name="Why cacheResult",
            content="Caches because upstream is slow.",
            tags=["design"], source="test",
        )
        rationale.explains.connect(method)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (r:RationaleNode)-[:EXPLAINS]->(t) "
            "WHERE r.qualified_name = $qname RETURN t",
            {"qname": "memory::test-explains"},
        )
        assert len(results) == 1

    def test_rationale_refines_decision(self, neo4j_connection):
        from codegraph_memory import RationaleNode, DecisionNode

        decision = DecisionNode.save_new(
            qualified_name="memory::test-refine-decision",
            name="Decision",
            content="Use caching.",
            tags=["design"], source="test",
        )
        rationale = RationaleNode.save_new(
            qualified_name="memory::test-refines",
            name="Refines caching",
            content="Specifically, LRU cache with TTL.",
            tags=["design"], source="test",
        )
        rationale.refines.connect(decision)

        assert decision in rationale.refines.all()

    def test_rationale_registered(self, neo4j_connection):
        from codegraph.models.tags import CodeGraphNode
        assert "RationaleNode" in CodeGraphNode._registry

    def test_rationale_not_abstract(self, neo4j_connection):
        from codegraph_memory import RationaleNode
        assert getattr(RationaleNode, "__abstract__", True) is False
        assert RationaleNode.__label__ == "RationaleNode"