"""Codegen run against the sister repo's cpp-sqlite one-hop as-built graph.

The fixture ``tests/unit_test_data/cpp_sqlite_one_hop.json`` is the
serialized as-built LayerGraph the sister repo
(``doxygen-dependency-parser``) exports from its cpp-sqlite fixture
project (``tests/cpp_sqlite_integration/`` → ``LayerGraph.from_backend(
"as-built")`` → ``serialize(fields="all")``).  It is **nested format**:
133 top-level entries, 474 flat nodes including composed children
(concepts, methods, attributes, and the P1 residual
``SourceFragmentNode``s), with provenance tags ``as-built`` and
``dependency``.

This suite is the as-built "regenerate in place" proof (spec D5) on a
real one-hop graph: the planner keeps ``FileNode.path`` verbatim, so
codegen re-emits the 14 cpp-sqlite files at their original
``tests/fixtures/cpp-sqlite/...`` locations plus one shell per external
one-hop dependency (boost / spdlog / sqlite3 — absolute conan-cache
paths baked into the fixture, emitted as near-empty guards).

``TestImplementationExport`` consumes the **implementation export**
(``cpp_sqlite_one_hop_impl.json`` — the same graph serialized with
``export_implementation=True``, so MethodNodes carry their implementation
``body``/``body_file`` and INCLUDES edges carry the include spelling) and
asserts codegen reconstructs the 16 cpp-sqlite sources *semantically*
(Jinja templates populated from the graph) — measuring byte-for-byte
fidelity against the committed copies under ``cpp_sqlite_impl_src/``
(the current drift is pinned in ``test_semantic_reconstruction_drift_pinned``).

Counts below are pinned to the committed fixture.  When the sister repo
regenerates the JSON, ``scripts/sync_codegen_fixtures.py check`` flags
drift and ``pull`` adopts the new canonical — re-pin the counts then.
"""

from __future__ import annotations

import json
from pathlib import Path

from codegraph.codegen import CodegenResult, generate, generate_from_layer_graph
from codegraph.codegen.cli import main
from codegraph.graph import LayerGraph

FIXTURE = (
    Path(__file__).resolve().parent.parent / "unit_test_data"
    / "cpp_sqlite_one_hop.json"
)

#: The implementation-bearing export (``export_implementation=True``): the
#: same as-built graph, with each MethodNode's implementation
#: ``body``/``body_file`` and the include spelling on INCLUDES edges.  Produced by the sister
#: repo's ``tests/cpp_sqlite_integration/`` suite with the export flag set.
IMPL_FIXTURE = (
    Path(__file__).resolve().parent.parent / "unit_test_data"
    / "cpp_sqlite_one_hop_impl.json"
)

#: The original cpp-sqlite source files (committed copies of
#: ``doxygen-dependency-parser/tests/fixtures/cpp-sqlite/``) the
#: byte-for-byte suite regenerates and compares against.
IMPL_SRC = (
    Path(__file__).resolve().parent.parent / "unit_test_data"
    / "cpp_sqlite_impl_src"
)

#: Pinned facts for the regenerated fixture (2026-08-16, P1
#: residual-fragment work): 133 top-level entries, 474 flat nodes
#: (including 25 SourceFragmentNodes), 100 as-built + 33 dependency roots.
TOP_LEVEL = 133
NESTED_TOTAL = 474
PROJECT_FILES = 14
EXTERNAL_FILES = 6
#: Node kinds orphaned at root (no COMPOSES parent in the one-hop export).
SKIPPED = {"FunctionNode": 18, "AttributeNode": 1, "MethodNode": 6}

#: The 14 project files planned verbatim from their FileNode paths.
EXPECTED_PROJECT_FILES = [
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDAOBase.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.cpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.cpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBRepeatedFieldTransferObject.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.cpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.cpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.hpp",
    "tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/StringUtils.hpp",
]


def _load() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _nested_total(entries: list[dict]) -> int:
    total = 0

    def walk(items: list[dict]) -> None:
        nonlocal total
        for entry in items:
            total += 1
            walk(entry.get("composes", []))

    walk(entries)
    return total


class TestFixture:
    def test_is_nested_as_built_graph(self):
        data = _load()
        assert any("composes" in entry for entry in data)
        assert len(data) == TOP_LEVEL
        assert _nested_total(data) == NESTED_TOTAL
        # Mixed provenance: project nodes are ``as-built``; the 33
        # external one-hop deps (sqlite3 C API + boost/spdlog files,
        # namespaces, and their members) carry ``dependency``.
        tags = {tag for entry in data for tag in entry["tags"]}
        assert tags == {"as-built", "dependency"}
        assert sum("as-built" in e["tags"] for e in data) == 100
        assert sum("dependency" in e["tags"] for e in data) == 33

    def test_deserializes_to_as_built_layer_graph(self):
        graph = LayerGraph.deserialize(_load())
        assert graph.tags == frozenset({"as-built"})
        assert len(graph.entries) == TOP_LEVEL
        # The one-hop export's 30 raw parameter entries (type = bare C++
        # type name, kind = "parameter") land at root as ParameterNodes.
        parameter_roots = sum(
            1 for e in graph.entries.values() if type(e.node).__name__ == "ParameterNode"
        )
        assert parameter_roots == 30


class TestGenerate:
    def test_renders_project_tree_verbatim(self):
        """D5 as-built passthrough: FileNode.path wins — the cpp-sqlite
        tree (14 production files + the two gtest files) is regenerated at
        its original fixture locations, plus one file per TestNode."""
        result = generate(_load())
        assert isinstance(result, CodegenResult)
        assert len(result.files) == 48
        assert result.graph_tags == frozenset({"as-built"})
        project = {p for p in result.files if p.startswith("tests/fixtures/")}
        assert set(EXPECTED_PROJECT_FILES) <= project
        assert "tests/fixtures/cpp-sqlite/cpp_sqlite/test/testDatabase.cpp" in project
        assert all(text.endswith("\n") for text in result.files.values())

    def test_external_deps_render_one_shell_each(self):
        """One-hop external deps (boost/spdlog/sqlite3, absolute conan
        paths baked into the fixture) plan as near-empty guards."""
        result = generate(_load())
        external = [p for p in result.files if p.startswith("/")]
        assert len(external) == EXTERNAL_FILES
        for path in external:
            text = result.files[path]
            assert text.startswith("#ifndef ")
            assert "// GENERATED by codegraph-codegen" not in text
            assert "namespace" not in text  # opaque shell — no project body
            assert text.endswith("\n")

    def test_rendering_is_deterministic(self):
        a = generate(_load())
        b = generate(_load())
        assert a.files == b.files

    def test_generate_from_layer_graph_equivalent(self):
        graph = LayerGraph.deserialize(_load())
        assert generate_from_layer_graph(graph).files == generate(_load()).files

    def test_orphaned_members_skipped_with_warning(self):
        """D10: the sqlite3 C API functions, one attribute, and the
        external boost/spdlog members are root orphans — the one-hop
        export carries no COMPOSES parent for them."""
        result = generate(_load())
        assert result.skipped == SKIPPED
        assert any(
            w.startswith("orphaned members skipped (D10): 25 — ")
            for w in result.warnings
        )
        assert "FunctionNode=18" in result.summarize()


class TestRenderedContent:
    """Spot-check the regenerated cpp-sqlite tree (machine-independent
    invariants; absolute conan paths are fixture-baked and asserted
    separately above)."""

    def test_header_guard_namespace_and_docs(self):
        text = generate(_load()).files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp"
        ]
        # as-built discipline: the guard comes from the indexed include_guard
        # (constraint 8 — never synthesized from the path)
        assert "#ifndef BASE_TRANSFER_OBJECT_HPP" in text
        assert "namespace cpp_sqlite {" in text
        assert "struct BaseTransferObject {" in text
        assert "\\brief The fundamental transfer object for SQL operations" in text

    def test_concepts_render_from_initializer(self):
        text = generate(_load()).files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"
        ]
        # the committed one-hop fixture predates the source-spelled concept
        # capture (WP2.4), so the doxygen-collapsed initializer renders
        assert "template<typename T> concept TransferObject = " in text
        assert "std::derived_from<T, BaseTransferObject >" in text

    def test_class_members_render_as_declarations(self):
        """Composed members render as real declarations (D11 kind aliases
        map the doxygen as-built vocabulary — MethodNode kind="function",
        AttributeNode kind="variable" — onto the pack's templates)."""
        text = generate(_load()).files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
        ]
        assert "class Database {" in text
        assert "Database(std::string url, bool allowWrite," in text
        assert "// TODO(codegen): unsupported" not in text
        # public methods + private attributes grouped by visibility
        assert "    public:" in text
        assert "    private:" in text
        assert "std::unique_ptr<sqlite3, decltype(&sqlite3_close)> db_;" in text

    def test_source_files_render_includes_only(self):
        text = generate(_load()).files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.cpp"
        ]
        # as-built include discipline: the indexed spelling wins (WP3.3),
        # never a path-derived fallback
        assert text == (
            '#include "cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp"\n'
        )

    def test_documentation_flows_for_every_element(self):
        """Doc comments reach the generated tree.  As-built files preserve
        the source documentation syntax (the verbatim ``/*!`` block,
        WP3.2) rather than a normalized ``///`` reflow."""
        result = generate(_load())
        fk = result.files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp"
        ]
        # class brief survives in the verbatim source documentation
        assert "\\brief ForeignKey<T> stores only the ID of a related object T" in fk
        assert "unset FK (id = 0)" in fk
        assert "\\brief Construct from an ID" in fk
        assert "\\brief Check if this FK is set (non-zero ID)" in fk
        # attribute doc — the regenerated fixture carries the verbatim
        # ``//!`` source documentation (P1 plain-comment attachment), so
        # it renders verbatim rather than as a normalized ``///`` reflow
        assert "//! The ID of the referenced object" in fk

    def test_no_provenance_markers_by_default(self):
        """R7 markers are opt-in; default output is byte-clean of
        ``// @codegraph uid:`` lines (they break fidelity with
        hand-written source and verify() never reads them)."""
        result = generate(_load())
        assert all("@codegraph uid" not in t for t in result.files.values())
        marked = generate(_load(), emit_markers=True)
        assert any("@codegraph uid" in t for t in marked.files.values())

    def test_output_dir_writes_tree(self, tmp_path: Path):
        generate(_load(), output_dir=tmp_path)
        for rel in EXPECTED_PROJECT_FILES:
            assert (tmp_path / rel).is_file()
        assert (tmp_path / "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp").exists()

    def test_output_dir_never_escapes_root(self, tmp_path: Path):
        """Absolute planned paths (external one-hop deps) must not be
        written outside the output root — they'd overwrite the real file
        (e.g. a conan-cache header).  They are skipped with a warning."""
        result = generate(_load(), output_dir=tmp_path)
        assert any(
            "absolute-path file(s) not written" in w for w in result.warnings
        )
        # No planned absolute path was clobbered (on this machine the
        # targets exist as real third-party headers; the guard must leave
        # them untouched — never a generated shell).
        for path in result.files:
            if path.startswith("/") and Path(path).exists():
                assert not Path(path).read_text().startswith(
                    "// GENERATED by codegraph-codegen"
                )
        # The sandboxed tree holds only the project files (+ gtest files +
        # one file per TestNode in the fixture).
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert len(written) == 42


class TestImplementationExport:
    """Semantic reconstruction from the implementation export.

    The impl fixture (``cpp_sqlite_one_hop_impl.json``) is the as-built
    graph exported with ``export_implementation=True``: every MethodNode
    carries its implementation ``body``/``body_file`` (extracted by the
    parser from the source's Doxygen body line range) and INCLUDES edges
    carry the include spelling.  Codegen populates Jinja templates from
    this graph representation — it does NOT regurgitate file text.

    Byte-for-byte fidelity is the goal being measured toward;
    ``test_semantic_reconstruction_drift_pinned`` pins the current drift
    so each fidelity fix is an explicit, failing reminder to tighten the
    pin.
    """

    #: Project files the impl export regenerates (the 14 src/utils sources
    #: + the two gtest files).
    PROJECT_FILES = sorted({
        e["path"] for e in json.loads(IMPL_FIXTURE.read_text(encoding="utf-8"))
        if e["type"] == "FileNode"
        and e["path"].startswith("tests/fixtures/cpp-sqlite/")
    })

    @staticmethod
    def _nested(entries):
        for e in entries:
            yield e
            for c in e.get("composes", []):
                yield from TestImplementationExport._nested([c])

    def test_fixture_carries_implementation(self):
        """The impl export carries method bodies (not verbatim file text)
        and the include spelling on INCLUDES edges."""
        data = json.loads(IMPL_FIXTURE.read_text(encoding="utf-8"))
        files = [e for e in data if e["type"] == "FileNode"]
        project = [e for e in files if e["path"].startswith("tests/fixtures/cpp-sqlite/")]
        assert len(project) == len(self.PROJECT_FILES) == 16
        # no FileNode carries raw source text — the implementation lives
        # on MethodNode.body, the semantic raw material for codegen
        assert all("source_text" not in e for e in project)
        methods = [e for e in self._nested(data) if e["type"] == "MethodNode"]
        with_body = [e for e in methods if e.get("body")]
        assert len(with_body) > 0
        assert all(e.get("body_file") for e in with_body)
        # includes spelling survives on INCLUDES edges
        spelled = sum(
            1 for e in project
            for edge in e.get("edges", [])
            if edge["relation_type"] == "INCLUDES" and edge.get("include")
        )
        assert spelled > 0
        # the plain one-hop fixture stays lean (no body)
        plain = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert all(
            "body" not in e
            for e in self._nested(plain)
            if e["type"] == "MethodNode"
        )

    def test_codegen_saves_every_project_file(self):
        """Every project file is regenerated (completeness), even though
        the semantic reconstruction is not yet byte-for-byte."""
        result = generate(_load_impl())
        assert set(result.files) >= set(self.PROJECT_FILES)

    def test_semantic_reconstruction_drift_pinned(self):
        """The exposed-issues pin: every project file currently differs
        from the original (provenance header, guard naming, doc-comment
        re-wrap, system includes, brace/indent style, …).  Shrink this
        pin as fidelity gaps are closed."""
        result = generate(_load_impl())
        drift = [
            rel for rel in self.PROJECT_FILES
            if result.files.get(rel) is None
            or result.files[rel].encode("utf-8") != (IMPL_SRC / rel).read_bytes()
        ]
        assert drift == self.PROJECT_FILES, (
            f"semantic-reconstruction pin changed — drift is now "
            f"{len(drift)}/{len(self.PROJECT_FILES)} files (was all "
            f"{len(self.PROJECT_FILES)}); update this pin:\n{drift}"
        )

    def test_bodies_reach_cpp_output(self):
        """Method bodies flow from the graph into the regenerated .cpp
        (Jinja reconstruction, not verbatim passthrough)."""
        result = generate(_load_impl())
        db = result.files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.cpp"
        ]
        assert "Database::Database(" in db
        assert "sqlite3_open_v2" in db
        assert "TODO(codegen): implementation body" not in db

    def test_includes_reconstructed_from_edge_spelling(self):
        """Includes come from the indexed ordered include list (WP3.3):
        system headers, local project headers, and sqlite3.h all render as
        written — the include discipline gap is closed."""
        result = generate(_load_impl())
        dbhpp = result.files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
        ]
        assert '#include "cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp"' in dbhpp
        assert '#include "sqlite3.h"' in dbhpp
        assert "#include <any>" in dbhpp
        assert "#include <boost/unordered_map.hpp>" in dbhpp

    def test_rendering_is_deterministic(self):
        a = generate(_load_impl())
        b = generate(_load_impl())
        assert a.files == b.files

    def test_saved_output_is_in_sync(self):
        """The viewable full-fidelity tree (``cpp_sqlite_generated/``) matches
        fresh codegen output.  It is refreshed by the integration round trip
        (``tests/codegen/test_cpp_sqlite_impl_roundtrip.py``) — if that suite
        is skipped (no doxygen-index) or a fixture/codegen change drifts the
        artifact, this test flags it."""
        generated_root = (
            Path(__file__).resolve().parent.parent / "unit_test_data"
            / "cpp_sqlite_generated"
        )
        if not (generated_root / self.PROJECT_FILES[0]).is_file():
            return  # local artifact not materialized — nothing to pin
        result = generate(_load_impl())
        drift = [
            rel for rel in self.PROJECT_FILES
            if (generated_root / rel).read_bytes() != result.files.get(rel, "").encode("utf-8")
        ]
        assert not drift, (
            f"saved output drifted for {drift} — run the integration round trip "
            "(tests/codegen/test_cpp_sqlite_impl_roundtrip.py) to refresh it"
        )


def _load_impl() -> list[dict]:
    return json.loads(IMPL_FIXTURE.read_text(encoding="utf-8"))


class TestCli:
    def test_dry_run_plans_one_hop_graph(self, capsys):
        rc = main(["--input", str(FIXTURE), "--dry-run"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp" in captured.out
        assert "48 file(s); skipped: AttributeNode=1, FunctionNode=18, MethodNode=6" in captured.out
        assert "orphaned members skipped (D10)" in captured.err
