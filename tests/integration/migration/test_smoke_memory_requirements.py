"""Smoke test for migrated pure-Python requirements + memory models.

These models no longer inherit ``StructuredNode``; all persistence goes
through the active backend (Neo4j).  This test exercises the full
CRUD + relationship lifecycle for HLR/LLR and memory node types.

NOTE: this is a temporary verification test for the decoupling migration.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def neo4j_connection(setup_neomodel):
    yield setup_neomodel


def _make_hlr(**kw):
    from codegraph_requirements.models.requirement import HLR

    data = dict(
        qualified_name="smoke.REQ-1",
        name="REQ-1",
        description="The system shall smoke test.",
        source="smoke",
        tags=["design"],
    )
    data.update(kw)
    return HLR(**data)


def test_hlr_save_and_query():
    from codegraph_requirements.models.requirement import HLR

    hlr = _make_hlr()
    hlr.save()
    assert hlr.canonical_key

    # Query via the .nodes shim
    found = HLR.nodes.get_or_none(canonical_key=hlr.canonical_key)
    assert found is not None
    assert found.qualified_name == "smoke.REQ-1"
    assert found.description == "The system shall smoke test."
    assert found.tags == ["design"]
    assert found.source == "smoke"
    assert found.element_id == hlr.element_id

    # get() raises DoesNotExist when missing
    with pytest.raises(HLR.DoesNotExist):
        HLR.nodes.get(canonical_key="nonexistent-uid-1234")

    # find_all via backend
    all_hlrs = HLR.nodes.all()
    assert len(all_hlrs) >= 1


def test_llr_relationship_lifecycle():
    from codegraph_requirements.models.requirement import HLR, LLR

    hlr = _make_hlr(qualified_name="smoke.REQ-2", name="REQ-2")
    hlr.save()
    llr = LLR(
        qualified_name="smoke.REQ-2.LLR-1",
        name="LLR-1",
        description="Verify smoke works.",
        source="smoke",
        tags=["design"],
    )
    # WP A: parent-relative — resolve the key from the owning HLR.
    llr.canonical_key = llr.resolve_canonical_key(
        parents={"parent_hlr_key": hlr.canonical_key}
    )
    llr.save()

    # Connect via the manager shim
    hlr.llrs.connect(llr)
    connected = hlr.llrs.all()
    assert any(c.canonical_key == llr.canonical_key for c in connected), "llrs.all() missing LLR"

    # Backend traversal agrees
    from codegraph.backends import get_backend

    children = get_backend().get_composed_children(hlr)
    assert any(c.canonical_key == llr.canonical_key for c in children)

    # Incoming traversal: llr.hlr
    parents = llr.hlr.all()
    assert any(p.canonical_key == hlr.canonical_key for p in parents)

    # Disconnect
    hlr.llrs.disconnect(llr)
    assert not any(c.canonical_key == llr.canonical_key for c in hlr.llrs.all())


def test_hlr_delete_cascades():
    from codegraph_requirements.models.requirement import HLR, LLR
    from codegraph.backends import get_backend

    hlr = _make_hlr(qualified_name="smoke.REQ-3", name="REQ-3")
    hlr.save()
    llr = LLR(
        qualified_name="smoke.REQ-3.LLR-1",
        description="child",
        source="smoke",
    )
    llr.canonical_key = llr.resolve_canonical_key(
        parents={"parent_hlr_key": hlr.canonical_key}
    )
    llr.save()
    hlr.llrs.connect(llr)

    llr_uid = llr.canonical_key
    hlr_uid = hlr.canonical_key
    hlr.delete()

    assert get_backend().graph.find_by_key(hlr_uid) is None
    assert get_backend().graph.find_by_key(llr_uid) is None


def test_decision_node_crud_and_edges():
    from codegraph_memory.models.decision import DecisionNode

    d = DecisionNode(
        qualified_name="memory::smoke-decision",
        content="We chose X over Y.",
        source="memory",
        tags=["design"],
        confidence=0.9,
    )
    d.save()
    assert d.canonical_key
    assert d.decided_at is not None, "decided_at should be set on save"
    assert d.updated_at is not None, "updated_at should be set on save"
    assert d.source == "memory"

    found = DecisionNode.nodes.get_or_none(canonical_key=d.canonical_key)
    assert found is not None
    assert found.content == "We chose X over Y."
    assert found.confidence == 0.9
    # Timestamps round-trip as datetime
    assert found.decided_at is not None

    # SUPERSEDES edge via backend memory repo
    d2 = DecisionNode(
        qualified_name="memory::smoke-decision-2",
        content="We now choose Z.",
        source="memory",
    )
    d2.save()
    from codegraph.backends import get_backend

    get_backend().memory.merge_edge(
        d2.canonical_key, "SUPERSEDES", d.canonical_key,
        source_label="DecisionNode", target_label="DecisionNode",
    )
    superseded = d2.supersedes.all()
    assert any(s.canonical_key == d.canonical_key for s in superseded)


def test_record_memory_tool_end_to_end():
    from codegraph_memory.tools.record import record_memory

    result = record_memory(
        type="decision",
        qualified_name="memory::smoke-recorded",
        content="This decision was recorded through the tool.",
        source="smoke",
    )
    assert result["action"] in ("created", "updated")
    assert result["canonical_key"]
    assert result["error"] is None

    # Update path
    result2 = record_memory(
        type="decision",
        qualified_name="memory::smoke-recorded",
        content="Updated decision content.",
        source="smoke",
        confidence=0.5,
        mode="upsert",
    )
    assert result2["action"] == "updated"
    assert result2["content"] == "Updated decision content."
    assert result2["confidence"] == 0.5
