"""WP5.2 — lossless flat portable snapshot of the Transaction slice.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

The slice is the connected requirements + code + test graph WP5.1 indexes:
one HLR owning five LLRs, the real ``cpp_sqlite::Transaction`` class and its
members, and the five real GoogleTests with all their children.

This module proves the slice can be exported without a backend:

1. the versioned flat document is a strict fixpoint — export, deserialize,
   export again, byte for byte;
2. the deserialized graph has the same normalized model as the indexed graph:
   every durable property of every node, every portable outgoing edge with its
   attributes, and every composition parent link;
3. nothing vanishes silently — each relation the flat layout does not carry as
   an edge is classified and justified, and the classification is compared
   against a frozen set so a new relation type cannot slip through;
4. deserialization needs no backend, no cache and no pre-computed index;
5. a changed property, a removed edge and a missing node are each reported
   precisely.

and, under WP5.5, that the same document survives an empty backend:

6. persisted into a brand-new backend and read back through backend-neutral
   repository APIs, the slice is an exact normalized bijection with the source
   graph and with the deserialized graph;
7. a second load is a no-op — no duplicate node, no duplicate relationship, no
   changed property;
8. a reversed edge and an unexpected extra edge are each reported precisely,
   at the document boundary and at the backend boundary.

The flat document carries the canonical ``cg:v1:`` key of every target.  That
includes the composing parents of a shared child and the ``COMPOSES`` children
of the HLR, whose in-memory bucket keys are the importer's local qualified
names — the flat layout resolves both through canonical identity, which is why
the flat form (not the nested one) is the portable snapshot.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

import pytest

from codegraph.graph import LayerGraph

from .test_transaction_requirements import SCOPE_PREFIX
from .transaction_backend_roundtrip import (
    BACKEND_KINDS,
    NEO4J_KIND,
    SLICE_TAGS,
    create_backend,
    edge_report,
    graph_from_backend,
    relationship_counts,
    require_contract,
    stored_keys,
)
from .transaction_evidence import (
    load_evidence_definitions,
    slice_graph_with_evidence,
)
from .transaction_memories import (
    load_memory_definitions,
    slice_graph_with_memories,
)
from .transaction_slice import build_transaction_slice

# ---------------------------------------------------------------------------
# Edge and node classification
# ---------------------------------------------------------------------------

#: Relation types the flat layout does not carry as edges, with the reason.
#:
#: Every other relation type is *portable*: it must appear in the flat document
#: with the same endpoints and attributes.  Silently adding a relation to this
#: set is how an intended edge would vanish, so the exclusion is asserted.
EXCLUDED_RELATIONS: Mapping[str, str] = {
    "COMPOSES": "carried as the composing parent's child placement",
    "HAS_IMPLEMENTATION": (
        "transport edge of an implementation leaf; carried only when the "
        "leaf is the sole carrier of its text"
    ),
    "TEMPLATE_PARAM": "template-parameter transport derived from the signature",
}

#: Relation types observed on the indexed slice.  Frozen so that a *new*
#: relation type — which the comparison below would otherwise have to guess
#: about — fails this module instead of being ignored.  ``SUPERSEDES`` is
#: deliberately absent: the reviewed memories carry a ``refines`` link and no
#: supersession, so a superseding memory has to be classified here first.
PORTABLE_RELATIONS = frozenset({
    "CALLEE", "CONSTRAINS", "DEFINED_IN", "DEPENDS_ON", "ENFORCES_CONCEPT",
    "EVIDENCES", "EXPLAINS", "HAS_PARAMETER", "INCLUDES", "INHERITS_FROM",
    "INVOKES", "MOTIVATES", "REALIZED_BY", "REFINES", "SPECIALIZES",
    "VERIFIED_BY", "VERIFIES",
})

#: Node type whose leaves are inlined on the owning node.
IMPLEMENTATION_TYPE = "ImplementationNode"


# ---------------------------------------------------------------------------
# Normalized model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotDrift:
    """One precise difference between two normalized models."""

    kind: str
    location: str
    expected: object
    actual: object

    def describe(self) -> str:
        return (
            f"{self.kind}: {self.location}: "
            f"expected {self.expected!r}, got {self.actual!r}"
        )


def inlined_implementation_keys(graph: LayerGraph) -> set[str]:
    """Canonical keys of implementation leaves the flat layout inlines.

    Mirrors the layout rule: a leaf is inlined when its owner's node type
    exposes the text as a populated ``body`` property, so the text rides on
    the owner; a leaf whose owner has no such property (a ``TestStepNode`` —
    its source block *is* the leaf) is carried as a node with its
    ``HAS_IMPLEMENTATION`` edge, because dropping it would lose the text.

    ``TestImplementationContent.test_document_omits_exactly_the_inlined_leaves``
    asserts that this prediction is exactly what the document does, so the
    mirror cannot hide a difference.
    """
    from codegraph.models.tags import PropertyRegistry

    flat = graph._flat_index()
    inlined: set[str] = set()
    for entry in graph._all_entries():
        if not PropertyRegistry.has_property(type(entry.node), "body"):
            continue
        if not (getattr(entry.node, "body", "") or ""):
            continue
        for relation_type, target_key, _target_type in entry.references:
            if relation_type != "HAS_IMPLEMENTATION":
                continue
            leaf = flat.get(target_key)
            if leaf is not None and type(leaf.node).__name__ == IMPLEMENTATION_TYPE:
                inlined.add(target_key)
    return inlined


def durable_properties(node) -> dict:
    """Every declared property of *node*, without asking a backend for edges.

    ``CodeGraphNode.serialize(fields="all")`` is the document's property form,
    but it also walks the *globally registered* backend for outgoing edges —
    which a persistence test has to discard, and which would otherwise make the
    comparison depend on whichever backend happens to be registered rather than
    on the node itself.  This is the same property set minus ``edges``:
    ``TestNormalizationCoverage.test_durable_properties_matches_serialize_for_every_node``
    pins that equality for every node of the slice, so the shortcut cannot hide
    a property.
    """
    from codegraph.models.descriptors import PropertyRegistry

    declared = PropertyRegistry.properties_of(type(node))
    values = dict(sorted(PropertyRegistry.values_of(node).items()))
    values.pop("edges", None)
    # The node-kind discriminator lives under ``node_type`` when the class
    # declares its own ``type`` property (ParameterNode), as serialize() does.
    discriminator = "node_type" if "type" in declared else "type"
    values[discriminator] = type(node).__name__
    if "canonical_key" in declared and getattr(node, "canonical_key", ""):
        values["canonical_key"] = node.canonical_key
    return values


def normalized_model(graph: LayerGraph) -> dict[str, dict]:
    """The durable, layout-independent model of *graph*.

    The flat layout's documented exclusions are applied on both sides so the
    indexed graph and the deserialized graph are comparable: transport
    relations are dropped, ``COMPOSES`` becomes the child's ``composed_by``
    tuple, and inlined implementation leaves are removed.  Nothing else is
    filtered — every remaining property of every remaining node participates.
    """
    inlined = inlined_implementation_keys(graph)
    flat = graph._flat_index()

    composed_by: dict[str, list[str]] = {}
    for entry in graph._all_entries():
        parent_key = LayerGraph._node_key(entry.node)
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                composed_by.setdefault(
                    LayerGraph._node_key(child_entry.node), []
                ).append(parent_key)

    model: dict[str, dict] = {}
    for entry in graph._all_entries():
        key = LayerGraph._node_key(entry.node)
        if key in inlined:
            continue
        properties = durable_properties(entry.node)
        edges: dict[tuple[str, str, str], dict] = {}
        for relation_type, target_key, target_type in entry.references:
            if relation_type in EXCLUDED_RELATIONS:
                continue
            assert relation_type in PORTABLE_RELATIONS, (
                f"{key} has unclassified relation {relation_type!r}: classify "
                "it as portable, or record why the flat layout drops it"
            )
            # A reference names its far end by canonical key; the target's class
            # is a fact about the graph rather than about whoever wrote the edge.
            # The indexing path records the label the parser declared
            # (``"member"``, ``"CompoundNode"``) where a backend reports the
            # class it stored under that key, so both sides of every comparison
            # read the class off the graph they are already looking at.
            target = flat.get(target_key)
            stored_type = (
                type(target.node).__name__ if target is not None else target_type
            )
            edges[(relation_type, target_key, stored_type)] = dict(
                entry.edge_attrs.get((relation_type, target_key)) or {}
            )
        model[key] = {
            "type": type(entry.node).__name__,
            "properties": properties,
            "edges": edges,
            "composed_by": sorted(composed_by.get(key, ())),
        }
    return model


def compare_models(
    expected: Mapping[str, dict], actual: Mapping[str, dict]
) -> list[SnapshotDrift]:
    """Report every difference between two normalized models, precisely."""
    drifts: list[SnapshotDrift] = []
    for key in sorted(set(expected) | set(actual)):
        if key not in actual:
            drifts.append(SnapshotDrift(
                "missing_node", key, expected[key]["type"], None,
            ))
            continue
        if key not in expected:
            drifts.append(SnapshotDrift(
                "extra_node", key, None, actual[key]["type"],
            ))
            continue
        want, got = expected[key], actual[key]

        if want["type"] != got["type"]:
            drifts.append(SnapshotDrift(
                "changed_node_type", key, want["type"], got["type"],
            ))

        for name in sorted(set(want["properties"]) | set(got["properties"])):
            if want["properties"].get(name) != got["properties"].get(name):
                drifts.append(SnapshotDrift(
                    "changed_property",
                    f"{key}.{name}",
                    want["properties"].get(name),
                    got["properties"].get(name),
                ))

        for edge in sorted(set(want["edges"]) - set(got["edges"])):
            drifts.append(SnapshotDrift("missing_edge", key, edge, None))
        for edge in sorted(set(got["edges"]) - set(want["edges"])):
            drifts.append(SnapshotDrift("extra_edge", key, None, edge))
        for edge in sorted(set(want["edges"]) & set(got["edges"])):
            if want["edges"][edge] != got["edges"][edge]:
                drifts.append(SnapshotDrift(
                    "changed_edge_attributes",
                    f"{key} {edge}",
                    want["edges"][edge],
                    got["edges"][edge],
                ))

        if want["composed_by"] != got["composed_by"]:
            drifts.append(SnapshotDrift(
                "changed_composition", key,
                tuple(want["composed_by"]), tuple(got["composed_by"]),
            ))
    return drifts


def _document_bytes(document: Mapping) -> str:
    return json.dumps(document, indent=2, sort_keys=True, default=str)


def document_entry_type(entry: Mapping) -> str:
    """The node-kind discriminator of a serialized entry.

    ``serialize()`` writes it under ``node_type`` when the class declares a
    real ``type`` property — ``ParameterNode`` does, holding the C++ type string
    — so reading ``type`` blindly would compare a C++ type against a class name.
    """
    return entry["node_type"] if "node_type" in entry else entry["type"]


def _edge_attributes(edge: Mapping) -> dict:
    """Everything on a wire edge that is not part of its identity."""
    return {
        key: value for key, value in edge.items()
        if key not in ("relation_type", "target_key", "target_type",
                       "target_local_id")
    }


def document_edges(document: Mapping) -> dict[str, dict[tuple, dict]]:
    """``{source_key: {(relation, endpoint, target_type, field): attributes}}``.

    Every edge the document states, including ``COMPOSES`` and
    ``HAS_IMPLEMENTATION`` — the two relations the normalized model treats as
    transport.  ``field`` records *how* the document names the far end:
    ``target_key`` for a node the document itself holds, ``target_ref`` for an
    endpoint outside the graph (an ``#include`` path with ``local: false``).
    A backend holds relationships between nodes it stores, so the two kinds are
    kept apart instead of being quietly equated — see
    ``test_the_backend_reports_every_document_edge_verbatim``.
    """
    return {
        entry["canonical_key"]: {
            (
                edge["relation_type"],
                edge.get("target_key") or edge.get("target_ref") or "",
                edge.get("target_type") or "",
                "target_key" if edge.get("target_key") else "target_ref",
            ): _edge_attributes(edge)
            for edge in entry["edges"]
        }
        for entry in document["entries"]
    }


def _flat_document(graph: LayerGraph, *, implementation: bool = True) -> dict:
    """The versioned flat document for *graph*."""
    return graph.serialize(
        fields="all", document=True, layout="flat",
        export_implementation=implementation,
    )


def _walk(entries):
    for entry in entries:
        yield entry
        yield from _walk(entry.get("composes", []))


# ---------------------------------------------------------------------------
# Fixtures — the shared session index run (one IndexService run per session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def indexed(transaction_slice_index):
    """The slice graph plus the WP5.3 memories and the WP5.4 execution evidence.

    WP5.5 step 1 names the bounded slice: requirements, memories, code, method
    bodies, the five real tests with all their children, and two evidence
    records.  Both overlays merge non-mutatingly, so the session index result
    stays exactly as indexed and the memories and evidence become ordinary
    entries of the graph — which means every guarantee below (fixpoint, exact
    model comparison, edge classification, empty-backend bijection) applies to
    ``MOTIVATES``/``CONSTRAINS``/``EXPLAINS``/``REFINES``/``SUPERSEDES`` and
    ``EVIDENCES``/``DEPENDS_ON`` edges too.
    """
    with_memories = slice_graph_with_memories(
        transaction_slice_index.graph, load_memory_definitions()
    )
    graph, _edges = slice_graph_with_evidence(
        with_memories, load_evidence_definitions()
    )
    return _ConnectedIndex(transaction_slice_index, graph)


class _ConnectedIndex:
    """The index result with its graph swapped for the connected slice."""

    def __init__(self, result, graph):
        self._result = result
        self.graph = graph

    def __getattr__(self, name):
        return getattr(self._result, name)


@pytest.fixture(scope="module")
def snapshot(indexed) -> dict:
    """The flat document and its deserialized graph (one export per session)."""
    document = _flat_document(indexed.graph)
    return {
        "document": document,
        "restored": LayerGraph.deserialize(copy.deepcopy(document)),
    }


# ---------------------------------------------------------------------------
# 1. Versioned flat export/import is a strict fixpoint
# ---------------------------------------------------------------------------


class TestFlatFixpoint:
    def test_flat_document_is_a_strict_fixpoint(self, snapshot):
        document = snapshot["document"]

        again = _flat_document(snapshot["restored"])

        assert _document_bytes(again) == _document_bytes(document)

    def test_document_envelope_is_versioned(self, snapshot):
        assert set(snapshot["document"]) == {
            "format_version", "identity_version", "entries",
        }

    def test_every_node_is_emitted_exactly_once(self, snapshot, indexed):
        keys = [
            entry["canonical_key"] for entry in snapshot["document"]["entries"]
        ]

        assert len(keys) == len(set(keys)), "a canonical node was duplicated"
        assert len(keys) == len(list(indexed.graph._all_entries())) - len(
            inlined_implementation_keys(indexed.graph)
        )
        for key in keys:
            assert key.startswith("cg:v1:"), key

    def test_nested_export_is_unchanged_by_the_flat_option(self, indexed):
        """The long-standing nested form is what a caller still gets.

        An explicit ``layout="nested"`` request reproduces the default output
        byte for byte, keeps children under ``composes``, and lists no
        ``COMPOSES`` edge — the legacy contract.
        """
        default = indexed.graph.serialize(fields="all", document=True)
        explicit = indexed.graph.serialize(
            fields="all", document=True, layout="nested"
        )
        assert explicit == default

        entries = list(_walk(default["entries"]))
        assert not [
            edge for entry in entries for edge in entry.get("edges", [])
            if edge["relation_type"] == "COMPOSES"
        ]
        assert len(entries) == len(list(indexed.graph._all_entries()))
        assert len(set(
            entry["canonical_key"] for entry in entries
        )) == len(entries)


# ---------------------------------------------------------------------------
# 2./3. The deserialized graph matches the indexed model — nothing vanishes
# ---------------------------------------------------------------------------


class TestSnapshotFidelity:
    def test_deserialized_model_matches_the_indexed_model(self, snapshot, indexed):
        drifts = compare_models(
            normalized_model(indexed.graph),
            normalized_model(snapshot["restored"]),
        )
        assert drifts == [], "\n".join(d.describe() for d in drifts)

    def test_model_covers_the_frozen_slice(self, snapshot, indexed):
        document = snapshot["document"]
        entries = {entry["canonical_key"]: entry for entry in document["entries"]}
        slice_ = build_transaction_slice(
            indexed.graph.serialize(fields="all", export_implementation=True)
        )

        assert slice_.class_key in entries
        for label, key in slice_.method_keys.items():
            assert key in entries, label
        for name, key in slice_.test_keys.items():
            assert key in entries, name
        for key in slice_.canonical_keys():
            assert key in entries, key
            assert key.startswith(SCOPE_PREFIX), key

        requirement_types = Counter(
            entry["type"] for entry in entries.values()
            if entry["type"] in ("HLR", "LLR")
        )
        assert requirement_types == Counter({"LLR": 5, "HLR": 1})

    def test_excluded_relations_are_accounted_for(self, snapshot, indexed):
        """No selected edge disappears without a recorded, asserted reason."""
        observed = Counter(
            relation_type
            for entry in indexed.graph._all_entries()
            for relation_type, _target, _type in entry.references
        )
        assert set(observed) - set(EXCLUDED_RELATIONS) == set(PORTABLE_RELATIONS), (
            "the slice's relation types changed; classify the difference"
        )
        # The transport relations the plan excludes really are present, so the
        # exclusions are load-bearing rather than speculative.
        assert observed["HAS_IMPLEMENTATION"] > 0
        assert observed["TEMPLATE_PARAM"] > 0

        emitted = Counter(
            edge["relation_type"]
            for entry in snapshot["document"]["entries"]
            for edge in entry["edges"]
        )
        # Every portable relation is carried …
        assert set(PORTABLE_RELATIONS) <= set(emitted), sorted(
            set(PORTABLE_RELATIONS) - set(emitted)
        )
        # … nothing else is, except the composition edges (which the flat
        # layout carries explicitly) and the transport edge of a leaf that had
        # to be retained as the sole carrier of its text.
        assert set(emitted) <= set(PORTABLE_RELATIONS) | {
            "COMPOSES", "HAS_IMPLEMENTATION",
        }, sorted(set(emitted) - set(PORTABLE_RELATIONS))
        assert emitted["COMPOSES"] > 0
        assert emitted["TEMPLATE_PARAM"] == 0
        assert emitted["HAS_IMPLEMENTATION"] > 0

    def test_reference_set_semantics_are_explicit(self, indexed):
        """Only *identical* duplicate references collapse, and they are counted.

        ``IndexService`` records one reference per source occurrence, so a node
        can carry the same ``(relation, target)`` twice while both wire layouts
        carry a logical edge once.  The collapse is enumerated here so it can
        never hide a real difference: the model is the *set* of that multiset,
        and every duplicate is byte-identical by construction.
        """
        duplicates = {
            LayerGraph._node_key(entry.node): {
                edge: count
                for edge, count in Counter(
                    (relation_type, target_key, target_type)
                    for relation_type, target_key, target_type in entry.references
                    if relation_type not in EXCLUDED_RELATIONS
                ).items()
                if count > 1
            }
            for entry in indexed.graph._all_entries()
        }
        duplicates = {key: counts for key, counts in duplicates.items() if counts}

        assert duplicates, "the slice no longer exercises duplicate references"
        collapsed = sum(
            count - 1 for counts in duplicates.values() for count in counts.values()
        )
        assert collapsed > 0

        model = normalized_model(indexed.graph)
        for key, counts in duplicates.items():
            for edge in counts:
                assert edge in model[key]["edges"], (key, edge)

    def test_import_needs_no_backend_and_no_precomputed_index(
        self, snapshot, monkeypatch
    ):
        """Deserialization is pure: no backend, no cache, no side effects."""
        import codegraph.graph as graph_module

        def _explode(*args, **kwargs):
            raise AssertionError("deserialization touched a backend")

        for name in ("get_backend", "resolve_node", "resolve_reference"):
            if hasattr(graph_module, name):
                monkeypatch.setattr(graph_module, name, _explode)

        document = copy.deepcopy(snapshot["document"])
        restored = LayerGraph.deserialize(document)

        # The identity universe is derived from the document alone …
        assert restored.known_keys == frozenset(
            entry["canonical_key"] for entry in document["entries"]
        )
        # … and it is complete enough to re-export without enrichment.
        assert _document_bytes(_flat_document(restored)) == _document_bytes(
            snapshot["document"]
        )


# ---------------------------------------------------------------------------
# 4. Implementation content rides on the owning node, exactly once
# ---------------------------------------------------------------------------


class TestImplementationContent:
    def test_document_omits_exactly_the_inlined_leaves(self, snapshot, indexed):
        """The document's omissions are exactly the predicted set.

        This is what makes the layout rule falsifiable: the mirror used by the
        model comparison must agree with the serializer output.
        """
        emitted = {
            entry["canonical_key"] for entry in snapshot["document"]["entries"]
        }
        every_key = set(indexed.graph._flat_index())

        assert every_key - emitted == inlined_implementation_keys(indexed.graph)
        assert len(every_key - emitted) == 48, (
            "the number of inlined method implementations changed"
        )

    def test_flat_layout_carries_method_bodies_on_the_method(self, snapshot, indexed):
        entries = {
            entry["canonical_key"]: entry
            for entry in snapshot["document"]["entries"]
        }
        inlined = inlined_implementation_keys(indexed.graph)

        assert not [
            entry for entry in entries.values()
            if entry["type"] == IMPLEMENTATION_TYPE
            and entry["canonical_key"] in inlined
        ], "an inlined implementation was also emitted as a leaf"
        assert not [
            entry for key, entry in entries.items()
            if entry["type"] == "MethodNode"
            and any(
                edge["relation_type"] == "HAS_IMPLEMENTATION"
                for edge in entry["edges"]
            )
        ], "a MethodNode still carries a transport edge"
        assert len([
            entry for entry in entries.values()
            if entry["type"] == "MethodNode" and entry.get("body")
        ]) > 0

        # A transport edge may only point at a node the document carries.
        for entry in entries.values():
            for edge in entry["edges"]:
                if edge["relation_type"] == "HAS_IMPLEMENTATION":
                    assert edge["target_key"] in entries, edge
                    assert entries[edge["target_key"]]["type"] == IMPLEMENTATION_TYPE

    def test_each_implementation_leaf_is_carried_exactly_once(
        self, snapshot, indexed
    ):
        """Every leaf's payload is either inlined on its owner or emitted once.

        Distinct nodes may legitimately share identical source text (four
        steps of the fixture share one setup line), so the invariant is per
        canonical leaf, not per text.
        """
        entries = {
            entry["canonical_key"]: entry
            for entry in snapshot["document"]["entries"]
        }
        flat = indexed.graph._flat_index()
        inlined = inlined_implementation_keys(indexed.graph)
        leaves = {
            key: entry for key, entry in flat.items()
            if type(entry.node).__name__ == IMPLEMENTATION_TYPE
        }
        assert leaves

        for key, leaf in leaves.items():
            text = getattr(leaf.node, "implementation", "")
            assert text, key
            owner = next(
                owner_key for owner_key, owner in flat.items()
                for relation_type, target_key, _type in owner.references
                if relation_type == "HAS_IMPLEMENTATION" and target_key == key
            )
            if key in inlined:
                assert key not in entries
                assert entries[owner].get("body") == flat[owner].node.body
            else:
                assert entries[key].get("implementation") == text
                assert owner in entries

    def test_implementation_free_export_carries_no_source_text(self, indexed):
        lean = _flat_document(indexed.graph, implementation=False)

        assert not [
            entry for entry in lean["entries"]
            if entry["type"] == IMPLEMENTATION_TYPE
        ]
        assert not [
            (entry["canonical_key"], edge)
            for entry in lean["entries"] for edge in entry["edges"]
            if edge["relation_type"] == "HAS_IMPLEMENTATION"
        ]
        assert not [
            entry for entry in lean["entries"]
            if entry["type"] == "MethodNode" and entry.get("body")
        ]

    def test_every_inlined_owner_really_carries_its_text(self, indexed):
        """The inlining rule trades the leaf for a populated owner property.

        Pinned because it is the whole justification for omitting a leaf: if a
        ``MethodNode`` owned an implementation leaf with an empty ``body``, the
        text would have nowhere to ride and the rule would lose it.
        """
        flat = indexed.graph._flat_index()
        for key in inlined_implementation_keys(indexed.graph):
            owner = next(
                entry for entry in flat.values()
                for relation_type, target_key, _type in entry.references
                if relation_type == "HAS_IMPLEMENTATION" and target_key == key
            )
            assert getattr(owner.node, "body", ""), (
                f"{LayerGraph._node_key(owner.node)} inlines an implementation "
                "leaf but carries no body"
            )

    def test_every_method_implementation_leaf_matches_its_body(self, indexed):
        """The leaf and the member body are one text, and coverage agrees.

        The parser reads a member's body from its ``body_file`` (an out-of-line
        definition lives in the ``.cpp``; ``template``/in-class members live in
        the header), so the two views cannot drift.  Every member with a body
        has a leaf, and every leaf carries that body verbatim.
        """
        flat = indexed.graph._flat_index()
        owner_of = {
            target_key: entry for entry in flat.values()
            for relation_type, target_key, _type in entry.references
            if relation_type == "HAS_IMPLEMENTATION"
        }
        leaves = {
            key: entry for key, entry in flat.items()
            if type(entry.node).__name__ == IMPLEMENTATION_TYPE
        }
        method_leaves = {
            key for key in leaves
            if type(owner_of[key].node).__name__ == "MethodNode"
        }
        methods_with_body = {
            key for key, entry in flat.items()
            if type(entry.node).__name__ == "MethodNode"
            and getattr(entry.node, "body", "")
        }

        assert len(method_leaves) == 48
        assert len(method_leaves) == len(methods_with_body), (
            "a method with a captured body has no implementation leaf, or vice "
            "versa: the two implementation paths disagree"
        )
        for key in method_leaves:
            owner = owner_of[key]
            assert leaves[key].node.implementation == owner.node.body, (
                f"{owner.node.qualified_name} leaf text is not its body"
            )

    def test_step_implementation_leaves_are_retained_as_carriers(self, snapshot, indexed):
        """A ``TestStepNode`` has no body property; its leaf is the only carrier.

        The flat layout keeps that leaf and its ``HAS_IMPLEMENTATION`` edge, so
        the test's source block survives.  This is the documented boundary of
        "do not serialize ``ImplementationNode`` leaves": the text must exist
        in exactly one place, and for a step that place is the leaf.
        """
        entries = {
            entry["canonical_key"]: entry
            for entry in snapshot["document"]["entries"]
        }
        inlined = inlined_implementation_keys(indexed.graph)
        carriers = {
            key for key, entry in entries.items()
            if entry["type"] == IMPLEMENTATION_TYPE
        }
        assert carriers, (
            "every implementation leaf was dropped, so the step source text "
            "has no carrier left"
        )
        assert not carriers & inlined

        flat = indexed.graph._flat_index()
        for key in carriers:
            owner = next(
                entry["canonical_key"] for entry in entries.values()
                if any(
                    edge["relation_type"] == "HAS_IMPLEMENTATION"
                    and edge["target_key"] == key
                    for edge in entry["edges"]
                )
            )
            owner_node = flat[owner].node
            assert not getattr(owner_node, "body", ""), (
                f"{owner} could carry its implementation text directly"
            )


# ---------------------------------------------------------------------------
# 5. Negative mutations are reported precisely
# ---------------------------------------------------------------------------


class TestNegativeMutations:
    """A single mutation must produce a single, precisely located report."""

    @pytest.fixture()
    def slice_(self, indexed):
        return build_transaction_slice(
            indexed.graph.serialize(fields="all", export_implementation=True)
        )

    def _drifts(self, snapshot, mutate) -> list[SnapshotDrift]:
        document = copy.deepcopy(snapshot["document"])
        mutate(document)
        restored = LayerGraph.deserialize(document)
        return compare_models(
            normalized_model(snapshot["restored"]), normalized_model(restored)
        )

    def test_changed_node_property_is_reported_precisely(
        self, snapshot, indexed, slice_
    ):
        method_key = slice_.method_key(next(iter(slice_.method_keys)))

        def mutate(document: dict) -> None:
            entry = next(
                entry for entry in document["entries"]
                if entry["canonical_key"] == method_key
            )
            entry["brief_description"] = "mutated"

        drifts = self._drifts(snapshot, mutate)

        assert [drift.kind for drift in drifts] == ["changed_property"]
        assert drifts[0].location == f"{method_key}.brief_description"
        assert drifts[0].actual == "mutated"

    def test_removed_edge_is_reported_precisely(self, snapshot, indexed, slice_):
        test_key = slice_.test_key(next(iter(slice_.test_keys)))
        removed = ("VERIFIES",)

        def mutate(document: dict) -> None:
            entry = next(
                entry for entry in document["entries"]
                if entry["canonical_key"] == test_key
            )
            before = [
                edge for edge in entry["edges"]
                if edge["relation_type"] in removed
            ]
            assert before, f"{test_key} carries no {removed[0]} edge"
            entry["edges"] = [
                edge for edge in entry["edges"]
                if edge["relation_type"] not in removed
            ]

        drifts = self._drifts(snapshot, mutate)

        assert {drift.kind for drift in drifts} == {"missing_edge"}
        assert {drift.location for drift in drifts} == {test_key}
        for drift in drifts:
            relation_type, target_key, target_type = drift.expected
            assert relation_type == "VERIFIES"
            assert target_key.startswith("cg:v1:"), target_key
            assert target_type in ("MethodNode", "ClassNode"), target_type
            assert drift.actual is None

    def test_missing_node_is_reported_precisely(self, snapshot, indexed, slice_):
        method_key = slice_.method_key(sorted(slice_.method_keys)[-1])

        def mutate(document: dict) -> None:
            document["entries"] = [
                entry for entry in document["entries"]
                if entry["canonical_key"] != method_key
            ]

        drifts = self._drifts(snapshot, mutate)

        assert ("missing_node", method_key, "MethodNode", None) in [
            (drift.kind, drift.location, drift.expected, drift.actual)
            for drift in drifts
        ], [drift.describe() for drift in drifts]

    def test_reversed_edge_is_reported_precisely(self, snapshot, indexed, slice_):
        """Flipping one edge's direction is two precise reports, not a wash.

        Same pair of nodes, same attributes, only the direction differs: a
        comparison that treated a relationship as an unordered pair of keys — or
        counted edges per pair — would call this unchanged.
        """
        test_key = slice_.test_key("TransactionCommit")
        method_key = next(
            key
            for key in sorted(slice_.verifies_targets["TransactionCommit"])
            if key in set(slice_.method_keys.values())
        )
        assert not any(
            edge["relation_type"] == "VERIFIES"
            and edge.get("target_key") == test_key
            for entry in snapshot["document"]["entries"]
            if entry["canonical_key"] == method_key
            for edge in entry["edges"]
        ), "the reversed edge already exists, so the mutation proves nothing"

        def mutate(document: dict) -> None:
            for entry in document["entries"]:
                if entry["canonical_key"] == test_key:
                    entry["edges"] = [
                        edge for edge in entry["edges"]
                        if not (edge["relation_type"] == "VERIFIES"
                                and edge.get("target_key") == method_key)
                    ]
                elif entry["canonical_key"] == method_key:
                    entry["edges"] = list(entry["edges"]) + [{
                        "relation_type": "VERIFIES",
                        "target_key": test_key,
                        "target_type": "TestNode",
                    }]

        drifts = self._drifts(snapshot, mutate)

        assert {drift.kind for drift in drifts} == {"missing_edge", "extra_edge"}, [
            drift.describe() for drift in drifts
        ]
        assert {drift.location for drift in drifts} == {test_key, method_key}
        lost = [d for d in drifts if d.kind == "missing_edge"]
        gained = [d for d in drifts if d.kind == "extra_edge"]
        assert len(lost) == len(gained) == 1
        assert lost[0].expected[:2] == ("VERIFIES", method_key)
        assert gained[0].actual[:2] == ("VERIFIES", test_key)

    def test_unexpected_extra_edge_is_reported_precisely(self, snapshot, indexed, slice_):
        """An edge nobody asked for shows up at its own source, once."""
        test_key = slice_.test_key("TransactionRollback")
        method_key = next(
            key
            for key in sorted(slice_.method_keys.values())
            if key not in slice_.verifies_targets["TransactionRollback"]
        )

        def mutate(document: dict) -> None:
            for entry in document["entries"]:
                if entry["canonical_key"] == test_key:
                    entry["edges"] = list(entry["edges"]) + [{
                        "relation_type": "VERIFIES",
                        "target_key": method_key,
                        "target_type": "MethodNode",
                    }]

        drifts = self._drifts(snapshot, mutate)

        assert [drift.kind for drift in drifts] == ["extra_edge"], [
            drift.describe() for drift in drifts
        ]
        assert drifts[0].location == test_key
        assert drifts[0].actual == ("VERIFIES", method_key, "MethodNode")
        assert drifts[0].expected is None


# ---------------------------------------------------------------------------
# 6. Empty-backend persistence — WP5.5 steps 5-7
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", params=BACKEND_KINDS)
def persisted(request, tmp_path_factory, snapshot):
    """A brand-new backend of each kind, holding exactly the slice document.

    The database is created here and written once, so every assertion below is
    about a backend that was empty until the flat document was loaded into it,
    and is afterwards reached only through repository APIs.
    """
    kind = request.param
    backend = create_backend(
        kind, tmp_path=tmp_path_factory.mktemp(f"wp55-{kind}")
    )
    require_contract(backend)
    request.addfinalizer(backend.close)
    empty_before = backend.graph.count_all_nodes()

    backend.bulk_save(snapshot["restored"])

    keys = [entry["canonical_key"] for entry in snapshot["document"]["entries"]]
    loaded = graph_from_backend(backend, keys)
    return {
        "kind": kind,
        "backend": backend,
        "keys": keys,
        "empty_before": empty_before,
        "loaded": loaded,
        "model": normalized_model(loaded),
        "edges": edge_report(backend, keys),
    }


def carried_edges(document: Mapping) -> dict[str, dict[tuple, dict]]:
    """The subset of :func:`document_edges` a backend is able to hold.

    A relationship needs two stored endpoints, so an edge whose far end is named
    by a bare ``target_ref`` — an ``#include`` path outside this graph, marked
    ``local: false`` — has no edge in any backend.  Callers compare against this
    map and then account for what it excludes, instead of letting "no such edge"
    pass for a relationship that really was dropped.
    """
    return {
        key: {
            edge: attrs for edge, attrs in edges.items() if edge[3] == "target_key"
        }
        for key, edges in document_edges(document).items()
    }


def outside_endpoints(document: Mapping) -> dict[str, list[str]]:
    """``{source_key: [drift line, ...]}`` for edges with a ``target_ref`` only.

    The lines are formatted exactly as :func:`_edge_drifts` formats a
    ``missing_edge``, so a test can assert that the endpoints outside the graph
    are *precisely* the ones a backend does not report.
    """
    stated = document_edges(document)
    return {
        key: sorted(f"missing_edge: {key} {edge}" for edge in edges)
        for key, edges in (
            (k, {e for e, _attrs in v.items() if e[3] == "target_ref"})
            for k, v in stated.items()
        )
        if edges
    }


def _edge_drifts(expected, actual) -> list[str]:
    """Precise edge-set differences between two ``edge_report``-shaped maps."""
    drifts: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        want = expected.get(key, {})
        got = actual.get(key, {})
        for edge in sorted(set(want) - set(got)):
            drifts.append(f"missing_edge: {key} {edge}")
        for edge in sorted(set(got) - set(want)):
            drifts.append(f"extra_edge: {key} {edge}")
        for edge in sorted(set(want) & set(got)):
            if want[edge] != got[edge]:
                drifts.append(
                    f"changed_edge_attributes: {key} {edge}: "
                    f"{want[edge]!r} -> {got[edge]!r}"
                )
    return drifts


class TestEmptyBackendPersistence:
    """The document persisted into an empty backend reads back identical."""

    def test_the_persistence_target_started_empty(self, persisted):
        assert persisted["empty_before"] == 0, (
            "the WP5.5 gate has to write into a backend that was empty first"
        )

    def test_every_document_node_is_fetched_by_canonical_key(self, persisted):
        backend = persisted["backend"]
        missing = [
            key for key in persisted["keys"]
            if backend.graph.find_by_key(key) is None
        ]
        assert missing == []

    def test_the_backend_holds_exactly_the_document_nodes(self, persisted):
        document = set(persisted["keys"])
        stored = stored_keys(persisted["backend"])

        assert sorted(document - stored) == []
        assert sorted(stored - document) == []
        # Nothing hides outside the tags the slice is spread over.
        assert persisted["backend"].graph.count_all_nodes() == len(stored)

    def test_every_node_keeps_its_canonical_key_and_class(self, persisted, snapshot):
        backend = persisted["backend"]
        drifts = []
        for entry in snapshot["document"]["entries"]:
            key = entry["canonical_key"]
            node = backend.graph.find_by_key(key)
            if node is None:  # pragma: no cover - covered by the test above
                drifts.append(f"missing_node: {key}")
                continue
            if node.canonical_key != key:
                drifts.append(f"changed_canonical_key: {key} -> {node.canonical_key}")
            if type(node).__name__ != document_entry_type(entry):
                drifts.append(
                    f"changed_node_type: {key}: "
                    f"{document_entry_type(entry)} -> {type(node).__name__}"
                )
        assert drifts == []

    def test_the_backend_reports_every_document_edge_verbatim(
        self, persisted, snapshot
    ):
        """Every relationship, with its attributes, including the transport ones.

        The normalized model deliberately reads ``COMPOSES`` as nesting and
        ``HAS_IMPLEMENTATION`` as inlining; this comparison asks the backend for
        its outgoing edges exactly as it stored them, so a relationship cannot
        survive normalization and still be missing from the database.
        """
        stated = document_edges(snapshot["document"])
        # Two endpoint kinds, classified from the document rather than guessed
        # from what the backend happens to return: see ``carried_edges``.  A
        # ``target_key`` names a node the document holds; a bare ``target_ref``
        # names something outside it that no node of this graph denotes.
        drifts = _edge_drifts(
            carried_edges(snapshot["document"]), persisted["edges"]
        )
        assert drifts == [], "\n".join(drifts[:40])

        # Read against the *whole* document, the only differences left are the
        # outside endpoints — the backend lacks exactly those and nothing else.
        outside = outside_endpoints(snapshot["document"])
        whole = _edge_drifts(stated, persisted["edges"])
        assert sorted(whole) == sorted(
            line for value in outside.values() for line in value
        ), "\n".join(sorted(whole)[:40])

    def test_bulk_save_stores_no_property_the_document_did_not_state(
        self, persisted, snapshot
    ):
        """Transport must not invent values for derived properties.

        ``qualified_name`` is computed from a node's own fields by the
        interactive ``save()`` path (a ``FileNode`` uses its ``path``, a
        ``ParameterNode`` its name).  The bulk path writes a document, so the
        value the document states is the value that gets stored — otherwise a
        backend would hold a property no document carried, and the same document
        would land differently depending on which backend received it.
        """
        stated = {
            entry["canonical_key"]: entry.get("qualified_name", "<absent>")
            for entry in snapshot["document"]["entries"]
        }
        derived = sorted(
            key for key, value in stated.items()
            if persisted["model"].get(key, {}).get("properties", {}).get(
                "qualified_name", "<absent>"
            ) != value
        )
        assert derived == [], derived[:10]

    def test_the_backend_model_matches_the_deserialized_model(self, persisted, snapshot):
        drifts = compare_models(
            normalized_model(snapshot["restored"]), persisted["model"]
        )
        assert drifts == [], "\n".join(drift.describe() for drift in drifts[:40])

    def test_the_backend_model_matches_the_source_graph(self, persisted, indexed):
        """The whole chain in one comparison: indexed ≡ document ≡ backend."""
        drifts = compare_models(normalized_model(indexed.graph), persisted["model"])
        assert drifts == [], "\n".join(drift.describe() for drift in drifts[:40])

    def test_the_backend_graph_has_no_unresolved_internal_edge(self, persisted):
        """The gate may not pass with an edge that points at nothing."""
        flat = persisted["loaded"]._flat_index()
        unresolved = [
            f"{LayerGraph._node_key(entry.node)} -[{relation}]-> {target_key}"
            for entry in persisted["loaded"]._all_entries()
            for relation, target_key, _type in entry.references
            if target_key not in flat
        ]
        assert unresolved == []


class TestPersistenceCoverageIsNotVacuous:
    """The comparison has to be shown to cover what it claims to cover."""

    def test_durable_properties_matches_serialize_for_every_node(self, persisted, indexed):
        """``durable_properties`` may not quietly drop what ``serialize`` emits."""
        nodes = [
            entry.node for entry in indexed.graph._all_entries()
        ] + [
            entry.node for entry in persisted["loaded"]._all_entries()
        ]
        assert nodes
        drifts = [
            (
                LayerGraph._node_key(node),
                sorted(set(via_serialize) - set(via_helper)),
                sorted(set(via_helper) - set(via_serialize)),
            )
            for node in nodes
            for via_serialize in [
                {
                    name: value
                    for name, value in node.serialize(fields="all").items()
                    if name != "edges"
                }
            ]
            for via_helper in [durable_properties(node)]
            if via_serialize != via_helper
        ]
        assert drifts == [], drifts[:10]

    def test_the_backend_model_covers_every_declared_property(self, persisted):
        """Per node class, the compared property set is the declared property set."""
        from codegraph.models.descriptors import PropertyRegistry

        declared: dict[str, set[str]] = {}
        compared: dict[str, set[str]] = {}
        for key, entry in persisted["model"].items():
            node_type = entry["type"]
            node = persisted["loaded"]._flat_index()[key].node
            discriminator = (
                "node_type" if "type" in PropertyRegistry.properties_of(type(node))
                else "type"
            )
            declared.setdefault(node_type, set()).update(
                PropertyRegistry.properties_of(type(node))
            )
            declared[node_type] |= {discriminator, "canonical_key"}
            compared.setdefault(node_type, set()).update(entry["properties"])

        assert compared.keys() == declared.keys()
        missing = {
            node_type: sorted(declared[node_type] - compared[node_type])
            for node_type in declared
            if declared[node_type] - compared[node_type]
        }
        assert missing == {}, missing

    def test_no_node_is_normalized_away_on_either_side(self, persisted, snapshot):
        """A bijection over 560-odd nodes must not start by dropping nodes."""
        assert inlined_implementation_keys(snapshot["restored"]) == set(), (
            "the deserialized document no longer carries every implementation "
            "leaf, so the backend comparison would be comparing less than the "
            "document holds"
        )
        assert inlined_implementation_keys(persisted["loaded"]) == set()
        assert len(persisted["model"]) == len(snapshot["document"]["entries"])


# ---------------------------------------------------------------------------
# 7. A second load is a no-op — WP5.5 step 9
# ---------------------------------------------------------------------------


class TestSecondLoadIdempotence:
    """Loading the same document twice must not double anything."""

    @pytest.fixture(params=BACKEND_KINDS)
    def twice(self, request, tmp_path_factory, snapshot):
        kind = request.param
        backend = create_backend(
            kind, tmp_path=tmp_path_factory.mktemp(f"wp55-twice-{kind}")
        )
        require_contract(backend)
        keys = [
            entry["canonical_key"] for entry in snapshot["document"]["entries"]
        ]
        rel_types = sorted(PORTABLE_RELATIONS | {"COMPOSES", "HAS_IMPLEMENTATION"})

        def read() -> dict:
            return {
                "nodes": backend.graph.count_all_nodes(),
                "keys": sorted(stored_keys(backend)),
                "counts": relationship_counts(backend, rel_types),
                "model": normalized_model(
                    graph_from_backend(backend, keys)
                ),
                "edges": edge_report(backend, keys),
            }

        backend.bulk_save(snapshot["restored"])
        first = read()
        backend.bulk_save(snapshot["restored"])
        second = read()
        yield {"backend": backend, "first": first, "second": second, "kind": kind}
        backend.close()

    def test_the_second_load_adds_no_nodes(self, twice):
        assert twice["second"]["nodes"] == twice["first"]["nodes"]
        assert twice["second"]["keys"] == twice["first"]["keys"]

    def test_the_second_load_adds_no_relationships(self, twice):
        grew = {
            rel_type: (twice["first"]["counts"][rel_type], twice["second"]["counts"][rel_type])
            for rel_type in twice["first"]["counts"]
            if twice["second"]["counts"][rel_type] != twice["first"]["counts"][rel_type]
        }
        assert grew == {}, grew
        assert sum(twice["second"]["counts"].values()) == sum(
            twice["first"]["counts"].values()
        )

    def test_the_second_load_changes_no_property(self, twice):
        drifts = compare_models(twice["first"]["model"], twice["second"]["model"])
        assert drifts == [], "\n".join(drift.describe() for drift in drifts[:40])

    def test_the_second_load_changes_no_edge_or_its_attributes(self, twice):
        assert _edge_drifts(twice["first"]["edges"], twice["second"]["edges"]) == []


# ---------------------------------------------------------------------------
# 8. Mutations are caught at the backend boundary — WP5.5 step 10
# ---------------------------------------------------------------------------


class TestBackendNegativeMutations:
    """A backend read has to notice a wrong document, not average it away."""

    @pytest.fixture(params=BACKEND_KINDS)
    def backend_(self, request, tmp_path_factory, snapshot):
        backend = create_backend(
            request.param,
            tmp_path=tmp_path_factory.mktemp(f"wp55-negative-{request.param}"),
        )
        require_contract(backend)
        yield backend
        backend.close()

    @pytest.fixture()
    def slice_(self, indexed):
        return build_transaction_slice(
            indexed.graph.serialize(fields="all", export_implementation=True)
        )

    def _persist(self, backend, snapshot, mutate=None) -> dict:
        document = copy.deepcopy(snapshot["document"])
        if mutate is not None:
            mutate(document)
        backend.bulk_save(LayerGraph.deserialize(document))
        keys = [entry["canonical_key"] for entry in document["entries"]]
        return {
            "document": document,
            "keys": keys,
            "expected": carried_edges(document),
            "actual": edge_report(backend, keys),
            "stored": stored_keys(backend),
        }

    def test_a_reversed_edge_is_reported_at_the_backend_boundary(
        self, backend_, snapshot, slice_
    ):
        """A flipped edge must still be flipped after it has been stored.

        The backend is compared with the pristine slice, not with the mutated
        document it was handed: persisting a wrong document faithfully proves
        nothing, and the difference is what the gate has to catch.
        """
        test_key = slice_.test_key("NestedTransactionWithSavepoints")
        method_key = next(
            key
            for key in sorted(slice_.verifies_targets["NestedTransactionWithSavepoints"])
            if key in set(slice_.method_keys.values())
        )

        def mutate(document: dict) -> None:
            for entry in document["entries"]:
                if entry["canonical_key"] == test_key:
                    entry["edges"] = [
                        edge for edge in entry["edges"]
                        if not (edge["relation_type"] == "VERIFIES"
                                and edge.get("target_key") == method_key)
                    ]
                elif entry["canonical_key"] == method_key:
                    entry["edges"] = list(entry["edges"]) + [{
                        "relation_type": "VERIFIES",
                        "target_key": test_key,
                        "target_type": "TestNode",
                    }]

        state = self._persist(backend_, snapshot, mutate)

        # The backend faithfully stored the mutated document, so the flip is
        # only visible against the pristine slice — which is the point: a
        # reversed edge has to survive as a *difference*, not as a pair of edges
        # that a lenient comparison reads as the same thing.
        drifts = _edge_drifts(
            carried_edges(snapshot["document"]), state["actual"]
        )

        missing = [line for line in drifts if line.startswith("missing_edge:")]
        extra = [line for line in drifts if line.startswith("extra_edge:")]
        assert len(drifts) == 2 and len(missing) == len(extra) == 1, drifts
        assert test_key in missing[0] and f"{method_key!r}" in missing[0]
        assert method_key in extra[0] and f"{test_key!r}" in extra[0]
        # Direction is the only difference: same two nodes, same relation.
        assert "'VERIFIES'" in missing[0] and "'VERIFIES'" in extra[0]

    def test_an_unexpected_extra_edge_is_reported_at_the_backend_boundary(
        self, backend_, snapshot, slice_
    ):
        """An edge nobody authored is reported once, at its own source node."""
        test_key = slice_.test_key("TransactionAutoRollbackOnDestruction")
        method_key = next(
            key for key in sorted(slice_.method_keys.values())
            if key not in slice_.verifies_targets["TransactionAutoRollbackOnDestruction"]
        )

        def mutate(document: dict) -> None:
            for entry in document["entries"]:
                if entry["canonical_key"] == test_key:
                    entry["edges"] = list(entry["edges"]) + [{
                        "relation_type": "VERIFIES",
                        "target_key": method_key,
                        "target_type": "MethodNode",
                    }]

        result = self._persist(backend_, snapshot, mutate)
        drifts = _edge_drifts(result["expected"], result["actual"])

        assert drifts == [], drifts  # the backend kept what the document said …
        # … so the difference has to be against the *unmutated* slice.
        honest = _edge_drifts(
            carried_edges(snapshot["document"]), result["actual"]
        )
        assert len(honest) == 1, honest
        assert honest[0].startswith("extra_edge:") and test_key in honest[0]
        assert f"{method_key}" in honest[0]

    def test_an_extra_edge_written_straight_into_the_backend_is_detected(
        self, backend_, snapshot, slice_
    ):
        """The read path itself must notice an edge no document carried."""
        state = self._persist(backend_, snapshot)
        test_key = slice_.test_key("TransactionRollback")
        method_key = next(
            key for key in sorted(slice_.method_keys.values())
            if key not in slice_.verifies_targets["TransactionRollback"]
        )
        source = backend_.graph.find_by_key(test_key)
        target = backend_.graph.find_by_key(method_key)
        assert source is not None and target is not None
        assert ("VERIFIES", method_key, "MethodNode", "target_key") not in (
            state["expected"][test_key]
        )

        backend_.connect(source, "VERIFIES", target)

        drifts = _edge_drifts(
            state["expected"], edge_report(backend_, state["keys"])
        )
        assert len(drifts) == 1, drifts
        assert drifts[0].startswith("extra_edge:") and test_key in drifts[0]

    def test_a_missing_node_is_reported_at_the_backend_boundary(
        self, backend_, snapshot, slice_
    ):
        """A dropped node is reported as the node, with its edges accounted."""
        method_key = slice_.method_key("commit")

        def mutate(document: dict) -> None:
            document["entries"] = [
                entry for entry in document["entries"]
                if entry["canonical_key"] != method_key
            ]

        state = self._persist(backend_, snapshot, mutate)
        document_keys = {
            entry["canonical_key"] for entry in snapshot["document"]["entries"]
        }

        # The backend holds exactly the (shorter) document it was given, and the
        # node that vanished from the document is the one it is missing relative
        # to the slice.
        assert state["stored"] == set(state["keys"])
        assert document_keys - state["stored"] == {method_key}
        assert state["stored"] - document_keys == set()

        # What the backend does not report is fully explained by the mutation:
        # the endpoints outside the graph, plus the edges that named the node
        # that was removed.  Anything else missing would be an unaccounted loss.
        stated = document_edges(state["document"])
        unexplained = _edge_drifts(stated, state["actual"])
        accounted = sorted(
            f"missing_edge: {key} {edge}"
            for key, edges in stated.items()
            for edge in edges
            if edge[3] == "target_ref" or edge[1] == method_key
        )
        assert sorted(unexplained) == accounted, "\n".join(
            sorted(set(unexplained) - set(accounted))[:20]
        )
        assert any("COMPOSES" in line for line in accounted), (
            "removing the node should have left its composition edge dangling; "
            "if it did not, the mutation did not touch a composed member"
        )
        # … and against the real slice the loss is reported at the node.
        model = normalized_model(
            graph_from_backend(backend_, state["keys"])
        )
        drifts = compare_models(normalized_model(snapshot["restored"]), model)
        missing = [d for d in drifts if d.kind == "missing_node"]
        assert [d.location for d in missing] == [method_key], drifts

    def test_a_changed_property_is_reported_at_the_backend_boundary(
        self, backend_, snapshot, slice_
    ):
        """A property rewritten on the way in is reported at node.property."""
        method_key = slice_.method_key("rollback")

        def mutate(document: dict) -> None:
            for entry in document["entries"]:
                if entry["canonical_key"] == method_key:
                    entry["brief_description"] = "mutated after review"

        state = self._persist(backend_, snapshot, mutate)
        model = normalized_model(graph_from_backend(backend_, state["keys"]))

        drifts = compare_models(normalized_model(snapshot["restored"]), model)
        assert [drift.kind for drift in drifts] == ["changed_property"], drifts
        assert drifts[0].location == f"{method_key}.brief_description"
        assert drifts[0].actual == "mutated after review"


# ---------------------------------------------------------------------------
# 9. Neo4j parity — opt-in and separately marked (WP5.5 step 8)
# ---------------------------------------------------------------------------

#: Explicit opt-in.  The parity leg writes to a database, so it never runs
#: implicitly against whatever backend the developer has configured.
NEO4J_PARITY_ENV = "CODEGRAPH_NEO4J_PARITY"


def _neo4j_parity_backend():
    """A reachable, empty Neo4j to compare against, or a skip with instructions."""
    import os

    if os.environ.get(NEO4J_PARITY_ENV) != "1":
        pytest.skip(
            f"Neo4j parity is opt-in: set {NEO4J_PARITY_ENV}=1 with a fresh "
            "test container (tests/docker-compose.yml) running"
        )
    backend = create_backend(NEO4J_KIND)
    require_contract(backend)
    if backend.graph.count_all_nodes() != 0:
        pytest.fail(
            "the Neo4j parity target is not empty. This package never clears a "
            "persistent graph, so start a throwaway container "
            "(tests/docker-compose.yml) and point CODEGRAPH_NEO4J_* at it."
        )
    return backend


@pytest.mark.neo4j
class TestNeo4jParity:
    """The same bijection against Neo4j.  Opt-in, never run by the default gate."""

    def test_neo4j_holds_the_slice_exactly(self, snapshot, indexed):
        backend = _neo4j_parity_backend()
        try:
            keys = [
                entry["canonical_key"]
                for entry in snapshot["document"]["entries"]
            ]
            backend.bulk_save(snapshot["restored"])

            assert stored_keys(backend) == set(keys)
            model = normalized_model(graph_from_backend(backend, keys))
            drifts = compare_models(normalized_model(snapshot["restored"]), model)
            assert drifts == [], "\n".join(d.describe() for d in drifts[:40])

            # Idempotence, as on every other backend.
            backend.bulk_save(snapshot["restored"])
            again = normalized_model(graph_from_backend(backend, keys))
            assert compare_models(model, again) == []
        finally:
            backend.close()

