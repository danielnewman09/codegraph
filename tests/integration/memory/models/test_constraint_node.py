"""Test ConstraintNode model."""

import pytest

from codegraph.backends import get_backend


class TestConstraintNode:
    """Test ConstraintNode creation and CONSTRAINS relationship."""

    def test_create_constraint(self, neo4j_connection):
        from codegraph_memory import ConstraintNode

        node = ConstraintNode.save_new(
            qualified_name="memory::test-constraint",
            name="Test Constraint",
            content="Must handle 10k concurrent connections.",
            tags=["design"],
            confidence=0.9,
            source="test",
        )
        assert node.qualified_name == "memory::test-constraint"
        assert node.content == "Must handle 10k concurrent connections."
        assert node.confidence == 0.9

    def test_constraint_constrains_code_node(self, neo4j_connection):
        from codegraph_memory import ConstraintNode
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="TestService", kind="class",
            qualified_name="test::TestService",
            tags=["design"], source="test",
        )
        constraint = ConstraintNode.save_new(
            qualified_name="memory::test-constrains",
            name="SLA",
            content="p99 < 50ms",
            tags=["design"], source="test",
        )
        constraint.constrains_compound.connect(cls)

        linked = get_backend().memory.find_linked_code_node(constraint.uid)
        assert linked is not None
        assert linked["rel_type"] == "CONSTRAINS"

    def test_constraint_registered(self, neo4j_connection):
        from codegraph.models.tags import CodeGraphNode
        assert "ConstraintNode" in CodeGraphNode._registry

    def test_constraint_not_abstract(self, neo4j_connection):
        from codegraph_memory import ConstraintNode
        assert getattr(ConstraintNode, "__abstract__", True) is False
        assert getattr(ConstraintNode, "__label__", "ConstraintNode") == "ConstraintNode"