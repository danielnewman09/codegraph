"""Tests for record_memory — the primary write-side tool for agents."""

from __future__ import annotations

import pytest

from codegraph.models.compound import ClassNode
from codegraph_memory.tools.record import record_memory


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def code_node():
    """Create a test ClassNode to link memories to."""
    node = ClassNode(
        qualified_name="test::RecordTarget",
        source="test",
    )
    node.save()
    yield node
    # Cleanup is handled by the parent conftest's clear_db fixture


# ── Create ────────────────────────────────────────────────────────────

class TestCreate:
    """Creating new memory nodes."""

    def test_create_decision(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-create-decision",
            content="We chose X over Y because of Z.",
            tags=["design"],
            confidence=0.9,
            source="testapp",
        )
        assert result["action"] == "created"
        assert result["type"] == "DecisionNode"
        assert result["qualified_name"] == "memory::test-create-decision"
        assert result["uid"] is not None
        assert result["content"] == "We chose X over Y because of Z."
        assert result["tags"] == ["design"]
        assert result["confidence"] == 0.9
        assert result["error"] is None
        assert result["matches"] is None

        # Cleanup
        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=result["uid"]).delete()

    def test_create_constraint(self):
        result = record_memory(
            type="constraint",
            qualified_name="memory::test-create-constraint",
            content="Must respond within 100ms.",
            tags=["design"],
        )
        assert result["action"] == "created"
        assert result["type"] == "ConstraintNode"
        assert result["confidence"] == 1.0  # default

        from codegraph_memory.models.constraint import ConstraintNode
        ConstraintNode.nodes.get(uid=result["uid"]).delete()

    def test_create_rationale(self):
        result = record_memory(
            type="rationale",
            qualified_name="memory::test-create-rationale",
            content="This exists because the legacy API requires it.",
        )
        assert result["action"] == "created"
        assert result["type"] == "RationaleNode"

        from codegraph_memory.models.rationale import RationaleNode
        RationaleNode.nodes.get(uid=result["uid"]).delete()

    def test_create_assumption(self):
        result = record_memory(
            type="assumption",
            qualified_name="memory::test-create-assumption",
            content="We assume the network is reliable.",
            confidence=0.5,
        )
        assert result["action"] == "created"
        assert result["type"] == "AssumptionNode"
        assert result["confidence"] == 0.5

        from codegraph_memory.models.assumption import AssumptionNode
        AssumptionNode.nodes.get(uid=result["uid"]).delete()

    def test_create_tradeoff(self):
        result = record_memory(
            type="tradeoff",
            qualified_name="memory::test-create-tradeoff",
            content="We sacrificed memory for speed.",
        )
        assert result["action"] == "created"
        assert result["type"] == "TradeoffNode"

        from codegraph_memory.models.tradeoff import TradeoffNode
        TradeoffNode.nodes.get(uid=result["uid"]).delete()

    def test_create_insight(self):
        result = record_memory(
            type="insight",
            qualified_name="memory::test-create-insight",
            content="After 6 months, we learned that caching is essential.",
        )
        assert result["action"] == "created"
        assert result["type"] == "InsightNode"

        from codegraph_memory.models.insight import InsightNode
        InsightNode.nodes.get(uid=result["uid"]).delete()


# ── Update (upsert) ───────────────────────────────────────────────────

class TestUpsert:
    """Upsert: find by qualified_name, update if exists, create if not."""

    def test_upsert_creates_when_not_found(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-upsert-new",
            content="Initial content.",
            mode="upsert",
        )
        assert result["action"] == "created"

        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=result["uid"]).delete()

    def test_upsert_updates_when_found(self):
        # Create first
        r1 = record_memory(
            type="decision",
            qualified_name="memory::test-upsert-existing",
            content="Original content.",
            tags=["design"],
            confidence=0.7,
        )
        uid = r1["uid"]
        assert r1["action"] == "created"

        # Upsert with new content
        r2 = record_memory(
            type="decision",
            qualified_name="memory::test-upsert-existing",
            content="Updated content.",
            tags=["as-built"],
            confidence=0.95,
            mode="upsert",
        )
        assert r2["action"] == "updated"
        assert r2["uid"] == uid  # same node, stable UID
        assert r2["content"] == "Updated content."
        assert r2["tags"] == ["as-built"]
        assert r2["confidence"] == 0.95

        # Cleanup
        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=uid).delete()

    def test_upsert_preserves_unchanged_fields(self):
        # Create with tags
        r1 = record_memory(
            type="decision",
            qualified_name="memory::test-upsert-partial",
            content="Original.",
            tags=["design"],
            confidence=0.8,
        )
        uid = r1["uid"]

        # Upsert without tags — tags should be preserved
        r2 = record_memory(
            type="decision",
            qualified_name="memory::test-upsert-partial",
            content="Updated.",
            mode="upsert",
        )
        assert r2["action"] == "updated"
        assert r2["tags"] == ["design"]  # preserved
        assert r2["confidence"] == 0.8  # preserved

        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=uid).delete()


# ── Mode constraints ──────────────────────────────────────────────────

class TestModeConstraints:
    """create/update mode validation."""

    def test_create_fails_if_exists(self):
        r1 = record_memory(
            type="decision",
            qualified_name="memory::test-create-exists",
            content="First.",
        )
        uid = r1["uid"]

        r2 = record_memory(
            type="decision",
            qualified_name="memory::test-create-exists",
            content="Second.",
            mode="create",
        )
        assert r2["action"] == "error"
        assert "already exists" in r2["error"]

        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=uid).delete()

    def test_update_fails_if_not_found(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-update-missing",
            content="Content.",
            mode="update",
        )
        assert result["action"] == "error"
        assert "No DecisionNode found" in result["error"]


# ── Disambiguation ─────────────────────────────────────────────────────

class TestDisambiguation:
    """When multiple nodes share a qualified_name."""

    def test_same_qualified_name_updates_in_place(self):
        """Saving a second node with the same qualified_name updates the first.

        Since UID is derived from qualified_name only, two nodes with the same
        qualified_name have the same UID.  CodeGraphNode._save uses MERGE on uid,
        so the second save updates the existing node rather than creating a duplicate.
        This is the intended behavior — one memory per qualified_name.
        """
        from codegraph_memory.models.decision import DecisionNode

        d1 = DecisionNode(
            qualified_name="memory::test-uid-unique",
            content="First version.",
            source="test",
        )
        d1.save()
        eid1 = d1.element_id

        # Second save with same qualified_name updates the first node
        d2 = DecisionNode(
            qualified_name="memory::test-uid-unique",
            content="Second version.",
            source="test",
        )
        d2.save()

        # Same element_id (same node), content updated
        assert d2.element_id == eid1
        assert d2.content == "Second version."

        d1.delete()

    def test_ambiguous_when_uids_differ(self):
        """Disambiguation when nodes share qualified_name but have different uids.

        This can happen if someone creates nodes via raw Cypher, bypassing
        the uid computation.  The tool should detect the ambiguity and return
        matches for the agent to disambiguate.
        """
        from codegraph_memory.models.decision import DecisionNode
        from neomodel import db
        from codegraph.backends import get_backend

        # Create first node normally
        d1 = DecisionNode(
            qualified_name="memory::test-ambiguous-raw",
            content="First version.",
            source="test",
        )
        d1.save()

        # Create second node via raw Cypher with a different uid.
        # Using neomodel's save() would recompute the uid, so raw
        # Cypher is the only way to create a node that bypasses the
        # normal uid computation — this test exists to verify the
        # system handles such externally-created nodes.
        db.cypher_query(
            "CREATE (n:DecisionNode:MemoryNode) SET n.uid = 'manual-uid-99999', "
            "n.qualified_name = 'memory::test-ambiguous-raw', "
            "n.content = 'Second version.', n.source = 'test', n.tags = [], "
            "n.confidence = 1.0, n.name = ''"
        )

        result = record_memory(
            type="decision",
            qualified_name="memory::test-ambiguous-raw",
            content="New content.",
        )
        assert result["action"] == "ambiguous"
        assert result["matches"] is not None
        assert len(result["matches"]) == 2

        # Cleanup
        d1.delete()
        get_backend().graph.delete_by_uid("manual-uid-99999")

    def test_uid_disambiguates(self):
        from codegraph_memory.models.decision import DecisionNode

        d1 = DecisionNode(
            qualified_name="memory::test-uid-ambiguous",
            content="First.",
            source="test",
        )
        d1.save()
        d2 = DecisionNode(
            qualified_name="memory::test-uid-ambiguous",
            content="Second.",
            source="test",
        )
        d2.save()

        # Target by uid
        result = record_memory(
            type="decision",
            qualified_name="memory::test-uid-ambiguous",
            content="Updated via uid.",
            uid=d1.uid,
        )
        assert result["action"] == "updated"
        assert result["uid"] == d1.uid
        assert result["content"] == "Updated via uid."

        d1.delete()
        d2.delete()


# ── Links to code ──────────────────────────────────────────────────────

class TestLinksTo:
    """Linking memory to code nodes."""

    def test_links_to_single_code_node(self, code_node):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-links-single",
            content="Decision about RecordTarget.",
            links_to="test::RecordTarget",
        )
        assert result["action"] == "created"
        assert result["linked_code"] == ["test::RecordTarget"]

        # Verify the edge exists
        from codegraph_memory.models.decision import DecisionNode
        node = DecisionNode.nodes.get(uid=result["uid"])
        from codegraph_memory.models.relationships import get_linked_code_nodes
        linked = get_linked_code_nodes(node, "MOTIVATES")
        assert len(linked) == 1
        assert linked[0].qualified_name == "test::RecordTarget"

        node.delete()

    def test_links_to_multiple_code_nodes(self, code_node):
        # Create a second code node
        c2 = ClassNode(qualified_name="test::RecordTarget2", source="test")
        c2.save()

        result = record_memory(
            type="constraint",
            qualified_name="memory::test-links-multi",
            content="Constraint on both targets.",
            links_to=["test::RecordTarget", "test::RecordTarget2"],
        )
        assert result["action"] == "created"
        assert set(result["linked_code"]) == {"test::RecordTarget", "test::RecordTarget2"}

        from codegraph_memory.models.constraint import ConstraintNode
        node = ConstraintNode.nodes.get(uid=result["uid"])
        from codegraph_memory.models.relationships import get_linked_code_nodes
        linked = get_linked_code_nodes(node, "CONSTRAINS")
        assert len(linked) == 2

        node.delete()
        c2.delete()

    def test_links_to_nonexistent_code_node(self, code_node):
        """Linking to a code node that doesn't exist is silently skipped."""
        result = record_memory(
            type="decision",
            qualified_name="memory::test-links-missing",
            content="Decision with missing link.",
            links_to="test::Nonexistent",
        )
        assert result["action"] == "created"
        assert result["linked_code"] == []  # skipped

        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=result["uid"]).delete()

    def test_links_to_is_additive_on_update(self, code_node):
        # Create with one link
        r1 = record_memory(
            type="decision",
            qualified_name="memory::test-links-additive",
            content="Decision.",
            links_to="test::RecordTarget",
        )
        uid = r1["uid"]

        # Create second code node
        c2 = ClassNode(qualified_name="test::RecordTarget3", source="test")
        c2.save()

        # Update with a new link
        r2 = record_memory(
            type="decision",
            qualified_name="memory::test-links-additive",
            content="Updated decision.",
            links_to="test::RecordTarget3",
        )
        assert r2["action"] == "updated"
        assert set(r2["linked_code"]) == {"test::RecordTarget3"}

        # Both links should exist
        from codegraph_memory.models.decision import DecisionNode
        node = DecisionNode.nodes.get(uid=uid)
        from codegraph_memory.models.relationships import get_linked_code_nodes
        linked = get_linked_code_nodes(node, "MOTIVATES")
        assert len(linked) == 2

        node.delete()
        c2.delete()


# ── Memory-to-memory edges ────────────────────────────────────────────

class TestSupersedes:
    """SUPERSEDES: new decision replaces old."""

    def test_supersedes_creates_new_and_links(self):
        # Create old decision
        old = record_memory(
            type="decision",
            qualified_name="memory::test-supersede-old",
            content="Old approach: use psycopg2.",
        )
        old_uid = old["uid"]

        # Create new decision that supersedes
        new = record_memory(
            type="decision",
            qualified_name="memory::test-supersede-new",
            content="New approach: use asyncpg.",
            supersedes="memory::test-supersede-old",
        )
        assert new["action"] == "created"
        assert new["uid"] != old_uid  # different node

        # Verify SUPERSEDES edge
        from codegraph_memory.models.decision import DecisionNode
        new_node = DecisionNode.nodes.get(uid=new["uid"])
        old_node = DecisionNode.nodes.get(uid=old_uid)

        assert old_node in new_node.supersedes.all()

        new_node.delete()
        old_node.delete()

    def test_supersedes_implies_create(self):
        """supersedes forces mode='create' — always a new node.

        The new decision gets a different qualified_name from the old one
        (e.g., 'memory::db-choice-v2' supersedes 'memory::db-choice-v1').
        Using the same qualified_name would produce the same UID and update
        in place, which defeats the purpose of supersession.
        """
        old = record_memory(
            type="decision",
            qualified_name="memory::test-supersede-force-old",
            content="Old approach.",
        )
        old_uid = old["uid"]

        # New decision with a different qualified_name supersedes the old
        new = record_memory(
            type="decision",
            qualified_name="memory::test-supersede-force-new",
            content="New approach superseding old.",
            supersedes="memory::test-supersede-force-old",
            mode="upsert",
        )
        # Should be created (not updated) because supersedes implies create
        assert new["action"] == "created"
        assert new["uid"] != old_uid  # different node

        from codegraph_memory.models.decision import DecisionNode
        new_node = DecisionNode.nodes.get(uid=new["uid"])
        old_node = DecisionNode.nodes.get(uid=old_uid)
        new_node.delete()
        old_node.delete()

    def test_supersedes_only_valid_for_decision(self):
        result = record_memory(
            type="constraint",
            qualified_name="memory::test-supersede-bad",
            content="Constraint with supersedes.",
            supersedes="memory::some-decision",
        )
        assert result["action"] == "error"
        assert "supersedes is only valid for type='decision'" in result["error"]


class TestRefines:
    """REFINES: rationale elaborates a decision."""

    def test_refines_links_rationale_to_decision(self):
        # Create decision first
        dec = record_memory(
            type="decision",
            qualified_name="memory::test-refines-decision",
            content="We chose async processing.",
        )
        dec_uid = dec["uid"]

        # Create rationale that refines it
        rat = record_memory(
            type="rationale",
            qualified_name="memory::test-refines-rationale",
            content="Async processing avoids blocking the main thread.",
            refines="memory::test-refines-decision",
        )
        assert rat["action"] == "created"

        # Verify REFINES edge
        from codegraph_memory.models.rationale import RationaleNode
        from codegraph_memory.models.decision import DecisionNode

        rat_node = RationaleNode.nodes.get(uid=rat["uid"])
        dec_node = DecisionNode.nodes.get(uid=dec_uid)

        assert dec_node in rat_node.refines.all()

        rat_node.delete()
        dec_node.delete()

    def test_refines_only_valid_for_rationale(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-refines-bad",
            content="Decision with refines.",
            refines="memory::some-decision",
        )
        assert result["action"] == "error"
        assert "refines is only valid for type='rationale'" in result["error"]


class TestContradicts:
    """CONTRADICTS: assumption flags tension with another."""

    def test_contradicts_links_assumptions(self):
        # Create first assumption
        a1 = record_memory(
            type="assumption",
            qualified_name="memory::test-contradicts-a1",
            content="The network is reliable.",
        )
        a1_uid = a1["uid"]

        # Create second assumption that contradicts the first
        a2 = record_memory(
            type="assumption",
            qualified_name="memory::test-contradicts-a2",
            content="The network is unreliable in production.",
            contradicts="memory::test-contradicts-a1",
        )
        assert a2["action"] == "created"

        # Verify CONTRADICTS edge
        from codegraph_memory.models.assumption import AssumptionNode

        a2_node = AssumptionNode.nodes.get(uid=a2["uid"])
        a1_node = AssumptionNode.nodes.get(uid=a1_uid)

        assert a1_node in a2_node.contradicts.all()

        a2_node.delete()
        a1_node.delete()

    def test_contradicts_only_valid_for_assumption(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-contradicts-bad",
            content="Decision with contradicts.",
            contradicts="memory::some-assumption",
        )
        assert result["action"] == "error"
        assert "contradicts is only valid for type='assumption'" in result["error"]


# ── Error handling ─────────────────────────────────────────────────────

class TestErrors:
    """Invalid inputs."""

    def test_unknown_type(self):
        result = record_memory(
            type="unknown",  # type: ignore
            qualified_name="memory::test-bad-type",
            content="Content.",
        )
        assert result["action"] == "error"
        assert "Unknown memory type" in result["error"]

    def test_uid_not_found(self):
        result = record_memory(
            type="decision",
            qualified_name="memory::test-uid-missing",
            content="Content.",
            uid="nonexistent-uid-12345",
        )
        assert result["action"] == "created"  # falls through to create
        assert result["uid"] != "nonexistent-uid-12345"

        from codegraph_memory.models.decision import DecisionNode
        DecisionNode.nodes.get(uid=result["uid"]).delete()
