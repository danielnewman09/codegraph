"""WP5.4 — model and capture of build/test execution evidence.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

Gate: a successful build record and a successful filtered-test record are
portable, linked to the exact class/tests, and their stored output digests
match the reviewed logs.

Ordinary runs of this module *validate* the committed evidence — they never
rebuild, rewrite timestamps, or access the network (plan step 6).  The only
supported re-capture path is ``scripts/capture_transaction_slice_evidence.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import replace as _replace

import pytest

from codegraph.graph import LayerGraph
from codegraph.models.evidence import ExecutionEvidenceNode

from .transaction_evidence import (
    BUILD_EVIDENCES_CLASS,
    EVIDENCE_INPUT,
    FROZEN_GTEST_FILTER,
    TEST_EVIDENCES_TESTS,
    EvidenceDefinition,
    EvidenceFixtureError,
    iter_evidence_nodes,
    load_evidence_definitions,
    log_digest,
    materialize_evidence,
    read_log,
    slice_graph_with_evidence,
)
from .transaction_memories import (
    SLICE_KEY_PREFIX,
    iter_entries,
    load_memory_definitions,
    slice_graph_with_memories,
)
from .transaction_slice import TEST_QNS

#: Golden gitlink recorded by the fixture provenance and embedded in every
#: evidence revision field by the capture script.
GOLDEN_REVISION = "4a1450a5e6a5b8edf7f3572b4eaa6085df37e571"

BUILD_QNAME = "evidence::cpp-sqlite::release-build"
TEST_QNAME = "evidence::cpp-sqlite::transaction-test-run"

#: Environment keys the capture must record — "environment" cannot decay
#: into an empty or decorative field.
REQUIRED_ENVIRONMENT_KEYS = ("platform", "compiler", "cmake", "conan",
                             "build_type")


# ---------------------------------------------------------------------------
# Fixtures — one augmentation of the shared session index run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def indexed(transaction_slice_index):
    return transaction_slice_index


@pytest.fixture(scope="module")
def definitions():
    return load_evidence_definitions()


@pytest.fixture(scope="module")
def slice_graph(indexed):
    """Code + tests + requirements, plus the WP5.3 memories.

    The evidence of the *tested* slice covers the same graph the memories
    describe, so it is materialized against the augmented graph — the same
    chain WP5.6's inspection report will assemble.
    """
    return slice_graph_with_memories(
        indexed.graph, load_memory_definitions()
    )


@pytest.fixture(scope="module")
def augmented(slice_graph, definitions) -> LayerGraph:
    """The slice graph plus the materialized evidence entries."""
    graph, _edges = slice_graph_with_evidence(slice_graph, definitions)
    return graph


@pytest.fixture(scope="module")
def evidence_edges(slice_graph, definitions):
    _graph, edges = slice_graph_with_evidence(slice_graph, definitions)
    return edges


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


def _evidence_entries(document) -> dict[str, dict]:
    return {
        entry["qualified_name"]: entry
        for entry in document["entries"]
        if entry["type"] == "ExecutionEvidenceNode"
    }


def _evidence_node(graph: LayerGraph, qualified_name: str) -> ExecutionEvidenceNode:
    for node in iter_evidence_nodes(graph):
        if node.qualified_name == qualified_name:
            return node
    raise AssertionError(f"no evidence node {qualified_name!r}")


def _properties(node) -> dict:
    """A node's portable properties, without its edge list."""
    data = node.serialize(fields="all")
    data.pop("edges", None)
    return data


def _definition(definitions, qualified_name: str) -> EvidenceDefinition:
    for definition in definitions:
        if definition.qualified_name == qualified_name:
            return definition
    raise AssertionError(f"no reviewed record {qualified_name!r}")


def _edges_of(graph: LayerGraph, qualified_name: str) -> set[tuple[str, str]]:
    """``{(relation_type, target_key)}`` outgoing from *qualified_name*."""
    for entry in iter_entries(graph):
        if entry.node.qualified_name == qualified_name:
            return {
                (relation, target)
                for relation, target, _type in entry.references
            }
    raise AssertionError(f"no entry for {qualified_name!r}")


def _key_of(graph: LayerGraph, qualified_name: str) -> str:
    for entry in iter_entries(graph):
        if entry.node.qualified_name == qualified_name:
            return entry.node.canonical_key
    raise AssertionError(f"no entry for {qualified_name!r}")


# ---------------------------------------------------------------------------
# 1. The reviewed input
# ---------------------------------------------------------------------------


class TestReviewedInput:
    def test_input_is_the_frozen_build_and_test_pair(self, definitions):
        assert [d.type for d in definitions] == ["build", "test"]
        assert [d.qualified_name for d in definitions] == [
            BUILD_QNAME, TEST_QNAME,
        ]

    def test_every_record_declares_the_documented_fields(self, definitions):
        for definition in definitions:
            assert definition.command.strip()
            assert definition.log_path.startswith(
                "tests/indexing/preservation/fixtures/"
            )
            assert definition.tags
            assert definition.source == "cpp-sqlite"

    def test_status_agrees_with_the_exit_code(self, definitions):
        for definition in definitions:
            assert (definition.status == "passed") == (definition.exit_code == 0)

    def test_records_are_successes(self, definitions):
        # The plan's exit gate: one successful build record and one
        # successful filtered-test record.
        assert all(d.status == "passed" and d.exit_code == 0
                   for d in definitions)

    def test_retained_logs_exist_and_match_their_digests(self, definitions):
        for definition in definitions:
            log = read_log(definition)
            assert log, f"{definition.qualified_name}: empty retained log"
            assert log_digest(definition) == definition.output_digest, (
                f"{definition.qualified_name}: retained log no longer matches "
                "the reviewed output digest"
            )

    def test_revision_records_the_provenance_chain(self, definitions):
        for definition in definitions:
            segments = dict(
                part.split(":", 1) for part in definition.revision.split(";")
            )
            assert set(segments) == {"git", "tree-sha256", "golden"}
            assert re.fullmatch(r"[0-9a-f]{40}", segments["git"])
            assert re.fullmatch(r"[0-9a-f]{64}", segments["tree-sha256"])
            assert segments["golden"] == GOLDEN_REVISION

    def test_environment_names_the_toolchain(self, definitions):
        for definition in definitions:
            keys = {item.split("=", 1)[0] for item in definition.environment}
            assert set(REQUIRED_ENVIRONMENT_KEYS) <= keys, definition

    def test_test_record_carries_exactly_the_frozen_filter(self, definitions):
        test = _definition(definitions, TEST_QNAME)
        assert f"--gtest_filter={FROZEN_GTEST_FILTER}" in test.command
        # Exactly five filter terms — the run cannot quietly widen.
        assert FROZEN_GTEST_FILTER.count(":") == 4

    def test_test_run_happens_after_the_build(self, definitions):
        build = _definition(definitions, BUILD_QNAME)
        test = _definition(definitions, TEST_QNAME)
        assert build.executed_at.tzinfo is not None
        assert test.executed_at.tzinfo is not None
        assert test.executed_at >= build.executed_at

    def test_the_input_file_is_the_reviewed_artifact(self):
        assert EVIDENCE_INPUT.is_file()
        text = EVIDENCE_INPUT.read_text(encoding="utf-8")
        assert "do not hand-edit" in text


# ---------------------------------------------------------------------------
# 2. Materialized nodes
# ---------------------------------------------------------------------------


class TestMaterializedNodes:
    def test_nodes_use_the_evidence_type(self, augmented):
        nodes = list(iter_evidence_nodes(augmented))
        assert len(nodes) == 2
        assert all(isinstance(n, ExecutionEvidenceNode) for n in nodes)

    def test_keys_are_computed_in_the_slice_scope(self, augmented):
        for node in iter_evidence_nodes(augmented):
            assert node.canonical_key.startswith(SLICE_KEY_PREFIX), node

    def test_materialization_does_not_mutate_the_slice_graph(
        self, slice_graph, definitions
    ):
        before = len(list(iter_entries(slice_graph)))
        slice_graph_with_evidence(slice_graph, definitions)
        assert len(list(iter_entries(slice_graph))) == before

    def test_authored_fields_survive_materialization_exactly(
        self, augmented, definitions
    ):
        for definition in definitions:
            node = _evidence_node(augmented, definition.qualified_name)
            assert node.evidence_type == definition.type
            assert node.status == definition.status
            assert node.command == definition.command
            assert node.exit_code == definition.exit_code
            assert node.executed_at == definition.executed_at
            assert node.duration_seconds == pytest.approx(
                definition.duration_seconds
            )
            assert list(node.environment) == list(definition.environment)
            assert node.revision == definition.revision
            assert node.output_digest == definition.output_digest
            assert node.log_path == definition.log_path
            assert list(node.tags) == list(definition.tags)
            assert node.source == definition.source


# ---------------------------------------------------------------------------
# 3. The frozen edges
# ---------------------------------------------------------------------------


class TestEvidenceEdges:
    def test_build_evidences_the_transaction_class(self, augmented):
        edges = _edges_of(augmented, BUILD_QNAME)
        class_edges = {
            target for relation, target in edges if relation == "EVIDENCES"
        }
        assert class_edges == {_key_of(augmented, BUILD_EVIDENCES_CLASS)}
        # …and it is typed as a ClassNode edge, not an untyped association.
        typed = [
            (relation, target_type)
            for entry in iter_entries(augmented)
            if entry.node.qualified_name == BUILD_QNAME
            for relation, _target, target_type in entry.references
            if relation == "EVIDENCES"
        ]
        assert typed == [("EVIDENCES", "ClassNode")]

    def test_test_run_evidences_exactly_the_five_tests(self, augmented):
        edges = _edges_of(augmented, TEST_QNAME)
        evidence_targets = {
            target for relation, target in edges if relation == "EVIDENCES"
        }
        assert evidence_targets == {
            _key_of(augmented, qname) for qname in TEST_EVIDENCES_TESTS
        }
        assert len(TEST_EVIDENCES_TESTS) == 5

    def test_evidence_targets_are_the_slice_test_nodes_themselves(
        self, augmented
    ):
        # Not lookalikes: the exact TestNode identities the slice froze.
        for qname in TEST_EVIDENCES_TESTS:
            assert TEST_QNS[qname.split("::")[-1]] == qname
            target = next(
                entry.node for entry in iter_entries(augmented)
                if entry.node.canonical_key == _key_of(augmented, qname)
            )
            assert type(target).__name__ == "TestNode"

    def test_test_run_depends_on_the_build_record(self, augmented):
        edges = _edges_of(augmented, TEST_QNAME)
        depends = {
            target for relation, target in edges if relation == "DEPENDS_ON"
        }
        assert depends == {_key_of(augmented, BUILD_QNAME)}

    def test_build_record_has_no_dependency(self, augmented):
        assert not [
            1 for relation, _t in _edges_of(augmented, BUILD_QNAME)
            if relation == "DEPENDS_ON"
        ]

    def test_every_evidence_edge_resolves_in_the_graph(self, augmented):
        keys = {entry.node.canonical_key for entry in iter_entries(augmented)}
        for node in iter_evidence_nodes(augmented):
            for relation, target in _edges_of(augmented, node.qualified_name):
                assert target in keys, (node.qualified_name, relation, target)

    def test_materialization_reports_every_edge_it_created(
        self, augmented, evidence_edges
    ):
        expected = {
            (relation, source, target)
            for node_qname in (BUILD_QNAME, TEST_QNAME)
            for relation, target in _edges_of(augmented, node_qname)
            for source in [_key_of(augmented, node_qname)]
        }
        assert set(evidence_edges) == expected
        assert len(evidence_edges) == 5 + 1 + 1  # EVIDENCES + DEPENDS_ON

    def test_unresolvable_evidences_target_raises_instead_of_dropping(
        self, slice_graph, definitions
    ):
        corrupted = tuple(
            d if d.qualified_name != TEST_QNAME else _replace(
                d, evidences=("no::such::test",)
            )
            for d in definitions
        )
        with pytest.raises(EvidenceFixtureError, match="not in the slice graph"):
            materialize_evidence(corrupted, slice_graph)

    def test_depends_on_outside_the_reviewed_pair_raises(
        self, slice_graph, definitions
    ):
        corrupted = tuple(
            d if d.qualified_name != TEST_QNAME else _replace(
                d, depends_on="evidence::bogus"
            )
            for d in definitions
        )
        with pytest.raises(EvidenceFixtureError, match="reviewed evidence"):
            materialize_evidence(corrupted, slice_graph)


# ---------------------------------------------------------------------------
# 4. Portability — the flat document carries evidence like any other node
# ---------------------------------------------------------------------------


class TestDocumentPortability:
    def test_document_carries_code_and_evidence_edges_together(
        self, document_chain
    ):
        entries = _evidence_entries(document_chain["document"])
        assert set(entries) == {BUILD_QNAME, TEST_QNAME}
        relation_types = {
            edge["relation_type"]
            for entry in entries.values()
            for edge in entry["edges"]
        }
        assert relation_types == {"EVIDENCES", "DEPENDS_ON"}

    def test_every_evidence_property_survives_export(self, augmented,
                                                     document_chain):
        entries = _evidence_entries(document_chain["document"])
        for definition_qname in (BUILD_QNAME, TEST_QNAME):
            node = _evidence_node(augmented, definition_qname)
            entry = entries[definition_qname]
            for field in ("command", "exit_code", "revision", "output_digest",
                          "log_path", "evidence_type", "status", "source"):
                assert entry[field] == getattr(node, field), (
                    definition_qname, field
                )
            assert entry["environment"] == node.environment

    def test_evidence_edges_survive_re_import(self, augmented, document_chain):
        restored = document_chain["restored"]
        for node_qname in (BUILD_QNAME, TEST_QNAME):
            original = _edges_of(augmented, node_qname)
            replayed = _edges_of(restored, node_qname)
            assert original == replayed, node_qname

    def test_evidence_properties_survive_re_import(self, augmented,
                                                   document_chain):
        restored = document_chain["restored"]
        for definition_qname in (BUILD_QNAME, TEST_QNAME):
            assert _properties(_evidence_node(restored, definition_qname)) == (
                _properties(_evidence_node(augmented, definition_qname))
            ), definition_qname

    def test_document_is_a_strict_fixpoint(self, document_chain):
        assert _document_bytes(_flat(document_chain["restored"])) == (
            _document_bytes(document_chain["document"])
        )

    def test_re_import_needs_no_backend(self, document_chain, monkeypatch):
        from codegraph import backends

        def _fail(*_args, **_kwargs):
            raise AssertionError("evidence re-import touched the backend")

        monkeypatch.setattr(backends, "get_backend", _fail, raising=False)
        restored = LayerGraph.deserialize(
            copy.deepcopy(document_chain["document"])
        )
        assert len(list(iter_evidence_nodes(restored))) == 2

    def test_no_second_identity_system_in_the_evidence(self, document_chain):
        for entry in _evidence_entries(document_chain["document"]).values():
            assert entry["canonical_key"].startswith("cg:v1:")
            for forbidden in ("uid", "refid", "target_uid"):
                assert forbidden not in entry
            for edge in entry["edges"]:
                assert edge["target_key"].startswith("cg:v1:"), edge


def _flat(graph: LayerGraph) -> dict:
    return graph.serialize(
        fields="all", document=True, layout="flat", export_implementation=True,
    )


# ---------------------------------------------------------------------------
# 5. The reviewed logs cannot drift silently
# ---------------------------------------------------------------------------


class TestLogIntegrity:
    def test_changed_log_bytes_break_the_recorded_digest(self, definitions):
        # The recorded digest is bound to the exact retained bytes: any edit
        # to a log invalidates its record, which is what makes the digest a
        # review guarantee rather than decoration.
        definition = _definition(definitions, TEST_QNAME)
        assert log_digest(definition) == definition.output_digest
        tampered = read_log(definition) + b"\n# tampered\n"
        tampered_digest = "sha256:" + hashlib.sha256(tampered).hexdigest()
        assert tampered_digest != definition.output_digest

    def test_missing_log_is_a_structured_failure(self, definitions):
        # A record whose log_path points nowhere must fail as a structured
        # EvidenceFixtureError — never an empty read, never a silent skip.
        definition = _definition(definitions, BUILD_QNAME)
        relocated = _replace(
            definition,
            log_path="tests/indexing/preservation/fixtures/cpp-sqlite/"
                     "transaction_slice/logs/deleted-log.log",
        )
        with pytest.raises(EvidenceFixtureError, match="retained log missing"):
            read_log(relocated)
