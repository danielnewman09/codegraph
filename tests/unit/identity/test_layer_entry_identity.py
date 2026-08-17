"""Work Package 5.1 — LayerGraph entry identity + ambiguity elimination.

- entry (local) keys are canonical keys when nodes have them, legacy
  uids otherwise (``_node_key`` → ``primary_key``);
- reference serialization keeps ``target_uid`` as the real legacy uid
  while entry keys are canonical (compatibility map);
- two distinct nodes sharing a legacy uid or canonical key in one
  document/load raise instead of last-write-wins;
- ``identity_digest()`` gives full-graph identity comparison.
"""

from __future__ import annotations

import pytest

from codegraph.backends import get_backend, set_backend
from codegraph.backends.memory import InMemoryBackend
from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.identity import (
    AmbiguousUidError,
    IdentityScope,
    KeyConflictError,
    identity_scope,
)
from codegraph.models import ClassNode, MethodNode, NamespaceNode

SCOPE = IdentityScope.repository("codegraph-suite", "codegraph")


@pytest.fixture(autouse=True)
def _memory_backend():
    previous = get_backend()
    set_backend(InMemoryBackend())
    yield
    set_backend(previous)


def _saved():
    ns = NamespaceNode(name="graph", qualified_name="codegraph.graph", source="cg")
    cls = ClassNode(name="LayerGraph", qualified_name="codegraph.graph.LayerGraph",
                    source="cg")
    m = MethodNode(name="load", qualified_name="codegraph.graph.LayerGraph::load",
                   argsstring="()", type_signature="void", source="cg")
    with identity_scope(SCOPE):
        ns.save()
        cls.save()
        m.save()
    return ns, cls, m


class TestEntryIdentity:
    def test_entry_keys_prefer_canonical(self) -> None:
        ns, cls, _ = _saved()
        graph = LayerGraph(tags=frozenset({"as-built"}))
        graph.entries[LayerGraph._node_key(ns)] = CompositeEntry(node=ns)
        graph.entries[LayerGraph._node_key(cls)] = CompositeEntry(node=cls)
        keys = set(graph.entries)
        assert keys == {ns.canonical_key, cls.canonical_key}
        assert ns.canonical_key.startswith("cg:v1:")

    def test_legacy_nodes_keep_uid_keys(self) -> None:
        """Removed in the cutover: every persistable node must carry a
        canonical key, so entry keys are always canonical.  A node
        without a key cannot be saved or serialized (WP A)."""
        from codegraph.identity import IdentityError

        legacy = ClassNode(name="W", qualified_name="app::W", source="leg")
        with pytest.raises(IdentityError):
            legacy.save()

    def test_reference_serialization_emits_canonical_key(self) -> None:
        """WP B: reference edges carry only the target's canonical key."""
        ns, cls, m = _saved()
        graph = LayerGraph(tags=frozenset({"as-built"}))
        ns_key, cls_key, m_key = (LayerGraph._node_key(n) for n in (ns, cls, m))
        ns_entry = CompositeEntry(node=ns)
        ns_entry.references.append(("INVOKES", m_key, "MethodNode"))
        graph.entries[ns_key] = ns_entry
        graph.entries[m_key] = CompositeEntry(node=m)
        edges = []
        for entry in graph.serialize(fields="all"):
            edges.extend(entry.get("edges", []))
        assert len(edges) == 1
        edge = edges[0]
        assert edge["target_key"] == m.canonical_key
        assert "target_uid" not in edge

    def test_roundtrip_with_canonical_entry_keys(self) -> None:
        ns, cls, m = _saved()
        graph = LayerGraph(tags=frozenset({"as-built"}))
        ns_key, cls_key, m_key = (LayerGraph._node_key(n) for n in (ns, cls, m))
        ns_entry = graph.entries.setdefault(ns_key, CompositeEntry(node=ns))
        ns_entry.children.setdefault("ClassNode", {})[cls_key] = CompositeEntry(node=cls)
        ns_entry.references.append(("INVOKES", m_key, "MethodNode"))
        graph.entries[m_key] = CompositeEntry(node=m)
        graph2 = LayerGraph.deserialize(graph.serialize(fields="all"))
        keys = set(graph2.entries)
        assert keys == {ns.canonical_key, m.canonical_key}
        ns2 = next(iter(graph2.entries.values()))
        assert "ClassNode" in ns2.children
        assert ns2.references == [("INVOKES", m.canonical_key, "MethodNode")]


class TestAmbiguityElimination:
    def test_shared_canonical_key_in_document_raises(self) -> None:
        ns, cls, _ = _saved()
        cls2 = ClassNode(name="LayerGraph",
                         qualified_name="codegraph.graph.LayerGraph", source="other")
        data = [
            {
                "type": "ClassNode", "name": "LayerGraph",
                "qualified_name": "codegraph.graph.LayerGraph", "source": "cg",
                "canonical_key": cls.canonical_key,
                "tags": ["as-built"], "edges": [],
            },
            {
                "type": "ClassNode", "name": "LayerGraph",
                "qualified_name": "codegraph.graph.LayerGraph", "source": "other",
                "canonical_key": cls.canonical_key,
                "tags": ["as-built"], "edges": [],
            },
        ]
        with pytest.raises(KeyConflictError):
            LayerGraph.deserialize(data)

    def test_duplicate_copy_of_same_node_tolerated(self) -> None:
        """D9-style placements (same logical node nested + at root) are
        not ambiguous — they load, with the child position winning."""
        ns, cls, _ = _saved()
        data = [
            {
                "type": "NamespaceNode", "name": "graph",
                "qualified_name": "codegraph.graph", "source": "cg",
                "canonical_key": ns.canonical_key,
                "tags": ["as-built"], "edges": [], "composes": [
                    {
                        "type": "ClassNode", "name": "LayerGraph",
                        "qualified_name": "codegraph.graph.LayerGraph",
                        "source": "cg",
                        "canonical_key": cls.canonical_key,
                        "tags": ["as-built"], "edges": [],
                    },
                ],
            },
            # the same class ALSO at root (D9 placement)
            {
                "type": "ClassNode", "name": "LayerGraph",
                "qualified_name": "codegraph.graph.LayerGraph",
                "source": "cg",
                "canonical_key": cls.canonical_key,
                "tags": ["as-built"], "edges": [],
            },
        ]
        graph = LayerGraph.deserialize(data)
        # nested position wins: cls is a child, not a root
        assert len(graph.entries) == 1
        ns_entry = next(iter(graph.entries.values()))
        assert "ClassNode" in ns_entry.children


class TestIdentityDigest:
    def test_digest_equal_for_equal_graphs(self) -> None:
        ns, cls, m = _saved()
        g1 = LayerGraph(tags=frozenset({"as-built"}))
        ns_key, cls_key, m_key = (LayerGraph._node_key(n) for n in (ns, cls, m))
        e1 = g1.entries.setdefault(ns_key, CompositeEntry(node=ns))
        e1.children.setdefault("ClassNode", {})[cls_key] = CompositeEntry(node=cls)
        e1.references.append(("INVOKES", m_key, "MethodNode"))
        g1.entries[m_key] = CompositeEntry(node=m)

        ns2, cls2, m2 = _saved()  # fresh instances, same identities
        g2 = LayerGraph(tags=frozenset({"as-built"}))
        k2 = (LayerGraph._node_key(n) for n in (ns2, cls2, m2))
        ns_key2, cls_key2, m_key2 = k2
        e2 = g2.entries.setdefault(ns_key2, CompositeEntry(node=ns2))
        e2.children.setdefault("ClassNode", {})[cls_key2] = CompositeEntry(node=cls2)
        e2.references.append(("INVOKES", m_key2, "MethodNode"))
        g2.entries[m_key2] = CompositeEntry(node=m2)

        assert g1.identity_digest() == g2.identity_digest()

    def test_digest_differs_on_content_change(self) -> None:
        ns, cls, m = _saved()
        g1 = LayerGraph(tags=frozenset({"as-built"}))
        ns_key, m_key = LayerGraph._node_key(ns), LayerGraph._node_key(m)
        e1 = g1.entries.setdefault(ns_key, CompositeEntry(node=ns))
        e1.children.setdefault("ClassNode", {})[
            LayerGraph._node_key(cls)
        ] = CompositeEntry(node=cls)
        g1.entries[m_key] = CompositeEntry(node=m)
        d1 = g1.identity_digest()

        changed = _saved()
        ns3, cls3, m3 = changed
        cls3.brief_description = "changed"
        g2 = LayerGraph(tags=frozenset({"as-built"}))
        e2 = g2.entries.setdefault(LayerGraph._node_key(ns3), CompositeEntry(node=ns3))
        e2.children.setdefault("ClassNode", {})[
            LayerGraph._node_key(cls3)
        ] = CompositeEntry(node=cls3)
        g2.entries[LayerGraph._node_key(m3)] = CompositeEntry(node=m3)
        assert g2.identity_digest() != d1

    def test_digest_stable_across_serialize_roundtrip(self) -> None:
        ns, cls, m = _saved()
        graph = LayerGraph(tags=frozenset({"as-built"}))
        ns_key, cls_key, m_key = (LayerGraph._node_key(n) for n in (ns, cls, m))
        e = graph.entries.setdefault(ns_key, CompositeEntry(node=ns))
        e.children.setdefault("ClassNode", {})[cls_key] = CompositeEntry(node=cls)
        e.references.append(("INVOKES", m_key, "MethodNode"))
        graph.entries[m_key] = CompositeEntry(node=m)
        graph2 = LayerGraph.deserialize(graph.serialize(fields="all"))
        assert graph.identity_digest() == graph2.identity_digest()
