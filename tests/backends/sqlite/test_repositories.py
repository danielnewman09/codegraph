"""Repository + search + LayerGraph tests for the SQLite backend.

Run:  CODEGRAPH_BACKEND=sqlite python -m pytest tests/backends/sqlite/ -q
"""

from __future__ import annotations

from codegraph.backends import get_backend
from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.compound import ClassNode
from codegraph.models.member import MethodNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.test import TestNode, TestStepNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_requirements.models.requirement import HLR, LLR

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_tree(b):
    ns = NamespaceNode(name="calc", source="demo", qualified_name="calc", kind="namespace", tags=["design"]).save()
    cls = ClassNode(name="Calculator", source="demo", qualified_name="calc::Calculator", kind="class", tags=["design"]).save()
    m = MethodNode(name="add", source="demo", qualified_name="calc::Calculator::add", kind="method", tags=["design"]).save()
    b.connect(ns, "COMPOSES", cls)
    b.connect(cls, "COMPOSES", m)
    return ns, cls, m


# TODO understand why this is necessary
def _save_keyed(node, scope, parents=None):
    """Compute the canonical key (with parent context when needed) and
    save under *scope* — canonical identity is mandatory (WP A)."""
    from codegraph.identity import resolve_identity_for

    node.canonical_key = resolve_identity_for(
        node, scope, parents=parents
    ).key()
    return node.save()

# TODO understand why this is necessary
def _keyed_standalone(node, scope):
    """Key a parent-relative node with a synthetic parent key (tests that
    only need a stable identity)."""
    from codegraph.identity import resolve_identity_for

    node.canonical_key = resolve_identity_for(
        node, scope,
        parents={"parent_key": "cg:v1:project:codegraph-suite:"
                                "requirement-hlr:qualified_name=test-hlr"},
    ).key()
    return node.save()


def _make_hlr_tree(b):
    from codegraph.identity import IdentityScope, identity_scope

    scope = IdentityScope.project("codegraph-suite")
    with identity_scope(scope):
        hlr = _save_keyed(HLR(
            name="HLR-1", source="req", qualified_name="AG-HLR-01",
            tags=["requirements", "design"], description="System must compute",
        ), scope)
        llr = _save_keyed(LLR(
            name="LLR-1", source="req", qualified_name="AG-LLR-01",
            tags=["requirements", "design"], description="Add must be int",
        ), scope, parents={"parent_hlr_key": hlr.canonical_key})
        test = _save_keyed(TestNode(
            name="test_add", source="req", qualified_name="AG-LLR-01::test_add",
            test_name="test_add", tags=["design"], description="add returns sum",
        ), scope, parents={"parent_key": llr.canonical_key})
        step = _save_keyed(TestStepNode(
            name="s1", source="req", qualified_name="AG-LLR-01::test_add::s1",
            order=1, tags=["design"],
        ), scope, parents={"parent_key": test.canonical_key})
        b.connect(hlr, "COMPOSES", llr)
        b.connect(llr, "COMPOSES", test)
        b.connect(test, "COMPOSES", step)
    return hlr, llr, test, step


# ── LayerGraph round-trip ────────────────────────────────────────────────


def test_list_sources_counts_by_source_desc():
    """list_sources returns distinct sources with node counts, desc."""
    b = get_backend()
    assert b.graph.list_sources() == []

    # Two sources, multiple nodes each
    ClassNode(name="A", source="alpha", qualified_name="a.A", kind="class").save()
    ClassNode(name="B", source="alpha", qualified_name="a.B", kind="class").save()
    NamespaceNode(name="ns", source="beta", qualified_name="ns", kind="namespace").save()

    assert b.graph.list_sources() == [
        {"source": "alpha", "count": 2},
        {"source": "beta", "count": 1},
    ]


def test_list_sources_counts_all_kinds():
    """All node kinds with a source are counted (incl. requirement nodes)."""
    b = get_backend()
    _make_tree(b)  # 3 nodes, source="demo"
    _make_hlr_tree(b)  # 4 nodes, source="req"
    assert b.graph.list_sources() == [
        {"source": "req", "count": 4},
        {"source": "demo", "count": 3},
    ]


def test_layer_graph_roundtrip():
    b = get_backend()
    # Canonical identity is mandatory: save first so nodes carry keys.
    ns = NamespaceNode(name="calc", source="demo", qualified_name="calc",
                       kind="namespace", tags=["design"]).save()
    cls = ClassNode(name="Calculator", source="demo",
                    qualified_name="calc::Calculator", kind="class",
                    tags=["design"]).save()
    m = MethodNode(name="add", source="demo",
                   qualified_name="calc::Calculator::add", kind="method",
                   tags=["design"]).save()
    m_entry = CompositeEntry(node=m)
    cls_entry = CompositeEntry(node=cls, children={"MethodNode": {LayerGraph._node_key(m): m_entry}})
    ns_entry = CompositeEntry(node=ns, children={"ClassNode": {LayerGraph._node_key(cls): cls_entry}})
    graph = LayerGraph(tags=frozenset({"design"}), entries={LayerGraph._node_key(ns): ns_entry})

    graph.to_backend(b)
    assert b.graph.count_all_nodes() == 3
    assert b.graph.count_relationships(["COMPOSES"]) == 2
    # element ids stamped on the source instances
    assert ns.element_id is not None and cls.element_id is not None and m.element_id is not None

    loaded = LayerGraph.from_backend(b, "design")
    root = next(iter(loaded.entries.values()))
    assert root.node.qualified_name == "calc"
    class_entries = root.children["ClassNode"]
    assert len(class_entries) == 1
    inner = next(iter(class_entries.values()))
    assert inner.node.qualified_name == "calc::Calculator"
    assert list(inner.children.keys()) == ["MethodNode"]


def test_bulk_save_incremental_preserves_labels_and_tags():
    """Incremental bulk_save must not wipe earlier batches' label/tag rows.

    Regression: ``bulk_save`` used to ``DELETE FROM node_labels`` and
    ``node_tags`` then re-insert only the current batch, so a second
    ingest (e.g. the API contract as scaffold after the requirements)
    erased the first batch's mirror rows — nodes stopped resolving by
    label or tag even though their rows were intact.
    """
    b = get_backend()

    # Batch 1: an HLR carrying the HLR label + design tag.
    from codegraph.identity import IdentityScope, resolve_identity_for

    scope = IdentityScope.project("codegraph-suite")
    hlr = HLR(
        name="Database Migration Manager", source="markdown-import",
        kind="hlr", tags=["design"],
        qualified_name="Database Migration Manager",
    )
    hlr.canonical_key = resolve_identity_for(hlr, scope).key()
    g1 = LayerGraph(
        tags=frozenset({"design"}),
        entries={hlr.canonical_key: CompositeEntry(node=hlr)},
    )
    g1.to_backend(b)

    # Batch 2: disjoint scaffold node — must not disturb batch 1.
    cls = ClassNode(
        name="Migration", source="scaffold",
        qualified_name="Migration", kind="class", tags=["scaffold"],
    )
    cls.canonical_key = resolve_identity_for(cls, scope).key()
    g2 = LayerGraph(
        tags=frozenset({"scaffold"}),
        entries={cls.canonical_key: CompositeEntry(node=cls)},
    )
    g2.to_backend(b)

    # Batch 1's HLR still resolves by label and by tag.
    assert len(list(HLR.nodes.all())) == 1
    loaded = LayerGraph.from_backend(b, "design")
    assert [e.node.name for e in loaded.entries.values()] == [
        "Database Migration Manager",
    ]


def test_get_by_tag_and_source():
    b = get_backend()
    _make_tree(b)
    g_tag = b.graph.get_by_tag("design")
    assert g_tag.count_entries() >= 1 if hasattr(g_tag, "count_entries") else True
    g_src = b.graph.get_by_source("demo")
    assert len(g_src.entries) >= 1


def test_get_by_compound_and_neighbourhood():
    b = get_backend()
    _, cls, _ = _make_tree(b)
    g = b.graph.get_by_compound(cls.qualified_name)
    # 1-hop neighbours include the namespace parent, which becomes the
    # root entry (identical to the Neo4j _build_layer_graph semantics).
    def _collect(entry):
        yield entry
        for ch in entry.children.values():
            for e in ch.values():
                yield from _collect(e)

    qnames = {e.node.qualified_name for e in _collect(next(iter(g.entries.values())))}
    assert "calc::Calculator" in qnames
    assert b.graph.get_by_compound("does.not.exist").tags == frozenset({"design"})
    g2 = b.graph.get_by_neighbourhood(cls.qualified_name)
    assert len(g2.entries) >= 1


def test_get_by_kind_and_namespace():
    b = get_backend()
    ns, _, _ = _make_tree(b)
    g = b.graph.get_by_kind("method")
    assert len(g.entries) >= 1
    g_ns = b.graph.get_by_namespace("calc")
    assert len(g_ns.entries) >= 1
    assert b.graph.get_by_namespace("nope").tags == frozenset({"design"})


# ── Memory repository ────────────────────────────────────────────────────


def test_memory_repository_lifecycle():
    b = get_backend()
    _, cls, m = _make_tree(b)
    d = DecisionNode(
        name="db-choice", source="memory", qualified_name="memory::db-choice",
        tags=["design"], content="We chose SQLite as the storage backend.",
    ).save()
    c = ConstraintNode(
        name="no-neo4j", source="memory", qualified_name="memory::no-neo4j",
        tags=["design"], content="CodeGraphNode must never import neomodel.",
    ).save()

    b.memory.link_to_code_node(d.canonical_key, cls.canonical_key, "MOTIVATES")
    b.memory.link_to_code_node(c.canonical_key, cls.canonical_key, "CONSTRAINS")

    found = b.memory.find_for_code_node(cls.canonical_key)
    assert {r["rel_type"] for r in found} == {"MOTIVATES", "CONSTRAINS"}
    assert {r["node"].qualified_name for r in found} == {
        "memory::db-choice", "memory::no-neo4j",
    }
    assert len(b.memory.find_for_code_node_by_qname("calc::Calculator")) == 2
    assert b.memory.find_for_code_node_by_qname("nope") == []

    by_tag = [n.qualified_name for n in b.memory.find_by_tag("design")]
    assert "memory::db-choice" in by_tag and "memory::no-neo4j" in by_tag

    linked = b.memory.find_linked_code_node(d.canonical_key)
    assert linked == {"uid": cls.canonical_key, "qualified_name": "calc::Calculator", "rel_type": "MOTIVATES"}
    assert b.memory.find_linked_code_node("nope") is None


def test_memory_to_memory_edges_excluded_from_linked_code():
    b = get_backend()
    _, cls, _ = _make_tree(b)
    d1 = DecisionNode(name="d1", source="memory", qualified_name="memory::d1", content="a").save()
    d2 = DecisionNode(name="d2", source="memory", qualified_name="memory::d2", content="b").save()
    b.memory.link_to_code_node(d1.canonical_key, cls.canonical_key, "MOTIVATES")
    b.memory.merge_edge(d2.canonical_key, "SUPERSEDES", d1.canonical_key, source_label="DecisionNode", target_label="DecisionNode")
    # d2's only non-meta link is the SUPERSEDES edge → no code node
    assert b.memory.find_linked_code_node(d2.canonical_key) is None
    # d1 still links to the class
    assert b.memory.find_linked_code_node(d1.canonical_key)["uid"] == cls.canonical_key


def test_linked_to_ancestors_and_descendants():
    b = get_backend()
    ns, _, m = _make_tree(b)
    d = DecisionNode(name="d", source="memory", qualified_name="memory::d", content="x").save()
    b.memory.link_to_code_node(d.canonical_key, m.canonical_key, "MOTIVATES")

    # Ancestors of the method (ns + cls) have no memory → empty (the
    # method itself is not an ancestor of itself).
    assert b.memory.find_linked_to_ancestors(m.canonical_key) == []
    # Descendants of the namespace include the method → memory found.
    found = b.memory.find_linked_to_descendants(ns.canonical_key)
    assert [n.qualified_name for n in found] == ["memory::d"]


def test_search_content_fts():
    b = get_backend()
    DecisionNode(
        name="db-choice", source="memory", qualified_name="memory::db-choice",
        tags=["design"], content="We chose SQLite for the storage backend.",
    ).save()
    ConstraintNode(
        name="no-neo4j", source="memory", qualified_name="memory::no-neo4j",
        tags=["design"], content="CodeGraphNode must never import neomodel.",
    ).save()

    hits = b.memory.search_content("sqlite storage")
    assert [h["name"] for h in hits] == ["db-choice"]
    assert hits[0]["search_score"] > 0
    hits2 = b.memory.search_content("neomodel")
    assert [h["name"] for h in hits2] == ["no-neo4j"]
    # tag filter
    assert b.memory.search_content("sqlite", tag="as-built") == []


def test_search_semantic_vector():
    b = get_backend()
    vec = [0.1 * i for i in range(8)]
    DecisionNode(
        name="d2", source="memory", qualified_name="memory::d2",
        tags=["design"], content="x", doc_embedding=vec,
    ).save()
    ClassNode(
        name="Other", source="demo", qualified_name="demo::Other",
        kind="class", tags=["design"], doc_embedding=[0.9] * 8,
    ).save()

    hits = b.memory.search_semantic(vec)
    assert hits and hits[0]["qualified_name"] == "memory::d2"
    assert hits[0]["similarity_score"] > 0.99
    assert b.memory.search_semantic(vec, tag="as-built") == []
    # general vector search returns both, best first
    g_hits = b.graph.search_vector(vec, index_name="x")
    assert g_hits[0]["node"].qualified_name == "memory::d2"
    # embedding is rehydrated on read
    assert len(b.graph.find_by_key(b.graph.find_all_by_kind("memory")[0].canonical_key).doc_embedding) == 8


# ── Requirements repository ──────────────────────────────────────────────


def test_hlr_tree():
    from codegraph.identity import IdentityScope, identity_scope

    b = get_backend()
    hlr, _, test, step = _make_hlr_tree(b)
    scope = IdentityScope.project("codegraph-suite")
    with identity_scope(scope):
        target = _keyed_standalone(
            TestNode(name="t", source="req", qualified_name="req::target",
                     test_name="t", tags=["design"]), scope,
        )
    b.graph.merge_relationship(test.canonical_key, "VERIFIES", target.canonical_key)
    b.graph.merge_relationship(step.canonical_key, "CALLEE", target.canonical_key)

    tree = b.requirements.get_hlr_tree(hlr.canonical_key)
    assert tree["hlr"]["name"] == "HLR-1"
    assert tree["hlr"]["description"] == "System must compute"
    assert len(tree["llrs"]) == 1
    llr0 = tree["llrs"][0]
    assert llr0["llr"]["name"] == "LLR-1"
    t0 = llr0["tests"][0]
    assert t0["test"]["test_name"] == "test_add"
    assert t0["verifies_targets"] == ["req::target"]
    assert t0["step_callees"][0]["callee_target"] == "req::target"
    assert b.requirements.get_hlr_tree("nope") == {"hlr": None, "llrs": []}


def test_scaffold_lifecycle():
    from codegraph.identity import IdentityScope, identity_scope

    b = get_backend()
    hlr, _, test, step = _make_hlr_tree(b)
    scope = IdentityScope.project("codegraph-suite")
    with identity_scope(scope):
        scaff = _keyed_standalone(
            TestNode(name="s", source="req", qualified_name="req::scaffold",
                     test_name="s", tags=["scaffold"]), scope,
        )
        b.graph.merge_relationship(test.canonical_key, "VERIFIES", scaff.canonical_key)

        assert b.requirements.find_scaffold_uids() == [scaff.canonical_key]
        # directly_referenced matches AssertionNode/TestStepNode sources via
        # LEFT_OPERAND/RIGHT_OPERAND/CALLEE — VERIFIES doesn't count.
        assert b.requirements.find_scaffold_uids(directly_referenced=True) == []
        step2 = _keyed_standalone(
            TestStepNode(name="st", source="req", qualified_name="req::step",
                         order=1, tags=["design"]), scope,
        )
        b.graph.merge_relationship(step2.canonical_key, "CALLEE", scaff.canonical_key)
        assert b.requirements.find_scaffold_uids(directly_referenced=True) == [scaff.canonical_key]
        assert b.requirements.find_scaffold_uids(with_edges=["VERIFIES"]) == [scaff.canonical_key]
        assert b.requirements.find_scaffold_uids(without_edges=True) == []
        # a scaffold without any edges is an orphan
        orphan = _keyed_standalone(
            TestNode(name="o", source="req", qualified_name="req::orphan",
                     test_name="o", tags=["scaffold"]), scope,
        )
    assert b.requirements.find_scaffold_uids(without_edges=True) == [orphan.canonical_key]

    b.requirements.retag_scaffold_to_design(scaff.canonical_key)
    assert b.requirements.find_scaffold_uids() == [orphan.canonical_key]
    b.requirements.delete_scaffold(orphan.canonical_key)
    assert b.requirements.find_scaffold_uids() == []


def test_scaffold_parents_of_referenced():
    b = get_backend()
    parent = ClassNode(name="P", source="demo", qualified_name="demo::P", kind="class", tags=["scaffold"]).save()
    child = ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class", tags=["scaffold"]).save()
    b.connect(parent, "COMPOSES", child)
    assert b.requirements.find_scaffold_parents_of_referenced([child.canonical_key]) == [parent.canonical_key]
    assert b.requirements.find_scaffold_parents_of_referenced([]) == []
    assert b.requirements.find_scaffold_parents_of_referenced(["nope"]) == []


def test_unresolved_verifications_and_callees():
    b = get_backend()
    hlr, _, test, step = _make_hlr_tree(b)
    from codegraph.identity import IdentityScope

    scope = IdentityScope.repository("codegraph-suite", "codegraph")
    scaff = _keyed_standalone(TestNode(
        name="s", source="req", qualified_name="req::scaffold",
        test_name="s", tags=["scaffold"],
    ), scope)
    b.graph.merge_relationship(test.canonical_key, "VERIFIES", scaff.canonical_key)
    b.graph.merge_relationship(step.canonical_key, "CALLEE", scaff.canonical_key)

    unres_v = b.requirements.find_unresolved_verifications(hlr.canonical_key)
    assert unres_v and unres_v[0]["test_qname"] == test.qualified_name
    assert unres_v[0]["target_qname"] == "req::scaffold"
    assert unres_v[0]["llr_name"] == "LLR-1"
    unres_c = b.requirements.find_unresolved_callee_steps(hlr.canonical_key)
    assert unres_c and unres_c[0]["step_qname"] == step.qualified_name
    assert unres_c[0]["target_qname"] == "req::scaffold"

    # resolve via merge_verification / replace_callee
    real = _keyed_standalone(TestNode(
        name="r", source="req", qualified_name="req::real",
        test_name="r", tags=["design"],
    ), scope)
    b.requirements.merge_verification(test.qualified_name, real.qualified_name)
    b.requirements.replace_callee(step.qualified_name, real.qualified_name)
    tree = b.requirements.get_hlr_tree(hlr.canonical_key)
    t0 = tree["llrs"][0]["tests"][0]
    assert "req::real" in t0["verifies_targets"]
    assert t0["step_callees"][0]["callee_target"] == "req::real"
    assert b.requirements.find_unresolved_callee_steps(hlr.canonical_key) == []


def test_merge_depends_on():
    b = get_backend()
    hlr = HLR(name="HLR-1", source="req", qualified_name="AG-HLR-01", tags=["requirements"], description="a").save()
    HLR(name="HLR-2", source="req", qualified_name="AG-HLR-02", tags=["requirements"], description="b").save()
    info = b.requirements.merge_depends_on(hlr.canonical_key, "HLR-2", description="needs HLR-2")
    assert info["relation"] == "DEPENDS_ON"
    assert info["target"] == "HLR-2"
    assert b.requirements.merge_depends_on(hlr.canonical_key, "NOPE") is None


def test_hlr_subtree_layer_graph():
    b = get_backend()
    hlr, _, _, _ = _make_hlr_tree(b)
    g = b.graph.get_hlr_subtree(hlr.canonical_key)
    assert len(g.entries) >= 1
    assert b.graph.get_hlr_subtree("nope").tags == frozenset({"design"})


# ── execute_raw / wipe ───────────────────────────────────────────────────


def test_execute_raw_shape():
    b = get_backend()
    rows, cols = b.execute_raw("SELECT 1 AS one, 'x' AS two")
    assert cols == ["one", "two"]
    assert rows == [{"one": 1, "two": "x"}]


def test_wipe_recreates_schema():
    b = get_backend()
    _make_tree(b)
    b.wipe()
    assert b.graph.count_all_nodes() == 0
    assert b.health_check() is True
    # backend remains usable after wipe
    ClassNode(name="C", source="demo", qualified_name="demo::C", kind="class").save()
    assert b.graph.count_all_nodes() == 1
