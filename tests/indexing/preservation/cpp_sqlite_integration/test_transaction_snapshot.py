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
#: about — fails this module instead of being ignored.
PORTABLE_RELATIONS = frozenset({
    "CALLEE", "CONSTRAINS", "DEFINED_IN", "DEPENDS_ON", "ENFORCES_CONCEPT",
    "HAS_PARAMETER", "INCLUDES", "INHERITS_FROM", "INVOKES", "REALIZED_BY",
    "SPECIALIZES", "VERIFIED_BY", "VERIFIES",
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


def normalized_model(graph: LayerGraph) -> dict[str, dict]:
    """The durable, layout-independent model of *graph*.

    The flat layout's documented exclusions are applied on both sides so the
    indexed graph and the deserialized graph are comparable: transport
    relations are dropped, ``COMPOSES`` becomes the child's ``composed_by``
    tuple, and inlined implementation leaves are removed.  Nothing else is
    filtered — every remaining property of every remaining node participates.
    """
    inlined = inlined_implementation_keys(graph)

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
        properties = entry.node.serialize(fields="all")
        properties.pop("edges", None)
        edges: dict[tuple[str, str, str], dict] = {}
        for relation_type, target_key, target_type in entry.references:
            if relation_type in EXCLUDED_RELATIONS:
                continue
            assert relation_type in PORTABLE_RELATIONS, (
                f"{key} has unclassified relation {relation_type!r}: classify "
                "it as portable, or record why the flat layout drops it"
            )
            edges[(relation_type, target_key, target_type)] = dict(
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
    return transaction_slice_index


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
        assert len(every_key - emitted) == 43, (
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
