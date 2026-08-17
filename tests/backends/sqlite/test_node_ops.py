"""Node CRUD + relationship tests for the SQLite backend.

Run:  CODEGRAPH_BACKEND=sqlite python -m pytest tests/backends/sqlite/ -q
"""

from __future__ import annotations

from datetime import UTC

import pytest

from codegraph.backends import get_backend
from codegraph.models.compound import ClassNode, InterfaceNode
from codegraph.models.member import MethodNode
from codegraph.models.namespace import NamespaceNode

# ── Node CRUD ────────────────────────────────────────────────────────────


def test_save_get_roundtrip():
    b = get_backend()
    cls = ClassNode(
        name="Calculator", source="demo", qualified_name="calc::Calculator",
        kind="class", tags=["design"], brief_description="A calculator",
    )
    saved = cls.save()
    assert saved.canonical_key
    assert saved.element_id is not None

    got = b.get(ClassNode, qualified_name="calc::Calculator")
    assert got is not None
    assert got.name == "Calculator"
    assert got.brief_description == "A calculator"
    assert got.tags == ["design"]
    assert got.element_id == cls.element_id


def test_save_is_idempotent_upsert():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class")
    cls.save()
    n1 = b.graph.count_all_nodes()
    cls.brief_description = "updated"
    cls.save()
    assert b.graph.count_all_nodes() == n1
    got = b.get(ClassNode, qualified_name="demo::C")
    assert got.brief_description == "updated"


def test_save_requires_canonical_identity():
    """Canonical identity is mandatory (WP A): a node without a scope
    raises IdentityError at save."""
    from codegraph.identity import IdentityError, set_identity_scope

    set_identity_scope(None)
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C",
                    kind="class")
    with pytest.raises(IdentityError):
        cls.save()


def test_find_all_and_filters():
    b = get_backend()
    for i in range(3):
        ClassNode(
            name=f"C{i}", source="demo", qualified_name=f"demo::C{i}",
            kind="class", tags=["design"] if i % 2 == 0 else ["as-built"],
        ).save()
    assert len(b.find_all(ClassNode)) == 3
    assert len(b.find_all(ClassNode, kind="class")) == 3
    assert len(b.find_all(ClassNode, name="C1")) == 1
    # Node types are distinguished by label
    InterfaceNode(name="I", source="demo", qualified_name="demo::I", kind="interface").save()
    assert len(b.find_all(ClassNode)) == 3


def test_inflate_by_uid_string():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    node = b.inflate(cls.canonical_key, ClassNode)
    assert isinstance(node, ClassNode)
    assert node.element_id == cls.element_id


def test_labels_and_inherited_labels():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    assert b.graph.get_labels(cls.canonical_key) == {"ClassNode", "CompoundNode"}
    # Label mutation
    b.graph.set_labels(cls.canonical_key, ["CustomNode"])
    assert b.graph.get_labels(cls.canonical_key) == {"CustomNode"}
    b.graph.remove_labels(cls.canonical_key, ["CustomNode"])
    assert b.graph.get_labels(cls.canonical_key) == set()


def test_update_properties():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    assert b.graph.update_properties(cls.canonical_key, {"brief_description": "hello"}) is True
    got = b.graph.find_by_key(cls.canonical_key)
    assert got.brief_description == "hello"
    assert b.graph.update_properties("nope", {"x": 1}) is False


def test_datetime_roundtrip():
    from datetime import datetime

    from codegraph_memory.models.decision import DecisionNode

    b = get_backend()
    ts = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    d = DecisionNode(
        name="d", source="memory", qualified_name="memory::d", content="x",
        decided_at=ts,
    ).save()
    got = b.graph.find_by_key(d.canonical_key)
    assert got.decided_at is not None
    assert got.decided_at.timestamp() == pytest.approx(ts.timestamp())


# ── Tag / source / kind queries ──────────────────────────────────────────


def test_tag_queries():
    b = get_backend()
    c1 = ClassNode(name="C1", source="demo", qualified_name="demo::C1", kind="class", tags=["design"]).save()
    m1 = MethodNode(name="m", source="demo", qualified_name="demo::C1::m", kind="method", tags=["as-built"]).save()
    assert set(b.graph.find_uids_by_tag("design")) == {c1.canonical_key}
    assert set(b.graph.find_uids_by_tag("as-built")) == {m1.canonical_key}
    assert [n.qualified_name for n in b.graph.find_all_by_tag("design")] == [c1.qualified_name]
    assert len(b.graph.find_by_tag(ClassNode, "design")) == 1
    assert b.graph.find_by_tag(MethodNode, "design") == []
    assert [n.qualified_name for n in b.graph.find_all_by_source("demo")] != []


def test_kind_queries():
    b = get_backend()
    ClassNode(name="C1", source="demo", qualified_name="demo::C1", kind="class", tags=["design"]).save()
    ClassNode(name="C2", source="demo", qualified_name="demo::C2", kind="class", tags=["as-built"]).save()
    InterfaceNode(name="I", source="demo", qualified_name="demo::I", kind="interface", tags=["design"]).save()
    assert len(b.graph.find_all_by_kind("class")) == 2
    assert len(b.graph.find_all_by_kind("class", tag="design")) == 1
    assert len(b.graph.find_all_by_kind("interface")) == 1


def test_uid_resolution():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    assert b.graph.resolve_uid("demo::C") == cls.canonical_key
    assert b.graph.resolve_uid("nonexistent") is None
    assert b.graph.resolve_uid_by_name("C", label="ClassNode") == cls.canonical_key
    assert b.graph.resolve_qualified_name(cls.canonical_key) == "demo::C"
    assert b.graph.find_by_qualified_name("demo::C").element_id == cls.element_id
    assert b.graph.find_all_by_qualified_name("demo::C") != []


# ── Relationships + traversal ────────────────────────────────────────────


def _make_tree(b):
    ns = NamespaceNode(name="calc", source="demo", qualified_name="calc", kind="namespace").save()
    cls = ClassNode(name="Calculator", source="demo", qualified_name="calc::Calculator", kind="class").save()
    m = MethodNode(name="add", source="demo", qualified_name="calc::Calculator::add", kind="method").save()
    b.connect(ns, "COMPOSES", cls)
    b.connect(cls, "COMPOSES", m)
    return ns, cls, m


def test_connect_disconnect_and_edges():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    edges = b.get_all_edges(cls)
    assert {e.relation_type for e in edges} == {"COMPOSES"}
    outgoing = b.get_all_edges_outgoing(cls)
    assert len(outgoing) == 1 and outgoing[0].target_key == m.canonical_key
    incoming = [e for e in edges if not e.is_outgoing]
    assert incoming[0].target_key == ns.canonical_key
    assert incoming[0].target_type == "NamespaceNode"

    b.disconnect(cls, "COMPOSES", m)
    assert b.get_all_edges_outgoing(cls) == []


def test_connect_requires_saved_nodes():
    b = get_backend()
    a = ClassNode(name="A", source="demo", qualified_name="demo::A", kind="class")
    z = ClassNode(name="Z", source="demo", qualified_name="demo::Z", kind="class").save()
    with pytest.raises(ValueError):
        b.connect(a, "COMPOSES", z)


def test_merge_relationship_idempotent():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    assert b.graph.merge_relationship(cls.canonical_key, "COMPOSES", m.canonical_key) == 1
    assert b.graph.merge_relationship(cls.canonical_key, "COMPOSES", m.canonical_key) == 1  # no dup
    assert b.graph.count_relationships(["COMPOSES"]) == 2
    assert b.graph.merge_relationship("nope", "COMPOSES", m.canonical_key) == 0


def test_composed_children_and_traversal():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    assert [c.qualified_name for c in b.get_composed_children(ns)] == ["calc::Calculator"]
    assert [c.qualified_name for c in b.graph.composed_children(cls, MethodNode)] == ["calc::Calculator::add"]
    assert [c.qualified_name for c in b.graph.incoming_composers(cls)] == ["calc"]
    assert [c.qualified_name for c in b.graph.outgoing_by_relation(cls, "COMPOSES")] == ["calc::Calculator::add"]

    ancestors = b.graph.get_ancestors(m.canonical_key)
    assert {a["uid"] for a in ancestors} == {ns.canonical_key, cls.canonical_key}
    descendants = b.graph.get_descendants(ns.canonical_key)
    assert {d["uid"] for d in descendants} == {cls.canonical_key, m.canonical_key}
    # Ancestor labels are the inherited label chains
    cls_labels = [a["labels"] for a in ancestors if a["uid"] == cls.canonical_key][0]
    assert set(cls_labels) == {"ClassNode", "CompoundNode"}


def test_delete_cascades():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    b.delete(ns)
    assert b.graph.count_all_nodes() == 0
    assert b.graph.count_relationships(["COMPOSES"]) == 0
    assert b.graph.find_by_key(cls.canonical_key) is None
    assert b.graph.find_by_key(m.canonical_key) is None


def test_delete_by_uid_detaches():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    assert b.graph.delete_by_uid(cls.canonical_key) is True
    assert b.graph.delete_by_uid("nope") is False
    # ns/m survive; the edge between ns and cls is gone
    assert b.graph.count_relationships(["COMPOSES"]) == 0
    assert b.graph.count_all_nodes() == 2


def test_count_all_nodes_with_tag():
    b = get_backend()
    ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class", tags=["design"]).save()
    assert b.graph.count_all_nodes() == 1
    assert b.graph.count_all_nodes(tag="design") == 1
    assert b.graph.count_all_nodes(tag="as-built") == 0


def test_get_all_node_labels_and_find_with_labels():
    b = get_backend()
    ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    all_labels = b.graph.get_all_node_labels()
    assert len(all_labels) == 1
    assert set(all_labels[0]["labels"]) == {"ClassNode", "CompoundNode"}
    found = b.graph.find_nodes_with_labels(["ClassNode", "CompoundNode"])
    assert len(found) == 1
    assert b.graph.find_nodes_with_labels(["MemberNode"]) == []


def test_count_relationships_with_filters():
    b = get_backend()
    ns, cls, m = _make_tree(b)
    # target_tag filter on the method
    assert b.graph.count_relationships(["COMPOSES"]) == 2
    assert b.graph.count_relationships(["COMPOSES"], source_labels=["NamespaceNode"]) == 1
    assert b.graph.count_relationships(["COMPOSES"], target_labels=["MethodNode"]) == 1


def test_update_tags_via_save():
    b = get_backend()
    cls = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class", tags=["scaffold"]).save()
    assert b.graph.find_uids_by_tag("scaffold") == [cls.canonical_key]
    cls.tags = ["design"]
    cls.save()
    assert b.graph.find_uids_by_tag("scaffold") == []
    assert b.graph.find_uids_by_tag("design") == [cls.canonical_key]
