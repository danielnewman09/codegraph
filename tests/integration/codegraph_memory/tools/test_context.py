"""Tests for memory_context — the primary read-side tool for agents."""

from __future__ import annotations

import pytest

from codegraph.models.compound import ClassNode
from codegraph.models.namespace import NamespaceNode
from codegraph.backends import get_backend
from codegraph_memory.tools.context import memory_context
from codegraph_memory.tools.record import record_memory


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def hierarchy():
    """Create a namespace → class → method hierarchy with memories at each level."""
    ns = NamespaceNode(qualified_name="testapp", source="test")
    ns.save()

    cls = ClassNode(qualified_name="testapp::DatabaseLayer", source="test")
    cls.save()

    # Link class into namespace via COMPOSES
    get_backend().graph.merge_relationship(ns.canonical_key, "COMPOSES", cls.canonical_key)

    # Create memories at each level
    # Namespace-level constraint
    record_memory(
        type="constraint",
        qualified_name="memory::app-constraint",
        content="All DB access must go through the DAL.",
        links_to="testapp",
    )

    # Class-level decision
    record_memory(
        type="decision",
        qualified_name="memory::dal-choice",
        content="Use asyncpg for async DB access.",
        links_to="testapp::DatabaseLayer",
    )

    # Class-level assumption
    record_memory(
        type="assumption",
        qualified_name="memory::pool-ready",
        content="Connection pool is always initialized before use.",
        confidence=0.3,
        links_to="testapp::DatabaseLayer",
    )

    yield {
        "namespace": ns,
        "class": cls,
    }

    # Cleanup is handled by the parent conftest's clear_db fixture
    # which wipes the database after every test.


# ── Direct memories ───────────────────────────────────────────────────

class TestDirect:
    """Memories directly linked to the target node."""

    def test_direct_memories(self, hierarchy):
        result = memory_context("testapp::DatabaseLayer")
        assert result["error"] is None
        assert result["target"]["kind"] == "ClassNode"

        direct = result["direct"]
        assert len(direct) == 2  # decision + assumption

        types = {m["type"] for m in direct}
        assert "DecisionNode" in types
        assert "AssumptionNode" in types

    def test_direct_memories_none(self, hierarchy):
        """Target with no direct memories."""
        # Create a class with no memories
        cls = ClassNode(qualified_name="testapp::EmptyClass", source="test")
        cls.save()

        result = memory_context("testapp::EmptyClass")
        assert result["error"] is None
        assert result["direct"] == []

        cls.delete()


# ── Inherited memories ────────────────────────────────────────────────

class TestInherited:
    """Memories from parent nodes via COMPOSES upward traversal."""

    def test_inherited_from_namespace(self, hierarchy):
        """A class inherits its namespace's constraint."""
        result = memory_context("testapp::DatabaseLayer")
        assert result["error"] is None

        inherited = result["inherited"]
        assert len(inherited) >= 1

        # Find the namespace entry
        ns_entry = next((e for e in inherited if e["source"] == "testapp"), None)
        assert ns_entry is not None
        assert ns_entry["source_kind"] == "NamespaceNode"
        assert len(ns_entry["memories"]) >= 1

        # Should contain the app-level constraint
        constraint = next(
            (m for m in ns_entry["memories"] if m["type"] == "ConstraintNode"), None
        )
        assert constraint is not None
        assert "DAL" in constraint["content"]

    def test_inherited_depth_ordering(self, hierarchy):
        """Inherited entries are ordered nearest-first."""
        result = memory_context("testapp::DatabaseLayer")
        depths = [e["depth"] for e in result["inherited"]]
        assert depths == sorted(depths)  # ascending = nearest first

    def test_traverse_parents_false(self, hierarchy):
        """With traverse_parents=False, only direct memories are returned."""
        result = memory_context("testapp::DatabaseLayer", traverse_parents=False)
        assert result["inherited"] == []
        assert len(result["direct"]) == 2


# ── Summary ───────────────────────────────────────────────────────────

class TestSummary:
    """Summary statistics in the response."""

    def test_by_type_counts(self, hierarchy):
        result = memory_context("testapp::DatabaseLayer")
        summary = result["summary"]
        assert summary["total_memories"] >= 3  # 2 direct + 1 inherited
        assert summary["by_type"]["DecisionNode"] >= 1
        assert summary["by_type"]["ConstraintNode"] >= 1
        assert summary["by_type"]["AssumptionNode"] >= 1

    def test_low_confidence_flags(self, hierarchy):
        result = memory_context("testapp::DatabaseLayer")
        summary = result["summary"]
        # The pool-ready assumption has confidence 0.3
        assert "memory::pool-ready" in summary["low_confidence"]

    def test_superseded_decisions(self, hierarchy):
        """Superseded decisions are flagged in the summary."""
        # Create a decision that supersedes the original
        record_memory(
            type="decision",
            qualified_name="memory::dal-choice-v2",
            content="Use psycopg3 instead of asyncpg.",
            supersedes="memory::dal-choice",
            links_to="testapp::DatabaseLayer",
        )

        result = memory_context("testapp::DatabaseLayer")
        summary = result["summary"]
        assert "memory::dal-choice" in summary["superseded"]

        # Cleanup the v2 decision
        from codegraph_memory.models.decision import DecisionNode
        nodes = DecisionNode.nodes.filter(qualified_name="memory::dal-choice-v2")
        for n in nodes:
            n.delete()

    def test_include_superseded(self, hierarchy):
        """With include_superseded=True, superseded decisions are not flagged."""
        record_memory(
            type="decision",
            qualified_name="memory::dal-choice-v2",
            content="Use psycopg3 instead of asyncpg.",
            supersedes="memory::dal-choice",
            links_to="testapp::DatabaseLayer",
        )

        result = memory_context("testapp::DatabaseLayer", include_superseded=True)
        summary = result["summary"]
        assert "memory::dal-choice" not in summary["superseded"]

        from codegraph_memory.models.decision import DecisionNode
        nodes = DecisionNode.nodes.filter(qualified_name="memory::dal-choice-v2")
        for n in nodes:
            n.delete()


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    """Target not found, no memories, etc."""

    def test_target_not_found(self):
        result = memory_context("nonexistent::Target")
        assert result["error"] is not None
        assert "No code node found" in result["error"]
        assert result["target"]["kind"] is None
        assert result["direct"] == []
        assert result["inherited"] == []
        assert result["summary"]["total_memories"] == 0

    def test_no_memories_at_all(self):
        """Target exists but has no memories anywhere in the hierarchy."""
        ns = NamespaceNode(qualified_name="emptyapp", source="test")
        ns.save()
        cls = ClassNode(qualified_name="emptyapp::EmptyClass", source="test")
        cls.save()

        get_backend().graph.merge_relationship(ns.canonical_key, "COMPOSES", cls.canonical_key)

        result = memory_context("emptyapp::EmptyClass")
        assert result["error"] is None
        assert result["direct"] == []
        assert result["inherited"] == []  # namespace has no memories either
        assert result["summary"]["total_memories"] == 0

        cls.delete()
        ns.delete()
