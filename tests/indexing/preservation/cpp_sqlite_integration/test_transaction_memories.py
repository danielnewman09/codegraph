"""WP5.3 — the three Transaction memories.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

The slice carries the reviewed design rationale for the frozen Transaction
implementation surface: the RAII ownership decision, the no-throw cleanup
constraint, and the savepoint-nesting rationale.  This module proves that

1. the authored input is the frozen set, grounded in the reviewed sources,
   with links to exactly the class plus the twelve frozen members — never a
   requirement, a test, an evidence record, or a drift finding;
2. materialization uses the existing memory node types and the framework's
   canonical identity (no authored key, no second identity system);
3. the memories are ordinary entries of the *same* ``LayerGraph`` the code
   slice uses, so requirement, code, test and memory edges travel in one flat
   document;
4. every memory-to-code and memory-to-memory edge, and every memory property,
   survives the in-memory flat round trip without a backend lookup.

The historical expectation that *deserialized memory edges disappear* belongs
to ``MemoryGraph``'s own scalar ``linked_code_*`` format, which
``tests/integration/memory/graph/test_memory_graph.py`` pins.  WP5.3 does not
use that format and deliberately leaves that code path alone: the flat
LayerGraph document carries memory edges like any other edge, which is what
this module asserts.
"""

from __future__ import annotations

import copy
import json
from collections import Counter

import pytest

from codegraph.graph import LayerGraph

from .artifacts import CODEGRAPH_ROOT
from .transaction_memories import (
    FROZEN_MEMORY_TYPES,
    MEMORY_KINDS,
    SLICE_KEY_PREFIX,
    SLICE_SCOPE,
    iter_entries,
    load_memory_definitions,
    materialize_memories,
    slice_graph_with_memories,
)
from .transaction_slice import (
    TRANSACTION_CLASS_QN,
    TRANSACTION_HEADER,
    TRANSACTION_METHOD_QNS,
    TRANSACTION_SOURCE,
)

#: Serialized ``type`` of every memory node.
MEMORY_CLASS_NAMES = frozenset({"DecisionNode", "ConstraintNode", "RationaleNode"})

#: The reviewed sources the memories describe (the header declares the
#: surface, the source holds the out-of-line bodies).
REVIEWED_SOURCES = (TRANSACTION_HEADER, TRANSACTION_SOURCE)

#: Literals each memory must be *grounded* in: every token has to appear both
#: in the authored content and in the reviewed sources.  This is what makes a
#: fabricated or drifted memory fail here instead of shipping as plausible
#: prose.
GROUNDING_TOKENS = {
    "decision": ("= delete", "db_ = nullptr", "isActive_", "rollback()"),
    "constraint": ("noexcept", "catch (...)", "swallow"),
    "rationale": (
        "sqlite3_get_autocommit", "SAVEPOINT", "ROLLBACK TO SAVEPOINT",
        "RELEASE SAVEPOINT", "sp_",
    ),
}

#: The member surface each memory explains, by frozen label.  Frozen
#: independently of the input document so a silently dropped or added link
#: fails here.
EXPECTED_LINKS = {
    "decision": (
        TRANSACTION_CLASS_QN,
        TRANSACTION_METHOD_QNS["constructor"],
        TRANSACTION_METHOD_QNS["destructor"],
        TRANSACTION_METHOD_QNS["is_active"],
        TRANSACTION_METHOD_QNS["move_constructor"],
        TRANSACTION_METHOD_QNS["move_assignment"],
        TRANSACTION_METHOD_QNS["copy_constructor_deleted"],
        TRANSACTION_METHOD_QNS["copy_assignment_deleted"],
    ),
    "constraint": (
        TRANSACTION_CLASS_QN,
        TRANSACTION_METHOD_QNS["destructor"],
        TRANSACTION_METHOD_QNS["move_constructor"],
        TRANSACTION_METHOD_QNS["move_assignment"],
    ),
    "rationale": (
        TRANSACTION_METHOD_QNS["constructor"],
        TRANSACTION_METHOD_QNS["commit"],
        TRANSACTION_METHOD_QNS["rollback"],
        TRANSACTION_METHOD_QNS["execute_sql"],
        TRANSACTION_METHOD_QNS["is_savepoint"],
        TRANSACTION_METHOD_QNS["get_savepoint_name"],
    ),
}

RAII = "memory::cpp-sqlite-transaction-raii-ownership"
NO_THROW = "memory::cpp-sqlite-transaction-no-throw-cleanup"
SAVEPOINTS = "memory::cpp-sqlite-transaction-savepoint-nesting"

#: Frozen confidence per memory.  A non-default value proves the field
#: survives serialization instead of being re-defaulted on import.
EXPECTED_CONFIDENCE = {RAII: 1.0, NO_THROW: 1.0, SAVEPOINTS: 0.9}

#: Relation type each memory type must use towards code.
EXPECTED_RELATION = {
    "decision": "MOTIVATES",
    "constraint": "CONSTRAINS",
    "rationale": "EXPLAINS",
}

#: Expected outgoing edge count per memory (code links plus the REFINES edge).
EXPECTED_LINK_COUNTS = {
    "decision": 8,
    "constraint": 4,
    "rationale": 6 + 1,
}


# ---------------------------------------------------------------------------
# Fixtures — one augmentation of the shared session index run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def indexed(transaction_slice_index):
    return transaction_slice_index


@pytest.fixture(scope="module")
def definitions():
    return load_memory_definitions()


@pytest.fixture(scope="module")
def augmented(indexed, definitions) -> LayerGraph:
    """The slice graph plus the materialized memories."""
    return slice_graph_with_memories(indexed.graph, definitions)


@pytest.fixture(scope="module")
def document_chain(augmented) -> dict:
    """The flat document and its backend-free re-import."""
    document = augmented.serialize(
        fields="all", document=True, layout="flat", export_implementation=True,
    )
    return {
        "document": document,
        "restored": LayerGraph.deserialize(copy.deepcopy(document)),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _document_bytes(document) -> str:
    return json.dumps(document, indent=2, sort_keys=True, default=str)


def _flat_document(graph: LayerGraph) -> dict:
    return graph.serialize(
        fields="all", document=True, layout="flat", export_implementation=True,
    )


def _memory_entries(document) -> dict[str, dict]:
    """``{qualified_name: entry}`` for the memory records of a document."""
    return {
        entry["qualified_name"]: entry
        for entry in document["entries"]
        if entry["type"] in MEMORY_CLASS_NAMES
    }


def _memory_nodes(graph: LayerGraph) -> dict[str, object]:
    """``{qualified_name: node}`` for the memory entries of a graph."""
    return {
        entry.node.qualified_name: entry.node
        for entry in iter_entries(graph)
        if type(entry.node).__name__ in MEMORY_CLASS_NAMES
    }


def _properties(node) -> dict:
    """A node's portable properties, without its edge list."""
    data = node.serialize(fields="all")
    data.pop("edges", None)
    return data


def _entry_of(graph: LayerGraph, qualified_name: str):
    for entry in iter_entries(graph):
        if entry.node.qualified_name == qualified_name:
            return entry
    raise AssertionError(f"no entry for {qualified_name!r}")


def _source_text(relative_path: str) -> str:
    path = CODEGRAPH_ROOT / relative_path
    assert path.is_file(), f"reviewed source is missing on disk: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The authored input
# ---------------------------------------------------------------------------


class TestAuthoredInput:
    def test_input_is_the_frozen_three_memories(self, definitions):
        assert tuple(d.type for d in definitions) == FROZEN_MEMORY_TYPES
        assert [d.qualified_name for d in definitions] == [
            RAII, NO_THROW, SAVEPOINTS,
        ]

    def test_every_memory_declares_the_documented_fields(self, definitions):
        for definition in definitions:
            assert definition.content.strip()
            assert len(definition.content) >= 400, definition.qualified_name
            assert 0.0 <= definition.confidence <= 1.0
            assert definition.tags == ("as-built",)
            assert definition.source == "cpp-sqlite"
            assert definition.links

    def test_content_is_grounded_in_the_reviewed_sources(self, definitions):
        """Every construct a memory names exists in the source it describes.

        A memory that quotes a construct the code does not contain fails here,
        so the prose cannot drift away from the implementation the slice
        freezes.
        """
        source_text = "\n".join(_source_text(p) for p in REVIEWED_SOURCES)
        for definition in definitions:
            tokens = GROUNDING_TOKENS[definition.type]
            assert tokens, definition.type
            for token in tokens:
                assert token in source_text, (
                    f"{definition.qualified_name}: {token!r} is not in the "
                    f"reviewed sources"
                )
                assert token in definition.content, (
                    f"{definition.qualified_name}: content does not cite "
                    f"{token!r}"
                )

    def test_links_are_exactly_the_class_and_the_twelve_members(
        self, definitions
    ):
        """The memory surface is exactly the frozen implementation surface.

        No requirement, test, evidence record, or drift finding is a memory
        target, and no frozen member is left without rationale.
        """
        frozen_surface = {TRANSACTION_CLASS_QN, *TRANSACTION_METHOD_QNS.values()}
        for definition in definitions:
            assert set(definition.links) == set(EXPECTED_LINKS[definition.type])
            assert set(definition.links) <= frozen_surface

        covered = {link for d in definitions for link in d.links}
        assert covered == frozen_surface
        assert len(covered) == 1 + len(TRANSACTION_METHOD_QNS)

    def test_memory_to_memory_edge_is_declared_by_the_data(self, definitions):
        assert {
            (d.type, field, target)
            for d in definitions for field, target in d.memory_links.items()
        } == {("rationale", "refines", RAII)}

    def test_confidence_is_authored_not_defaulted(self, definitions):
        assert {
            d.qualified_name: d.confidence for d in definitions
        } == EXPECTED_CONFIDENCE


# ---------------------------------------------------------------------------
# 2. Materialization — existing types, framework identity
# ---------------------------------------------------------------------------


class TestMaterialization:
    def test_materialized_nodes_carry_the_authored_fields_exactly(
        self, indexed, definitions
    ):
        """Exact content and endpoints: the node is the authored memory.

        No transformation, truncation, or re-derivation happens between the
        reviewed input and the graph, and nothing is invented on the way —
        the timestamps stay unset because the fixture is never saved.
        """
        entries, _edges = materialize_memories(definitions, indexed.graph)
        by_qname = {e.node.qualified_name: e.node for e in entries.values()}
        for definition in definitions:
            node = by_qname[definition.qualified_name]
            assert node.content == definition.content
            assert node.confidence == definition.confidence
            assert list(node.tags) == list(definition.tags)
            assert node.source == definition.source
            assert node.kind == "memory"
            assert type(node) is MEMORY_KINDS[definition.type][0]
            assert node.decided_at is None
            assert node.updated_at is None

    def test_nodes_use_the_existing_memory_types(self, indexed, definitions):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        assert len(entries) == 3
        assert {type(e.node).__name__ for e in entries.values()} == (
            MEMORY_CLASS_NAMES
        )

    def test_keys_are_computed_in_the_slice_scope(self, indexed, definitions):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        for key, entry in entries.items():
            assert key.startswith(SLICE_KEY_PREFIX), key
            # Recomputing from the node's own fields reproduces the stored key.
            assert entry.node.resolve_canonical_key(scope=SLICE_SCOPE) == key

    def test_keys_share_the_scope_of_the_indexed_slice(self, indexed, definitions):
        """The memories are not a parallel identity universe."""
        entries, _edges = materialize_memories(definitions, indexed.graph)
        class_keys = [
            entry.node.canonical_key
            for entry in iter_entries(indexed.graph)
            if type(entry.node).__name__ == "ClassNode"
        ]
        assert class_keys
        assert all(key.startswith(SLICE_KEY_PREFIX) for key in class_keys)
        assert all(key.startswith(SLICE_KEY_PREFIX) for key in entries)

    def test_every_code_edge_is_typed_and_resolves(self, indexed, definitions):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        by_qname = {
            entry.node.qualified_name: entry.node
            for entry in iter_entries(indexed.graph)
        }
        for definition in definitions:
            relation = EXPECTED_RELATION[definition.type]
            entry = next(
                e for e in entries.values()
                if e.node.qualified_name == definition.qualified_name
            )
            code_edges = {
                (rt, target_key, target_type)
                for rt, target_key, target_type in entry.references
                if rt != "REFINES"
            }
            assert code_edges == {
                (relation, by_qname[target].canonical_key,
                 type(by_qname[target]).__name__)
                for target in definition.links
            }, definition.qualified_name
            assert {rt for rt, _k, _t in code_edges} == {relation}
            assert relation == MEMORY_KINDS[definition.type][1]

    def test_code_targets_are_compound_and_member_nodes_only(
        self, indexed, definitions
    ):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        assert {
            target_type
            for entry in entries.values()
            for rt, _key, target_type in entry.references
            if rt != "REFINES"
        } == {"ClassNode", "MethodNode"}

    def test_refines_edge_has_exact_endpoints(self, indexed, definitions):
        entries, memory_edges = materialize_memories(definitions, indexed.graph)
        keys = {e.node.qualified_name: k for k, e in entries.items()}
        assert memory_edges == (("REFINES", keys[SAVEPOINTS], keys[RAII]),)


# ---------------------------------------------------------------------------
# 3. One graph, one snapshot format
# ---------------------------------------------------------------------------


class TestSharedGraph:
    def test_assembly_does_not_mutate_the_slice_graph(self, indexed, definitions):
        """The session-scoped slice graph is read-only here."""
        before_keys = set(indexed.graph._flat_index())
        before_known = set(indexed.graph.known_keys)

        augmented = slice_graph_with_memories(indexed.graph, definitions)

        memory_keys, _edges = materialize_memories(definitions, indexed.graph)
        assert set(indexed.graph._flat_index()) == before_keys
        assert set(indexed.graph.known_keys) == before_known
        assert set(augmented._flat_index()) == before_keys | set(memory_keys)

    def test_memories_join_the_same_layer_graph(self, indexed, definitions):
        augmented = slice_graph_with_memories(indexed.graph, definitions)
        assert augmented.tags == indexed.graph.tags
        assert set(indexed.graph.entries) <= set(augmented.entries)
        assert set(_memory_nodes(augmented)) == {RAII, NO_THROW, SAVEPOINTS}

    def test_document_carries_code_and_memory_edges_together(self, document_chain):
        """One snapshot format: requirements, code, tests and memories.

        The same flat document carries requirement, code and memory edges, so
        the memories are not a second, parallel document.
        """
        relations = Counter(
            edge["relation_type"]
            for entry in document_chain["document"]["entries"]
            for edge in entry.get("edges", ())
        )
        assert {"REALIZED_BY", "VERIFIES"} <= set(relations)
        assert {"MOTIVATES", "CONSTRAINS", "EXPLAINS", "REFINES"} <= set(
            relations
        )


# ---------------------------------------------------------------------------
# 4. Flat round trip
# ---------------------------------------------------------------------------


class TestFlatRoundTrip:
    def test_document_contains_every_memory(self, document_chain, definitions):
        assert set(_memory_entries(document_chain["document"])) == {
            d.qualified_name for d in definitions
        }

    def test_every_memory_edge_survives_export(self, indexed, definitions, document_chain):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        expected = Counter(
            (key, rt, target_key, target_type)
            for key, entry in entries.items()
            for rt, target_key, target_type in entry.references
        )
        found = Counter(
            (entry["canonical_key"], edge["relation_type"], edge["target_key"],
             edge["target_type"])
            for entry in document_chain["document"]["entries"]
            if entry["type"] in MEMORY_CLASS_NAMES
            for edge in entry.get("edges", ())
        )
        assert found == expected
        assert len(found) == sum(EXPECTED_LINK_COUNTS.values())

    def test_memory_properties_survive_re_import(self, indexed, definitions, document_chain):
        entries, _edges = materialize_memories(definitions, indexed.graph)
        source_nodes = {
            entry.node.qualified_name: entry.node for entry in entries.values()
        }
        restored_nodes = _memory_nodes(document_chain["restored"])
        assert set(restored_nodes) == set(source_nodes)
        for qualified_name, node in source_nodes.items():
            assert _properties(restored_nodes[qualified_name]) == _properties(node)
        assert type(restored_nodes[RAII]).__name__ == "DecisionNode"
        assert type(restored_nodes[NO_THROW]).__name__ == "ConstraintNode"
        assert type(restored_nodes[SAVEPOINTS]).__name__ == "RationaleNode"

    def test_memory_to_memory_edge_survives_re_import(self, document_chain):
        restored = document_chain["restored"]
        entry = _entry_of(restored, SAVEPOINTS)
        decision = _memory_nodes(restored)[RAII]
        assert (
            "REFINES", decision.canonical_key, "DecisionNode",
        ) in entry.references

    def test_memory_to_code_edges_survive_re_import(self, indexed, definitions, document_chain):
        restored = document_chain["restored"]
        by_qname = {
            entry.node.qualified_name: entry.node
            for entry in iter_entries(restored)
        }
        for definition in definitions:
            entry = _entry_of(restored, definition.qualified_name)
            relation = EXPECTED_RELATION[definition.type]
            assert {
                (rt, target_key)
                for rt, target_key, _target_type in entry.references
                if rt != "REFINES"
            } == {
                (relation, by_qname[target].canonical_key)
                for target in definition.links
            }
        # Every memory target is a node of the exported document.
        for definition in definitions:
            for target in definition.links:
                assert target in by_qname, target

    def test_re_import_needs_no_backend(self, document_chain, monkeypatch):
        """Deserialization is pure: no backend, no cache, no side effects."""
        import codegraph.graph as graph_module

        def _explode(*args, **kwargs):
            raise AssertionError("re-import touched a backend")

        for name in ("get_backend", "resolve_node", "resolve_reference"):
            if hasattr(graph_module, name):
                monkeypatch.setattr(graph_module, name, _explode)

        restored = LayerGraph.deserialize(
            copy.deepcopy(document_chain["document"])
        )
        assert _document_bytes(_flat_document(restored)) == _document_bytes(
            document_chain["document"]
        )

    def test_document_is_a_strict_fixpoint(self, document_chain):
        assert _document_bytes(_flat_document(document_chain["restored"])) == (
            _document_bytes(document_chain["document"])
        )

    def test_no_second_identity_system_in_the_document(self, document_chain):
        for entry in document_chain["document"]["entries"]:
            assert entry["canonical_key"].startswith("cg:v1:")
            for forbidden in ("uid", "refid", "target_uid"):
                assert forbidden not in entry
            for edge in entry.get("edges", ()):
                if "target_key" in edge:
                    assert edge["target_key"].startswith("cg:v1:"), edge
                else:
                    # An unresolved extraction endpoint; the flat layout keeps
                    # it explicit rather than inventing a canonical key.
                    assert "target_ref" in edge, edge

