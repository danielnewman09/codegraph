"""Bidirectional fidelity test for a golden repository requirements document.

The fixture ``data/requirements_roundtrip/requirements.md`` is an
authoritative, human-authored requirements document.  This module pins
the full loop the repository-authority contract depends on (see
design_intent/14-prioritized-work-roadmap.md, Priority 4):

    golden markdown → unified index → assertions on indexed content
                                    → export back to markdown
                                    → re-index → identical content

The three claims under test are distinct:

1. **Ingestion** — the unified index operation discovers the document
   under ``requirements_dir`` and imports every requirement, test, and
   relationship without an error diagnostic.
2. **Content** — the indexed graph carries the authored hierarchy,
   descriptions, lifecycle ``status``, verification structure, and
   resolved relationships (as canonical keys, not legacy endpoints).
3. **Round trip** — the indexed content exports back to Markdown that
   (a) still contains every authored element, (b) re-imports to the same
   nodes, and (c) is a fixpoint: exporting the re-imported graph yields
   byte-identical Markdown.

The exported document is written to the gitignored local
``unit_test_data/requirements.md`` for visual inspection after a run, and
that same file is what gets re-indexed — so the assertions cover the exact
bytes the test produced, not an in-memory copy.

The fixture deliberately references only entities declared inside the
document, so every relationship must resolve within the document — an
unresolved reference is a failure rather than an expected warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegraph.export.markdown import export_markdown
from codegraph.graph import LayerGraph
from codegraph_index.contracts import (
    Availability,
    ExtractionResult,
    IndexRequest,
    Severity,
)
from codegraph_index.service import IndexService

FIXTURE_DIR = Path(__file__).parent / "data" / "requirements_roundtrip"
FIXTURE = FIXTURE_DIR / "requirements.md"

#: Local, gitignored inspection directory for the round-trip export.  Each
#: run regenerates ``unit_test_data/requirements.md`` in this directory and
#: re-indexes that exact file.
ROUNDTRIP_OUTPUT_DIR = Path(__file__).resolve().parent / "unit_test_data"

#: Qualifying names the fixture declares, in document order.
HLRS = ("Transaction Safety", "Exception Safety")
LLRS = ("llr_transaction_commit", "llr_transaction_rollback")
TESTS = (
    "vm::transaction::test_commit_persists",
    "vm::transaction::test_rollback_discards",
)
STEPS = (
    "step::transaction_commit_insert",
    "step::transaction_rollback_insert",
)
ASSERTIONS = (
    "cond::post::commit_row_count_is_one",
    "cond::post::rollback_row_count_is_zero",
)

#: The golden fixture deliberately wraps authored prose across several
#: physical lines.  A single-line-only importer silently keeps the first
#: line and drops the rest, so these constants pin the complete text.
TRANSACTION_DESCRIPTION = (
    "A transaction shall apply the statements issued between begin and commit "
    "as a single unit,\n"
    "and a failure before commit shall leave the database exactly as it was "
    "before begin,\n"
    "including the values of every row it touched."
)
COMMIT_DESCRIPTION = (
    "When commit succeeds the transaction shall persist every statement "
    "executed since begin\n"
    "and release the underlying database lock."
)
EXCEPTION_DESCRIPTION = (
    "The transaction shall roll back automatically when an exception escapes "
    "the scope that owns it,\n"
    "so that no partially applied change survives unwinding."
)


class EmptyAdapter:
    """Adapter that extracts nothing, isolating the requirements slice."""

    name = "empty"
    version = "test"
    languages = frozenset({"empty"})

    def available(self, request):
        return Availability(True)

    def extract(self, request):
        return ExtractionResult(LayerGraph(tags=frozenset({"as-built"})))


def _request(tmp_path: Path) -> IndexRequest:
    return IndexRequest(
        project_root=tmp_path,
        project_id="requirements-roundtrip",
        repository_id="fixture",
        source="fixture",
        language="empty",
        input_paths=(tmp_path,),
        requirements_dir=FIXTURE_DIR,
    )


def _nodes(graph: LayerGraph, type_name: str) -> dict[str, object]:
    """Return ``{qualified_name: node}`` for every node of *type_name*."""
    return {
        entry.node.qualified_name: entry.node
        for entry in graph._all_entries()
        if type(entry.node).__name__ == type_name
    }


def _child_qnames(graph: LayerGraph, parent_qname: str, type_name: str) -> set[str]:
    """Qualified names of *type_name* children composed under *parent_qname*."""
    for entry in graph._all_entries():
        if entry.node.qualified_name != parent_qname:
            continue
        return {
            child.node.qualified_name
            for children in entry.children.values()
            for child in children.values()
            if type(child.node).__name__ == type_name
        }
    return set()


def _export_and_reindex(graph: LayerGraph) -> LayerGraph:
    """Export *graph* to the local authoritative document and re-index it.

    The document is written to the gitignored ``unit_test_data/requirements.md``
    (so a failed run can be inspected after the fact) and pushed back through
    the *unified index operation* (:class:`IndexService`) rather than the
    Markdown importer directly.  That is the path a repository checkout
    actually takes, so the assertions exercise discovery, import,
    canonical-key resolution, and reconciliation — not just a private helper.
    """
    requirements_dir = ROUNDTRIP_OUTPUT_DIR
    requirements_dir.mkdir(parents=True, exist_ok=True)
    (requirements_dir / "requirements.md").write_text(
        export_markdown(graph), encoding="utf-8"
    )

    request = IndexRequest(
        project_root=requirements_dir,
        project_id="requirements-roundtrip",
        repository_id="fixture",
        source="fixture",
        language="empty",
        input_paths=(requirements_dir,),
        requirements_dir=requirements_dir,
    )
    result = IndexService((EmptyAdapter(),)).index(request)
    errors = [d for d in result.diagnostics if d.severity is Severity.ERROR]
    assert result.success is True, [f"{d.code}: {d.message}" for d in errors]
    return result.graph


#: Identity/bookkeeping fields that legitimately differ between two index
#: runs and therefore must not participate in the semantic comparison.
_VOLATILE_FIELDS = frozenset(
    {"uid", "canonical_key", "element_id", "edges", "composes"}
)


def _entity_properties(graph: LayerGraph) -> dict:
    """Every node's type, qualified name, and remaining property values."""
    entities: dict[str, dict[str, dict]] = {}
    for entry in graph._all_entries():
        node = entry.node
        data = node.serialize(fields="all")
        for field_name in _VOLATILE_FIELDS:
            data.pop(field_name, None)
        if "tags" in data:
            data["tags"] = sorted(data.get("tags") or [])
        entities.setdefault(type(node).__name__, {})[node.qualified_name] = data
    return entities


def _hierarchy(graph: LayerGraph) -> dict:
    """Composed ``(parent type, parent) → [(child type, child)]`` map."""
    result = {}
    for entry in graph._all_entries():
        children = sorted(
            (type(child.node).__name__, child.node.qualified_name)
            for type_children in entry.children.values()
            for child in type_children.values()
        )
        if children:
            result[(type(entry.node).__name__, entry.node.qualified_name)] = children
    return result


def _relationships(graph: LayerGraph) -> dict:
    """Non-composition edges, with canonical endpoints resolved to names."""
    by_canonical = {
        entry.node.canonical_key: entry
        for entry in graph._all_entries()
        if getattr(entry.node, "canonical_key", "")
    }
    result = {}
    for entry in graph._all_entries():
        edges = sorted(
            (
                rel_type,
                target_type,
                (
                    by_canonical[target_key].node.qualified_name
                    if target_key in by_canonical
                    else target_key
                ),
            )
            for rel_type, target_key, target_type in entry.references
        )
        if edges:
            result[(type(entry.node).__name__, entry.node.qualified_name)] = edges
    return result


def _semantic_snapshot(graph: LayerGraph) -> tuple:
    """The complete authored content: properties, hierarchy, relationships."""
    return (
        _entity_properties(graph),
        _hierarchy(graph),
        _relationships(graph),
    )


@pytest.fixture(scope="module")
def golden_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def indexed(tmp_path_factory) -> object:
    """Run the golden document through the unified index operation once."""
    tmp_path = tmp_path_factory.mktemp("requirements-roundtrip")
    return IndexService((EmptyAdapter(),)).index(_request(tmp_path))


# ── 1. Ingestion ─────────────────────────────────────────────────────────


def test_golden_fixture_exists_and_is_the_authoritative_filename():
    assert FIXTURE.is_file(), f"missing golden fixture: {FIXTURE}"
    assert FIXTURE.name == "requirements.md"


def test_unified_index_ingests_the_golden_document(indexed):
    errors = [d for d in indexed.diagnostics if d.severity is Severity.ERROR]
    assert not errors, [f"{d.code}: {d.message}" for d in errors]
    assert indexed.success is True, errors

    # Smoke check that the document actually reached the graph; the
    # per-type content assertions follow in the next section.
    assert _nodes(indexed.graph, "HLR"), "no HLR nodes indexed"


def test_no_reference_diagnostics_the_document_resolves_internally(indexed):
    """Every authored reference resolves; nothing is dropped or ambiguous."""
    unexpected = [
        d.code
        for d in indexed.diagnostics
        if d.code
        in {
            "UNRESOLVED_REQUIREMENT_REFERENCE",
            "AMBIGUOUS_REQUIREMENT_REFERENCE",
            "LEGACY_REQUIREMENT_REFERENCE_DROPPED",
        }
    ]
    assert not unexpected, unexpected


# ── 2. Indexed content ───────────────────────────────────────────────────


def test_hlr_hierarchy_and_descriptions_are_indexed(indexed):
    graph = indexed.graph
    hlrs = _nodes(graph, "HLR")
    assert set(hlrs) == set(HLRS)

    tx = hlrs["Transaction Safety"]
    # The complete multiline description, not just its first physical line.
    assert tx.description == TRANSACTION_DESCRIPTION
    assert len(tx.description.splitlines()) == 3
    assert tx.status == "accepted"
    assert "requirements" in tx.tags

    safety = hlrs["Exception Safety"]
    assert safety.description == EXCEPTION_DESCRIPTION
    assert len(safety.description.splitlines()) == 2
    assert safety.status == "proposed"


def test_llrs_are_composed_under_their_owning_hlr(indexed):
    graph = indexed.graph
    assert set(_nodes(graph, "LLR")) == set(LLRS)

    assert _child_qnames(graph, "Transaction Safety", "LLR") == set(LLRS)
    assert _child_qnames(graph, "Exception Safety", "LLR") == set()

    assert _nodes(graph, "LLR")["llr_transaction_commit"].status == "accepted"
    assert _nodes(graph, "LLR")["llr_transaction_rollback"].status == "accepted"
    assert (
        _nodes(graph, "LLR")["llr_transaction_commit"].description
        == COMMIT_DESCRIPTION
    )


def test_verification_structure_is_composed_under_each_llr(indexed):
    graph = indexed.graph
    assert set(_nodes(graph, "TestNode")) == set(TESTS)
    assert set(_nodes(graph, "TestStepNode")) == set(STEPS)
    assert set(_nodes(graph, "AssertionNode")) == set(ASSERTIONS)
    assert set(_nodes(graph, "TestFixtureNode")) == set()

    assert _child_qnames(graph, "llr_transaction_commit", "TestNode") == {
        "vm::transaction::test_commit_persists"
    }
    assert _child_qnames(
        graph, "vm::transaction::test_commit_persists", "TestStepNode"
    ) == {"step::transaction_commit_insert"}
    assert _child_qnames(
        graph, "vm::transaction::test_commit_persists", "AssertionNode"
    ) == {"cond::post::commit_row_count_is_one"}

    assertion = _nodes(graph, "AssertionNode")["cond::post::commit_row_count_is_one"]
    assert assertion.operator == "=="
    assert assertion.phase == "post"


def test_relationship_is_indexed_as_a_canonical_key(indexed):
    """The authored ``depends_on`` edge resolves to a canonical endpoint."""
    graph = indexed.graph
    source = next(
        entry
        for entry in graph._all_entries()
        if entry.node.qualified_name == "Exception Safety"
    )
    depends_on = [
        (rel_type, target, target_type)
        for rel_type, target, target_type in source.references
        if rel_type == "DEPENDS_ON"
    ]
    assert len(depends_on) == 1, source.references
    _rel_type, target, target_type = depends_on[0]

    assert target.startswith("cg:v1:"), target
    assert target_type == "HLR"

    target_entry = next(
        entry
        for entry in graph._all_entries()
        if entry.node.canonical_key == target
    )
    assert target_entry.node.qualified_name == "Transaction Safety"


# ── 3. Round trip ────────────────────────────────────────────────────────


def test_export_retains_every_authored_element(indexed, golden_text):
    """Nothing authored is dropped on the way back out to Markdown."""
    exported = export_markdown(indexed.graph)

    for qname in (*HLRS, *LLRS, *TESTS, *STEPS, *ASSERTIONS):
        assert f"`{qname}`" in exported, f"export lost node {qname!r}"

    for phrase in (
        "A transaction shall apply the statements",
        "The transaction shall roll back automatically",
        "When commit succeeds the transaction shall persist",
        "When rollback is invoked the transaction shall discard",
        "A row inserted inside a committed transaction",
        "A row inserted inside a rolled-back transaction",
    ):
        assert phrase in exported, f"export lost description text {phrase!r}"

    # Multiline prose survives as the complete joined description.
    assert TRANSACTION_DESCRIPTION in exported
    assert COMMIT_DESCRIPTION in exported
    assert EXCEPTION_DESCRIPTION in exported

    assert "- status: accepted" in exported
    assert "- status: proposed" in exported
    assert "**depends_on**" in exported
    assert "Transaction Safety" in exported

    # The authored document stays the authority: the export is a
    # projection of it, not a rewrite of its content.
    assert golden_text.count("## HLR:") == len(HLRS)


def test_exported_markdown_reimports_to_the_same_nodes(indexed):
    restored = _export_and_reindex(indexed.graph)

    for type_name, expected in (
        ("HLR", set(HLRS)),
        ("LLR", set(LLRS)),
        ("TestNode", set(TESTS)),
        ("TestStepNode", set(STEPS)),
        ("AssertionNode", set(ASSERTIONS)),
    ):
        assert set(_nodes(restored, type_name)) == expected, type_name

    original_hlrs = _nodes(indexed.graph, "HLR")
    restored_hlrs = _nodes(restored, "HLR")
    for qname, node in original_hlrs.items():
        assert restored_hlrs[qname].description == node.description
        assert restored_hlrs[qname].status == node.status
        assert set(restored_hlrs[qname].tags) == set(node.tags)

    original_llrs = _nodes(indexed.graph, "LLR")
    restored_llrs = _nodes(restored, "LLR")
    for qname, node in original_llrs.items():
        assert restored_llrs[qname].description == node.description
        assert restored_llrs[qname].status == node.status

    # Hierarchy survives the trip in both directions.
    assert _child_qnames(restored, "Transaction Safety", "LLR") == set(LLRS)
    assert _child_qnames(restored, "llr_transaction_rollback", "TestNode") == {
        "vm::transaction::test_rollback_discards"
    }


def test_reindex_via_index_service_preserves_semantic_content(indexed):
    """The re-indexed document carries the *whole* authored semantics.

    Comparing the original indexed graph with the graph produced by
    re-indexing its own export catches data lost on the first import: the
    byte-stable fixpoint below cannot, because the loss is already present
    in both of the exports it compares.
    """
    restored = _export_and_reindex(indexed.graph)

    original_entities, original_hierarchy, original_edges = _semantic_snapshot(
        indexed.graph
    )
    restored_entities, restored_hierarchy, restored_edges = _semantic_snapshot(
        restored
    )

    assert restored_entities == original_entities
    assert restored_hierarchy == original_hierarchy
    assert restored_edges == original_edges

    # Spot-check the multiline prose against the authored constants so a
    # failure names the lost text instead of dumping two property maps.
    restored_hlrs = _nodes(restored, "HLR")
    assert restored_hlrs["Transaction Safety"].description == TRANSACTION_DESCRIPTION
    assert restored_hlrs["Exception Safety"].description == EXCEPTION_DESCRIPTION
    assert (
        _nodes(restored, "LLR")["llr_transaction_commit"].description
        == COMMIT_DESCRIPTION
    )


def test_export_is_a_fixpoint(indexed):
    """``export(import(export(g))) == export(g)`` byte for byte."""
    first = export_markdown(indexed.graph)
    restored = _export_and_reindex(indexed.graph)
    second = export_markdown(restored)
    assert second == first
