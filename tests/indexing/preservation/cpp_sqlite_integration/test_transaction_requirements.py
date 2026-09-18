"""WP5.1 — author and index the Transaction requirements slice.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

The repository document
``fixtures/cpp-sqlite/requirements/transaction/requirements.md`` is the
authority: one HLR owning five LLRs, each bound to the real
``cpp_sqlite::Transaction`` class/members with ``REALIZED_BY`` and to the five
real GoogleTests with ``VERIFIED_BY``.

This module drives the **normal** ``IndexService`` C++ path — the same request
the ``project`` command builds from ``.doxygen-index.toml`` — and asserts:

1. the configured ``requirements_dir`` is discovered inside the one index run
   (no second, manual import);
2. every requirement reference resolves to the exact as-built code/test
   canonical key, with the author-declared endpoint type, and produces no
   unresolved/ambiguous/legacy diagnostic;
3. the requirements merge does not perturb the extracted tests — the same five
   TestNodes with their real assertion/step children and core ``VERIFIES``
   links (no duplicated TestNodes);
4. Markdown export of the requirements projection re-imports to identical
   requirement properties and identical cross-domain endpoint identities.

The authored document — not a copy of it — is what the assertions compare
against, so a silently dropped description line or a dropped relationship line
fails here.

``IndexService`` does not index the Conan dependency tree (the legacy
``codegraph`` CLI does), so this slice has no ``boost``/``spdlog``/``sqlite3``
nodes.  That is recorded as a characterization, not normalized away: see
``TestExtractionNotPerturbed.test_verifies_edges_are_a_multiset_across_paths``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from codegraph.export.markdown import export_markdown
from codegraph.graph import LayerGraph
from codegraph_index.config import load_config_file, request_from_project_config
from codegraph_index.contracts import (
    Availability,
    ExtractionResult,
    IndexMode,
    IndexRequest,
    Severity,
)
from codegraph_index.service import IndexService

from .transaction_slice import (
    CORE_VERIFIES,
    TEST_BASELINES,
    TEST_QNS,
    TRANSACTION_METHOD_QNS,
    TransactionSlice,
    build_transaction_slice,
)

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "cpp-sqlite"
_FIXTURE_CONFIG = _FIXTURE_DIR / ".doxygen-index.toml"
_REQUIREMENTS_DOC = (
    _FIXTURE_DIR / "requirements" / "transaction" / "requirements.md"
)
_TEST_SOURCE = (
    _FIXTURE_DIR / "cpp_sqlite" / "test" / "testDatabase.cpp"
)

#: The identity both the as-built cpp-sqlite graph and these requirements use.
SCOPE_PREFIX = "cg:v1:repository:cpp-sqlite%2Fcpp-sqlite:"

HLR_QN = "Transaction Lifecycle"

#: The relationship types the frozen vocabulary allows on an LLR.
FROZEN_RELATION_TYPES = frozenset({"REALIZED_BY", "VERIFIED_BY"})

_REQUIREMENT_REFERENCE_CODES = frozenset({
    "UNRESOLVED_REQUIREMENT_REFERENCE",
    "AMBIGUOUS_REQUIREMENT_REFERENCE",
    "LEGACY_REQUIREMENT_REFERENCE_DROPPED",
})

_HEADING_RE = re.compile(r"^#{2,}\s+(HLR|LLR):\s+`([^`]+)`\s*$")
_RELATIONSHIP_RE = re.compile(
    r"^-\s*`([^`]+)`\s*→\s*`([^`]+)`\s*\*\*(\w+)\*\*\s*\((\w+)\)\s*$"
)
_TEST_F_RE = re.compile(r"^TEST_F\(\s*DatabaseTest\s*,\s*(\w+)\s*\)")


# ---------------------------------------------------------------------------
# Authored-document parsing (the authority the assertions compare against)
# ---------------------------------------------------------------------------


def _authored_blocks() -> dict[str, str]:
    """Return ``{qualified_name: authored description}`` from the document.

    Mirrors the importer's rule: a description is every non-blank line after a
    requirement heading up to the first property line (``- key: value``) or
    the next heading, joined with newlines.
    """
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in _REQUIREMENTS_DOC.read_text(encoding="utf-8").splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            current = match.group(2)
            blocks[current] = []
            continue
        if line.startswith("## Relationships") or line.startswith("# "):
            current = None
            continue
        if current is None:
            continue
        if line.strip().startswith("- "):
            current = None
            continue
        if line.strip():
            blocks[current].append(line.rstrip())
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def _authored_relationships() -> list[tuple[str, str, str, str]]:
    """Return ``(source_qname, relation_type, target_qname, target_type)``."""
    relationships: list[tuple[str, str, str, str]] = []
    for line in _REQUIREMENTS_DOC.read_text(encoding="utf-8").splitlines():
        match = _RELATIONSHIP_RE.match(line.strip())
        if match:
            source, target, label, target_type = match.groups()
            relationships.append(
                (source, label.upper(), target, target_type)
            )
    return relationships


def _fixture_test_names() -> set[str]:
    """The ``TEST_F`` names declared by the fixture test source."""
    names = set()
    for line in _TEST_SOURCE.read_text(encoding="utf-8").splitlines():
        match = _TEST_F_RE.match(line.strip())
        if match:
            names.add(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def _entries(graph: LayerGraph, type_name: str) -> list:
    return [e for e in graph._all_entries() if type(e.node).__name__ == type_name]


def _node_of_type(graph: LayerGraph, qualified_name: str, type_name: str):
    """The single entry named *qualified_name* whose node type is *type_name*."""
    matches = [
        entry for entry in graph._all_entries()
        if entry.node.qualified_name == qualified_name
        and type(entry.node).__name__ == type_name
    ]
    assert len(matches) == 1, (
        f"expected exactly one {type_name} named {qualified_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _reference_triples(entry) -> set[tuple[str, str, str]]:
    return {
        (relation_type, target_key, target_type)
        for relation_type, target_key, target_type in entry.references
    }


# ---------------------------------------------------------------------------
# The indexed slice (module scope: one index run)
# ---------------------------------------------------------------------------


class _ExtractedGraphAdapter:
    """Adapter that re-supplies an already-extracted graph.

    Used by the round-trip test: the requirements document is re-indexed
    through the normal service, against the *same* extracted code/test graph
    the first run produced, so the comparison isolates the document round trip.
    """

    name = "preservation-extracted"
    version = "1"
    languages = frozenset({"preservation-extracted"})

    def __init__(self, graph: LayerGraph) -> None:
        self._graph = graph

    def available(self, request: IndexRequest) -> Availability:
        return Availability(True)

    def extract(self, request: IndexRequest) -> ExtractionResult:
        return ExtractionResult(self._graph)


def _index_request(project_root: Path, output_dir: Path, requirements_dir: Path):
    """The request the ``project`` command builds from the fixture config."""
    config = load_config_file(_FIXTURE_DIR)
    request = request_from_project_config(
        project_root,
        config,
        project_id="cpp-sqlite",
        repository_id="cpp-sqlite",
        source="cpp-sqlite",
        mode=IndexMode.EXTRACT_ONLY,
        # ``layer`` is the provenance tag the parser stamps on extracted
        # nodes.  "as-built" is the tag the rest of the cpp-sqlite
        # integration suite uses for this fixture's graph.
        adapter_options={"progress_interval": 0, "layer": "as-built"},
    )
    return dataclasses.replace(
        request, output_dir=output_dir, requirements_dir=requirements_dir
    )


@pytest.fixture(scope="module")
def indexed(transaction_slice_index):
    """The shared session ``IndexService`` run for this fixture slice.

    One index run per session serves every module that asserts against the
    Transaction slice; see ``conftest.transaction_slice_index``.
    """
    return transaction_slice_index


@pytest.fixture(scope="module")
def slice_(indexed) -> TransactionSlice:
    """The WP5.0 frozen slice contract, re-derived from this index run."""
    return build_transaction_slice(indexed.graph.serialize(fields="all"))


# ---------------------------------------------------------------------------
# 1. Discovery through the configured requirements_dir
# ---------------------------------------------------------------------------


class TestRequirementsDiscovery:
    def test_fixture_configures_a_requirements_directory(self):
        config = load_config_file(_FIXTURE_DIR)
        assert config.requirements_dir == (_FIXTURE_DIR / "requirements").resolve()
        assert config.requirements_dir.is_dir()

    def test_authoritative_document_is_named_requirements_md(self):
        assert _REQUIREMENTS_DOC.is_file()
        assert _REQUIREMENTS_DOC.name == "requirements.md"

    def test_one_index_run_discovers_the_requirements(self, indexed):
        assert indexed.success is True, [
            f"{d.code}: {d.message}" for d in indexed.diagnostics
        ]
        assert not [
            d for d in indexed.diagnostics if d.severity is Severity.ERROR
        ]

        hlrs = _entries(indexed.graph, "HLR")
        llrs = _entries(indexed.graph, "LLR")
        assert [e.node.qualified_name for e in hlrs] == [HLR_QN]
        assert {e.node.qualified_name for e in llrs} == set(
            name for name in _authored_blocks() if name != HLR_QN
        )
        assert len(llrs) == 5, "the frozen scope is one HLR owning five LLRs"

    def test_hlr_composes_the_five_llrs(self, indexed):
        hlr = _node_of_type(indexed.graph, HLR_QN, "HLR")
        composed = {
            child.node.qualified_name
            for children in hlr.children.values()
            for child in children.values()
            if type(child.node).__name__ == "LLR"
        }
        expected = {
            name for name in _authored_blocks() if name != HLR_QN
        }
        assert composed == expected

    def test_provenance_tags_separate_requirements_from_code(self, indexed):
        for entry in indexed.graph._all_entries():
            tags = set(entry.node.tags or ())
            node_type = type(entry.node).__name__
            if node_type in ("HLR", "LLR"):
                assert tags == {"requirements"}, entry.node.qualified_name
            else:
                assert tags == {"as-built"}, (
                    f"{node_type} {entry.node.qualified_name} carries {tags}"
                )
            assert entry.node.source == "cpp-sqlite"


# ---------------------------------------------------------------------------
# 2. Exact cross-domain reference resolution
# ---------------------------------------------------------------------------


class TestReferenceResolution:
    def test_llr_references_match_the_authored_relationships_exactly(
        self, indexed
    ):
        """Every authored edge, and only those, resolves to the right endpoint."""
        expected: dict[str, set[tuple[str, str, str]]] = {}
        for source, relation_type, target, target_type in (
            _authored_relationships()
        ):
            assert relation_type in FROZEN_RELATION_TYPES, relation_type
            endpoint = _node_of_type(indexed.graph, target, target_type)
            key = endpoint.node.canonical_key
            assert key.startswith(SCOPE_PREFIX), key
            expected.setdefault(source, set()).add(
                (relation_type, key, target_type)
            )

        for llr_qname, triples in expected.items():
            llr = _node_of_type(indexed.graph, llr_qname, "LLR")
            assert _reference_triples(llr) == triples, llr_qname
            assert {rt for rt, _key, _tt in triples} <= FROZEN_RELATION_TYPES

    def test_all_five_real_tests_are_verified_by_a_requirement(self, indexed):
        verified = {
            target_key
            for entry in _entries(indexed.graph, "LLR")
            for relation_type, target_key, _type in entry.references
            if relation_type == "VERIFIED_BY"
        }
        expected = {
            _node_of_type(indexed.graph, qn, "TestNode").node.canonical_key
            for qn in TEST_QNS.values()
        }
        assert verified == expected
        assert len(expected) == 5

    def test_verified_by_targets_the_real_parsed_test_nodes(self, indexed):
        for llr_entry in _entries(indexed.graph, "LLR"):
            for relation_type, target_key, target_type in llr_entry.references:
                if relation_type != "VERIFIED_BY":
                    continue
                assert target_type == "TestNode"
                target = indexed.graph._flat_index()[target_key].node
                assert target.qualified_name in set(TEST_QNS.values())
                assert target.file_path.endswith("testDatabase.cpp")
                assert target.line_number > 0
                assert target.method == "automated"

    def test_realized_by_targets_the_transaction_class_and_members(
        self, indexed
    ):
        member_qnames = set(TRANSACTION_METHOD_QNS.values())
        realized = {
            indexed.graph._flat_index()[target_key].node.qualified_name
            for entry in _entries(indexed.graph, "LLR")
            for relation_type, target_key, _type in entry.references
            if relation_type == "REALIZED_BY"
        }
        authored = {
            target for _source, relation_type, target, _type
            in _authored_relationships()
            if relation_type == "REALIZED_BY"
        }
        assert realized == authored
        # Nothing outside the frozen implementation surface is claimed.
        assert realized <= member_qnames | {"cpp_sqlite::Transaction"}
        assert len(realized) > 1
        assert "cpp_sqlite::Transaction::commit()" in realized
        assert "cpp_sqlite::Transaction::rollback()" in realized
        assert "cpp_sqlite::Transaction::~Transaction(())" in realized

    def test_no_unresolved_or_ambiguous_reference_diagnostics(self, indexed):
        codes = {d.code for d in indexed.diagnostics}
        assert not (codes & _REQUIREMENT_REFERENCE_CODES), [
            f"{d.code}: {d.message}" for d in indexed.diagnostics
        ]
        assert indexed.diagnostics == ()

    def test_every_reference_endpoint_is_a_canonical_key(self, indexed):
        for entry in indexed.graph._all_entries():
            for relation_type, target_key, target_type in entry.references:
                assert target_key.startswith("cg:v1:"), (
                    f"{entry.node.qualified_name} {relation_type} -> "
                    f"{target_key!r}"
                )
                assert target_type, entry.node.qualified_name
                assert target_key in indexed.graph._flat_index(), (
                    f"{entry.node.qualified_name} {relation_type} -> "
                    f"{target_key} does not resolve to a node"
                )

    def test_requirement_relationship_descriptors_exist(self):
        """The frozen vocabulary is declared on the model, not invented per doc."""
        from codegraph.models import (
            AttributeNode,
            ClassNode,
            MethodNode,
            TestNode,
        )
        from codegraph.models.descriptors import (
            find_relationship_descriptor,
        )
        from codegraph_requirements.models.requirement import LLR

        assert find_relationship_descriptor(
            LLR, "REALIZED_BY", ClassNode
        ) is not None
        assert find_relationship_descriptor(
            LLR, "REALIZED_BY", MethodNode
        ) is not None
        assert find_relationship_descriptor(
            LLR, "REALIZED_BY", AttributeNode
        ) is not None
        assert find_relationship_descriptor(
            LLR, "VERIFIED_BY", TestNode
        ) is not None
        # Canonical identity of the requirement types is unchanged.
        assert LLR._identity_fields == ("qualified_name",)


# ---------------------------------------------------------------------------
# 3. The requirements merge does not perturb the extracted tests
# ---------------------------------------------------------------------------


class TestExtractionNotPerturbed:
    def test_five_real_tests_exist_exactly_once(self, indexed):
        for name, qualified_name in TEST_QNS.items():
            matches = [
                entry for entry in indexed.graph._all_entries()
                if getattr(entry.node, "qualified_name", "") == qualified_name
            ]
            assert len(matches) == 1, (
                f"{name}: expected one TestNode, found {len(matches)} — the "
                "requirements document must not declare Test headings"
            )
            assert type(matches[0].node).__name__ == "TestNode"

    def test_test_node_inventory_matches_the_fixture_source(self, indexed):
        tests = _entries(indexed.graph, "TestNode")
        names = [entry.node.qualified_name for entry in tests]
        assert len(names) == len(set(names)), "duplicate TestNode identities"
        assert set(names) == {
            f"testDatabase::DatabaseTest::{name}"
            for name in _fixture_test_names()
        }

    def test_real_tests_keep_their_assertion_and_step_children(
        self, indexed, slice_
    ):
        for name, baseline in TEST_BASELINES.items():
            entry = _node_of_type(
                indexed.graph, TEST_QNS[name], "TestNode"
            )
            children = [
                child.node
                for group in entry.children.values()
                for child in group.values()
            ]
            assertions = [
                c for c in children if type(c).__name__ == "AssertionNode"
            ]
            steps = [
                c for c in children if type(c).__name__ == "TestStepNode"
            ]
            assert len(assertions) == baseline.assertions, name
            assert len(steps) == baseline.steps, name
            # The frozen WP5.0 contract sees the same children.
            assert len(slice_.child_keys[name]) == (
                baseline.assertions + baseline.steps
            )

    def test_core_verifies_links_survive(self, indexed, slice_):
        member_keys = set(slice_.method_keys.values())
        label_by_key = {
            key: label for label, key in slice_.method_keys.items()
        }
        for name in TEST_QNS:
            entry = _node_of_type(indexed.graph, TEST_QNS[name], "TestNode")
            members = {
                label_by_key[target_key]
                for relation_type, target_key, _type in entry.references
                if relation_type == "VERIFIES" and target_key in member_keys
            }
            assert members == set(CORE_VERIFIES[name]), name

    def test_verifies_edges_are_a_multiset_across_paths(self, indexed):
        """Characterization: the C++ adapter emits repeated ``VERIFIES`` edges.

        ``IndexService`` (project + test Doxygen, no Conan dependencies) emits
        one ``VERIFIES`` edge per source reference, so a test that names
        ``Database::isInTransaction`` three times yields three edges.  The
        legacy unified ``codegraph`` CLI path dedupes them and additionally
        resolves dependency targets (``boost::…``).  The plan's baseline table
        was taken from that CLI path, so distinct-target sets — not edge
        counts — are the cross-path contract.  Recording it here keeps the
        difference visible instead of hiding it behind a counts assertion.
        """
        repeated = {}
        for name in TEST_QNS:
            entry = _node_of_type(indexed.graph, TEST_QNS[name], "TestNode")
            targets = [
                target_key
                for relation_type, target_key, _type in entry.references
                if relation_type == "VERIFIES"
            ]
            if len(targets) != len(set(targets)):
                repeated[name] = len(targets) - len(set(targets))
        assert repeated, (
            "expected the adapter path to repeat at least one VERIFIES edge; "
            "if the extractor started deduplicating, update the plan baseline "
            "rather than deleting this characterization"
        )


# ---------------------------------------------------------------------------
# 4. Markdown export → re-import
# ---------------------------------------------------------------------------


def _requirements_projection(graph: LayerGraph) -> LayerGraph:
    """A requirements-only view of the merged graph.

    The projection contains the HLR subtree (HLR + its LLRs) and nothing else:
    the endpoint identities stay on each LLR's references, they are not
    re-declared as headings (which would create duplicate code nodes on
    re-import).
    """
    entries = {
        entry.node.canonical_key: entry
        for entry in _entries(graph, "HLR")
    }
    return LayerGraph(tags=frozenset({"requirements"}), entries=entries)


def _code_only_copy(graph: LayerGraph) -> LayerGraph:
    """A fresh, requirement-free copy of the extracted code/test graph."""
    serialized = [
        entry.serialize(fields="all", export_implementation=True)
        for key, entry in graph.entries.items()
        if "requirements" not in (getattr(entry.node, "tags", None) or ())
    ]
    return LayerGraph.deserialize(serialized, create_missing=False)


def _requirement_snapshot(graph: LayerGraph) -> dict:
    """``{(node type, qualified name): (properties, reference triples)}``."""
    return {
        (type(entry.node).__name__, entry.node.qualified_name): (
            entry.node.description,
            getattr(entry.node, "status", ""),
            tuple(sorted(entry.node.tags or ())),
            tuple(sorted(
                (relation_type, target_key, target_type)
                for relation_type, target_key, target_type in entry.references
            )),
        )
        for entry in graph._all_entries()
        if type(entry.node).__name__ in ("HLR", "LLR")
    }


def _reindex_requirements(indexed, tmp_path: Path, text: str):
    """Re-index *text* as the authoritative document, same code graph."""
    requirements_dir = tmp_path / "requirements"
    document = requirements_dir / "transaction" / "requirements.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(text, encoding="utf-8")

    request = IndexRequest(
        project_root=tmp_path,
        project_id="cpp-sqlite",
        repository_id="cpp-sqlite",
        source="cpp-sqlite",
        language="preservation-extracted",
        input_paths=(tmp_path,),
        requirements_dir=requirements_dir,
        mode=IndexMode.EXTRACT_ONLY,
    )
    return IndexService(
        (_ExtractedGraphAdapter(_code_only_copy(indexed.graph)),)
    ).index(request)


class TestRequirementsRoundTrip:
    def test_exported_projection_keeps_the_authored_requirement_text(
        self, indexed
    ):
        exported = export_markdown(
            _requirements_projection(indexed.graph), fields="all"
        )
        assert f"## HLR: `{HLR_QN}`" in exported
        for name, description in _authored_blocks().items():
            heading = (
                f"## HLR: `{name}`" if name == HLR_QN
                else f"### LLR: `{name}`"
            )
            assert heading in exported, name
            assert description in exported, f"export lost the text of {name}"

    def test_reimport_preserves_properties_and_endpoint_identities(
        self, indexed, tmp_path
    ):
        exported = export_markdown(
            _requirements_projection(indexed.graph), fields="all"
        )
        result = _reindex_requirements(indexed, tmp_path, exported)

        assert result.success is True, [
            f"{d.code}: {d.message}" for d in result.diagnostics
        ]
        assert result.diagnostics == ()

        original = _requirement_snapshot(indexed.graph)
        restored = _requirement_snapshot(result.graph)
        assert set(restored) == set(original)
        assert restored == original

    def test_ascii_arrow_relationship_lines_resolve_identically(
        self, indexed, tmp_path
    ):
        """The authored document with ASCII arrows indexes to the same slice.

        ``→`` is the exporter's canonical spelling, but the repository
        document is hand-authored and an ASCII arrow is a natural way to write
        it.  A line the importer cannot parse is a dropped requirement→code
        link, so both spellings must produce identical endpoints.
        """
        authored = _REQUIREMENTS_DOC.read_text(encoding="utf-8")
        ascii_document = authored.replace("→", "->")
        assert ascii_document != authored
        assert "→" not in ascii_document

        result = _reindex_requirements(indexed, tmp_path, ascii_document)

        assert result.success is True, [
            f"{d.code}: {d.message}" for d in result.diagnostics
        ]
        assert result.diagnostics == ()
        assert _requirement_snapshot(result.graph) == _requirement_snapshot(
            indexed.graph
        )

    def test_exported_relationships_name_exact_canonical_endpoints(
        self, indexed
    ):
        """The projection carries endpoint identity, not a human guess.

        A requirements-only projection has no code/test nodes to look names up
        in, so each cross-domain edge is written with its canonical key; the
        re-import above proves those keys resolve to the same nodes.  This is
        the documented spelling for a projection — the repository document
        itself stays the reviewable, human-authored authority.
        """
        exported = export_markdown(
            _requirements_projection(indexed.graph), fields="all"
        )
        lines = [
            line for line in exported.splitlines()
            if "**realized_by**" in line or "**verified_by**" in line
        ]
        assert lines
        for line in lines:
            _, _, target = line.partition(" → ")
            assert target.startswith(f"`{SCOPE_PREFIX}"), line
        assert len(lines) == len(_authored_relationships())
