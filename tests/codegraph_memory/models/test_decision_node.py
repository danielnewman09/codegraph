"""Test DecisionNode model — creation, serialization, relationships."""

import pytest


class TestDecisionNode:
    """Test DecisionNode creation, tag management, and MOTIVATES relationship."""

    def test_create_decision(self, neo4j_connection):
        """DecisionNode can be created with required fields."""
        from codegraph_memory import DecisionNode

        node = DecisionNode.save_new(
            qualified_name="memory::test-decision",
            name="Test Decision",
            content="We chose X because of Y.",
            tags=["design"],
            source="test",
        )
        assert node.qualified_name == "memory::test-decision"
        assert node.content == "We chose X because of Y."
        assert "design" in node.tags
        assert node.confidence == 1.0  # default

    def test_decision_confidence(self, neo4j_connection):
        """DecisionNode accepts custom confidence values."""
        from codegraph_memory import DecisionNode

        node = DecisionNode.save_new(
            qualified_name="memory::test-confidence",
            name="Confident Decision",
            content="We are 80% sure.",
            tags=["design"],
            confidence=0.8,
            source="test",
        )
        assert node.confidence == 0.8

    def test_decision_timestamps(self, neo4j_connection):
        """DecisionNode sets decided_at and updated_at on save."""
        from codegraph_memory import DecisionNode

        node = DecisionNode.save_new(
            qualified_name="memory::test-timestamps",
            name="Timestamped Decision",
            content="Has timestamps.",
            tags=["design"],
            source="test",
        )
        assert node.decided_at is not None
        assert node.updated_at is not None

    def test_decision_uid_stable_across_content_change(self, neo4j_connection):
        """UID stays the same when content changes — identity is qualified_name, not content."""
        from codegraph_memory import DecisionNode

        node = DecisionNode.save_new(
            qualified_name="memory::test-uid",
            name="UID Test",
            content="Content A",
            tags=["design"],
            source="test",
        )
        original_uid = node.uid
        node.update(content="Content B - completely different")
        assert node.uid == original_uid

    def test_decision_motivates_code_node(self, neo4j_connection):
        """DecisionNode can MOTIVATE a code node."""
        from codegraph_memory import DecisionNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="TestClass", kind="class",
            qualified_name="test::TestClass",
            tags=["design"], source="test",
        )
        decision = DecisionNode.save_new(
            qualified_name="memory::test-motivates",
            name="Motivates Test",
            content="This decision motivated the class.",
            tags=["design"], source="test",
        )
        decision.motivates.connect(cls)

        # Verify via raw Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (d:DecisionNode)-[:MOTIVATES]->(c:ClassNode) "
            "WHERE d.qualified_name = $qname RETURN c",
            {"qname": "memory::test-motivates"},
        )
        assert len(results) == 1

    def test_decision_supersedes(self, neo4j_connection):
        """DecisionNode can supersede an older decision."""
        from codegraph_memory import DecisionNode

        old = DecisionNode.save_new(
            qualified_name="memory::test-old-choice",
            name="Old Choice",
            content="Original decision.",
            tags=["design"], source="test",
        )
        new = DecisionNode.save_new(
            qualified_name="memory::test-new-choice",
            name="New Choice",
            content="Updated decision.",
            tags=["design"], source="test",
        )
        new.supersedes.connect(old)

        assert old in new.supersedes.all()
        assert new in old.superseded_by.all()

    def test_decision_update(self, neo4j_connection):
        """DecisionNode.update() modifies fields and persists."""
        from codegraph_memory import DecisionNode

        node = DecisionNode.save_new(
            qualified_name="memory::test-update",
            name="Update Test",
            content="Original content.",
            tags=["design"], source="test",
        )
        original_uid = node.uid
        node.update(
            content="Updated content.",
            tags=["design", "as-built"],
            confidence=0.95,
        )
        # UID should stay the same — identity is qualified_name, not content
        assert node.uid == original_uid
        assert node.content == "Updated content."
        assert "as-built" in node.tags
        assert node.confidence == 0.95

    def test_decision_serialization(self, neo4j_connection):
        """DecisionNode serializes with correct type discriminator."""
        from codegraph_memory import DecisionNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="TestClass", kind="class",
            qualified_name="test::SerialClass",
            tags=["design"], source="test",
        )
        node = DecisionNode.save_new(
            qualified_name="memory::test-serial",
            name="Serial Test",
            content="Serialize me.",
            tags=["design"], source="test",
        )
        node.motivates.connect(cls)

        data = node.serialize()
        assert data["type"] == "DecisionNode"
        assert data["qualified_name"] == "memory::test-serial"
        assert data["content"] == "Serialize me."
        assert "design" in data["tags"]

    def test_decision_registered_in_registry(self, neo4j_connection):
        """DecisionNode is registered in CodeGraphNode._registry."""
        from codegraph.models.tags import CodeGraphNode
        assert "DecisionNode" in CodeGraphNode._registry

    def test_decision_not_abstract(self, neo4j_connection):
        """DecisionNode is not abstract (can be instantiated)."""
        from codegraph_memory import DecisionNode
        assert getattr(DecisionNode, "__abstract__", True) is False
        assert hasattr(DecisionNode, "__label__")
        assert DecisionNode.__label__ == "DecisionNode"