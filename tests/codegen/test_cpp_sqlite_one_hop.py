"""Codegen run against the sister repo's cpp-sqlite one-hop as-built graph.

The fixture ``tests/unit_test_data/cpp_sqlite_one_hop.json`` is the
serialized as-built LayerGraph the sister repo
(``doxygen-dependency-parser``) exports from its cpp-sqlite fixture
project (``tests/cpp_sqlite_integration/`` → ``LayerGraph.from_backend(
"as-built")`` → ``serialize(fields="all")``).  It is **nested format**:
74 top-level entries, 205 nodes including composed children (concepts,
methods, attributes), with provenance tag ``as-built``.

This suite is the as-built "regenerate in place" proof (spec D5) on a
real one-hop graph: the planner keeps ``FileNode.path`` verbatim, so
codegen re-emits the 14 cpp-sqlite files at their original
``tests/fixtures/cpp-sqlite/...`` locations plus one shell per external
one-hop dependency (boost / spdlog / sqlite3 — absolute conan-cache
paths baked into the fixture, emitted as near-empty guards).

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

#: Pinned facts for the committed fixture (74 top-level / 205 nested nodes).
TOP_LEVEL = 74
NESTED_TOTAL = 205
PROJECT_FILES = 14
EXTERNAL_FILES = 6
SKIPPED = {"FunctionNode": 18, "AttributeNode": 1}

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
        # Mixed provenance: project nodes are ``as-built``; the 27
        # external one-hop deps (sqlite3 C API + boost/spdlog files &
        # namespaces) carry ``dependency``.
        tags = {tag for entry in data for tag in entry["tags"]}
        assert tags == {"as-built", "dependency"}
        assert sum("as-built" in e["tags"] for e in data) == TOP_LEVEL - 27
        assert sum("dependency" in e["tags"] for e in data) == 27

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
        tree is regenerated at its original fixture locations."""
        result = generate(_load())
        assert isinstance(result, CodegenResult)
        assert len(result.files) == PROJECT_FILES + EXTERNAL_FILES
        assert result.graph_tags == frozenset({"as-built"})
        project = {p for p in result.files if p.startswith("tests/fixtures/")}
        assert project == set(EXPECTED_PROJECT_FILES)
        assert all(text.endswith("\n") for text in result.files.values())

    def test_external_deps_render_one_shell_each(self):
        """One-hop external deps (boost/spdlog/sqlite3, absolute conan
        paths baked into the fixture) plan as near-empty guards."""
        result = generate(_load())
        external = [p for p in result.files if p.startswith("/")]
        assert len(external) == EXTERNAL_FILES
        for path in external:
            text = result.files[path]
            assert text.startswith("// GENERATED by codegraph-codegen")
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
        """D10: the sqlite3 C API functions (and one attribute) are root
        orphans — the one-hop export carries no COMPOSES parent for them."""
        result = generate(_load())
        assert result.skipped == SKIPPED
        assert any(
            w.startswith("orphaned members skipped (D10): 19 — sqlite3,")
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
        assert "TESTS_FIXTURES_CPP_SQLITE_CPP_SQLITE_SRC_CPP_SQLITE_DBBASETRANSFEROBJECT_HPP" in text
        assert "namespace cpp_sqlite {" in text
        assert "struct BaseTransferObject {" in text
        assert "The fundamental transfer object for SQL operations." in text

    def test_concepts_render_from_initializer(self):
        text = generate(_load()).files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"
        ]
        assert (
            "template<typename T> concept TransferObject = "
            "std::derived_from<T, BaseTransferObject >" in text
        )
        # D6: the concept whose initializer carries embedded comments is
        # deliberately not emitted — the design-data defect is surfaced.
        assert "initializer contains embedded comments — not emitted" in text

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
        assert text == (
            "// GENERATED by codegraph-codegen — do not edit\n"
            '#include "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/'
            'DBDataAccessObject.hpp"\n'
        )

    def test_documentation_flows_for_every_element(self):
        """brief/detailed descriptions reach the generated ``///`` blocks
        for classes, methods, and attributes (wrapped at ~78 cols)."""
        result = generate(_load())
        fk = result.files[
            "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp"
        ]
        # class brief + wrapped detailed
        assert "/// ForeignKey<T> stores only the ID of a related object T." in fk
        assert "/// This allows lazy loading - the full object is not loaded from the" in fk
        # method brief
        assert "/// Default constructor - creates unset FK (id = 0)." in fk
        assert "/// Construct from an ID." in fk
        assert "/// Check if this FK is set (non-zero ID)." in fk
        # attribute brief
        assert "/// The ID of the referenced object." in fk
        # wrapped lines stay within the doc width (78 content + indent/prefix)
        for line in fk.splitlines():
            if line.strip().startswith("///"):
                assert len(line) <= 90, line

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
        # The sandboxed tree holds only the project files.
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert len(written) == PROJECT_FILES


class TestCli:
    def test_dry_run_plans_one_hop_graph(self, capsys):
        rc = main(["--input", str(FIXTURE), "--dry-run"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp" in captured.out
        assert "20 file(s); skipped: AttributeNode=1, FunctionNode=18" in captured.out
        assert "orphaned members skipped (D10)" in captured.err
