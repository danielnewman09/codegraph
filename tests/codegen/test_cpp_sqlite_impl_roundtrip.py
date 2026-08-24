"""Full round trip: index the real project → codegen → save → compare.

The loop this suite runs end-to-end (the three steps the round-trip
must exercise):

    cpp-sqlite source ──doxygen-index──▶ as-built graph ──export_implementation──▶
        ▲                                                                        │
        └──────────── byte-compare ◀──────── codegen(output_dir) ◀───────────────┘

1. **index the project** — doxygen-index ingests the committed source
   copies (``cpp_sqlite_impl_src/``) into a temp sqlite backend; the
   parser extracts each method's implementation body (``body``/``body_file``)
   so the graph carries the semantic raw material codegen needs;
2. **codegen the project** — the as-built graph is exported with
   ``export_implementation=True`` and ``generate(output_dir=...)`` SAVES
   the generated tree to a directory (mirrored to the viewable
   ``cpp_sqlite_generated/`` artifact);
3. **match the existing code** — the 14 production files in the declared
   manifest are canonicalized with pinned clang-format 17 configuration
   and compared against the original source.  The two GoogleTest files
   remain available as the later behavioral oracle but are outside the
   Priority 1 source-generation contract.

Required ``doxygen-index``, the synced source copies, and clang-format 17 are
exercised directly; missing prerequisites fail the integration suite.
``unit_test_data/`` is gitignored and synced from the sister repo via
``scripts/sync_codegen_fixtures.py``. Marked ``integration`` — full-stack
(external tool + sqlite backend).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from codegraph.codegen import generate
from codegraph.codegen.fidelity import compare_manifest
from codegraph.graph import LayerGraph
from tests.codegen.external_tools import (
    ExternalToolError,
    run_index,
)

_HERE = Path(__file__).resolve().parent.parent / "unit_test_data"

#: The committed source copies (and their doxygen-index config) that the
#: round trip indexes.  The index runs with cwd at this root so the
#: resulting FileNode paths are the canonical ``tests/fixtures/...``
#: layout (the planner mirrors it verbatim on regeneration).
IMPL_SRC = _HERE / "cpp_sqlite_impl_src"
PROJECT_DIR = "tests/fixtures/cpp-sqlite"

#: The viewable regenerated tree (gitignored local artifact).
ARTIFACT = _HERE / "cpp_sqlite_generated"

MANIFEST_FILE = Path(__file__).with_name("cpp_sqlite_roundtrip_manifest.txt")
FORMAT_CONFIG = Path(__file__).with_name("cpp_sqlite.clang-format")
CLANG_FORMAT_MAJOR = 17


def _load_manifest() -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


PRODUCTION_FILES = _load_manifest()

_LOCAL_DOXYGEN_INDEX = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "doxygen-index"
_DOXYGEN_INDEX = shutil.which("doxygen-index") or (
    str(_LOCAL_DOXYGEN_INDEX) if _LOCAL_DOXYGEN_INDEX.is_file() else None
)


def _find_clang_format() -> str | None:
    override = os.environ.get("CLANG_FORMAT")
    if override:
        return override
    on_path = shutil.which("clang-format")
    if on_path:
        return on_path
    xcode = Path(
        "/Applications/Xcode.app/Contents/Developer/Toolchains/"
        "XcodeDefault.xctoolchain/usr/bin/clang-format"
    )
    return str(xcode) if xcode.is_file() else None


_CLANG_FORMAT = _find_clang_format()

pytestmark = [pytest.mark.integration]


def _canonical_cpp(path: Path, content: bytes) -> bytes:
    proc = subprocess.run(
        [
            _CLANG_FORMAT,
            f"--style=file:{FORMAT_CONFIG}",
            f"--assume-filename={path}",
        ],
        input=content,
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"clang-format failed for {path}:\n"
        f"{proc.stderr.decode(errors='replace')}"
    )
    # Canonical source policy: LF with exactly one final newline. clang-format
    # preserves the input's missing final newline, so make this boundary rule
    # explicit rather than treating it as a semantic model element.
    return proc.stdout.rstrip(b"\n") + b"\n"


def _canonical_boundary(content: bytes) -> bytes:
    """Apply only the final-newline boundary half of the canonical policy.

    ``_canonical_cpp`` rstrips the clang-format output to exactly one final
    newline; ``_canonical_boundary`` applies the same boundary to a raw file
    so a source that is already clang-format-canonical apart from its missing
    final newline compares equal.  The real golden sources (read-only) end
    without a trailing newline — the boundary is explicitly not a semantic
    model element (plan constraint 4).
    """
    return content.rstrip(b"\n") + b"\n"


def _project_rels(graph) -> list[str]:
    """Project FileNode paths (``tests/fixtures/cpp-sqlite/...``)."""
    return sorted({
        getattr(e.node, "path", "")
        for e in graph._all_entries()
        if type(e.node).__name__ == "FileNode"
        and getattr(e.node, "path", "").startswith("tests/fixtures/cpp-sqlite/")
    })


def _methods(graph):
    return [
        e for e in graph._all_entries()
        if type(e.node).__name__ == "MethodNode"
    ]


# ── Work package 1: deterministic drift diagnosis ─────────────────────
#
# The final gate reports byte counts + first differing line.  These helpers
# record, per production file, the structured nodes and their owned spans,
# residual fragments, parser-reported ownership problems, and the canonical
# first-difference line so every drift can be assigned to exactly one layer
# (parser/model, persistence, planner/context, renderer, safe residual, or
# deliberate canonical-format equivalence).  All of it is test-only: the
# acceptance rule (``report.is_identical``) is unchanged.

#: Node kinds the parser owns structured source spans for (mirrors
#: Doxygen-Dependency-Parser's ``build_owned_spans`` owner set).
_SPANNED_NODE_TYPES = frozenset({
    "CompoundNode", "ClassNode", "InterfaceNode", "EnumNode",
    "UnionNode", "ConceptNode", "ModuleNode",
    "MemberNode", "MethodNode", "FunctionNode", "AttributeNode",
    "EnumValueNode", "DefineNode",
})

#: The single category every drifting file must be assigned to.
DRIFT_CATEGORIES = frozenset({
    "parser/model loss",
    "persistence/serialization loss",
    "planner/context loss",
    "renderer loss",
    "safe residual fallback",
    "deliberate canonical-format equivalence",
})

#: Current matched-file inventory (monotonic: never lower, never remove).
#: Update a file only when it genuinely becomes canonical-identical.
#: All 14 production files are canonical-identical (2026-08-16).
EXPECTED_MATCHED = frozenset({
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
})


def _parser_overlap_problems(stderr: str) -> dict[str, list[str]]:
    """Parser-reported ownership overlaps, keyed by manifest-relative path.

    The parser prints ``Warning: ownership overlap in <path>: <problem>`` to
    stderr during indexing; the fixture stashes that text on the graph.
    """
    problems: dict[str, list[str]] = {}
    for line in (stderr or "").splitlines():
        if "ownership overlap in" not in line:
            continue
        marker = "ownership overlap in "
        rest = line.split(marker, 1)[1]
        path, _, problem = rest.partition(":")
        problems.setdefault(path.strip(), []).append(problem.strip())
    return problems


def _recompute_overlap_problems(graph, file_rel: str) -> list[str]:
    """Test-local interval sweep over the graph's structured spans.

    Mirrors the parser's ``_normalize_ownership`` (identical spans merge,
    nested spans are legal, crossing spans are reported) so the inventory
    stays meaningful even when stderr is unavailable.  Only crossing
    overlaps are reported — never nesting or identical spans.
    """
    spans: list[tuple[int, int, str, str]] = []
    for entry in graph._all_entries():
        node = entry.node
        if type(node).__name__ not in _SPANNED_NODE_TYPES:
            continue
        if getattr(node, "file_path", "") != file_rel:
            continue
        start = int(getattr(node, "start_line", 0) or 0)
        end = int(getattr(node, "end_line", 0) or 0)
        if not start or not end:
            continue
        spans.append((
            start, end,
            type(node).__name__,
            getattr(node, "qualified_name", "") or getattr(node, "name", ""),
        ))
    spans.sort(key=lambda s: (s[0], s[1]))
    merged: list[tuple[int, int, str, str]] = []
    for span in spans:
        if merged and merged[-1][:2] == span[:2]:
            continue  # identical span merges (same owner info kept)
        merged.append(span)
    problems: list[str] = []
    active: list[tuple[int, int, str, str]] = []
    for start, end, ntype, owner in merged:
        active = [p for p in active if p[1] >= start]
        for pstart, pend, ptype, powner in active:
            if pend >= end:
                continue  # nested — safe
            problems.append(
                f"{ntype} '{owner}' [{start}-{end}] overlaps "
                f"{ptype} '{powner}' [{pstart}-{pend}]"
            )
        active.append((start, end, ntype, owner))
    return problems


def _declaration_lines(source_root: Path, file_rel: str) -> list[str]:
    """Golden source lines of *file_rel* (for the no-residual-invasion rule)."""
    path = source_root / file_rel
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def build_drift_inventory(
    graph,
    source_root: Path,
    save_dir: Path,
    manifest,
    *,
    normalize=None,
) -> dict[str, dict]:
    """Per-production-file deterministic drift inventory.

    Returns ``{file_rel: {...}}`` with:

    - ``structured``: indexed compounds/members and their owned spans
      (node type, qualified name, span, declaration ``line_number``);
    - ``residuals``: SourceFragmentNodes with span, placement and a short
      escaped preview, sorted by start line;
    - ``parser_problems``: ownership overlaps reported by the parser;
    - ``recomputed_problems``: crossing overlaps derived from graph spans;
    - ``first_different_line``: canonical first-difference line (None when
      the file is canonical-identical).

    Missing generated files are recorded as ``"missing": True`` and never
    passed to the normalizer.
    """
    report = compare_manifest(
        source_root, save_dir, manifest, normalize=normalize,
    )
    first_diff = {d.path: d.first_different_line for d in report.drift}
    missing = set(report.missing)
    parser_problems = _parser_overlap_problems(
        getattr(graph, "_parser_stderr", "") or ""
    )

    by_file: dict[str, dict] = {}
    for file_rel in sorted(set(manifest)):
        structured: list[dict] = []
        for entry in graph._all_entries():
            node = entry.node
            if type(node).__name__ not in _SPANNED_NODE_TYPES:
                continue
            if getattr(node, "file_path", "") != file_rel:
                continue
            structured.append({
                "node_type": type(node).__name__,
                "qualified_name": (
                    getattr(node, "qualified_name", "") or getattr(node, "name", "")
                ),
                "start_line": int(getattr(node, "start_line", 0) or 0),
                "end_line": int(getattr(node, "end_line", 0) or 0),
                "line_number": int(getattr(node, "line_number", 0) or 0),
            })
        structured.sort(key=lambda s: (s["start_line"], s["qualified_name"]))
        residuals = [
            {
                "start_line": int(entry.node.start_line or 0),
                "end_line": int(entry.node.end_line or 0),
                "placement": getattr(entry.node, "placement", "") or "",
                "preview": repr((getattr(entry.node, "text", "") or "")[:80]),
            }
            for entry in graph._all_entries()
            if type(entry.node).__name__ == "SourceFragmentNode"
            and getattr(entry.node, "file_path", "") == file_rel
        ]
        residuals.sort(key=lambda r: (r["start_line"], r["preview"]))
        by_file[file_rel] = {
            "structured": structured,
            "residuals": residuals,
            "parser_problems": parser_problems.get(file_rel, []),
            "recomputed_problems": _recompute_overlap_problems(graph, file_rel),
            "first_different_line": None if file_rel in missing
            else first_diff.get(file_rel),
            "missing": file_rel in missing,
        }
    return by_file


def _assert_no_residual_invasion(graph, source_root: Path, file_rel: str) -> None:
    """WP1 rule: no residual text contains the declaration line of an indexed
    compound or member in the same file.

    ``line_number`` is the declaration line (Doxygen location); the golden
    source line at that position is the declaration text (or its first line
    for multiline declarations).  A residual may never contain it.
    """
    source_lines = _declaration_lines(source_root, file_rel)
    declarations = {
        (int(getattr(entry.node, "line_number", 0) or 0),)
        for entry in graph._all_entries()
        if type(entry.node).__name__ in _SPANNED_NODE_TYPES
        and getattr(entry.node, "file_path", "") == file_rel
        and int(getattr(entry.node, "line_number", 0) or 0) > 0
    }
    decl_texts = [
        source_lines[line - 1].strip()
        for (line,) in declarations
        if 0 < line <= len(source_lines) and source_lines[line - 1].strip()
    ]
    for entry in graph._all_entries():
        node = entry.node
        if type(node).__name__ != "SourceFragmentNode":
            continue
        if getattr(node, "file_path", "") != file_rel:
            continue
        text = getattr(node, "text", "") or ""
        for decl in decl_texts:
            assert decl not in text, (
                f"residual in {file_rel} [{node.start_line}-{node.end_line}] "
                f"contains structured declaration line: {decl!r}"
            )


@pytest.fixture(scope="module")
def impl_graph(tmp_path_factory, conan_test_environment):
    """Step 1 — index the real cpp-sqlite source into a temp sqlite backend."""
    db_path = tmp_path_factory.mktemp("impl-rt") / "impl.sqlite3"
    out_dir = tmp_path_factory.mktemp("impl-rt-out")
    env = {
        **conan_test_environment.env,
        "CODEGRAPH_BACKEND": "sqlite",
        "SQLITE_PATH": str(db_path),
    }
    try:
        proc = run_index(
            [_DOXYGEN_INDEX, "codegraph",
             "--project-dir", PROJECT_DIR,
             "--output-dir", str(out_dir),
             "--neo4j", "--clear", "--yes"],
            cwd=IMPL_SRC,
            env=env,
        )
    except ExternalToolError as exc:
        raise AssertionError(str(exc)) from exc
    assert db_path.exists(), "doxygen-index did not write the sqlite backend"

    from codegraph.backends import get_backend, set_backend
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

    set_backend(SqliteBackend(SqliteConfig(path=str(db_path))))
    graph = LayerGraph.from_backend(get_backend(), "as-built")
    # Test-only transport: the parser's ownership diagnostics (stderr of the
    # doxygen-index process) are needed by the deterministic drift inventory.
    graph._parser_stderr = proc.stderr  # type: ignore[attr-defined]
    return graph


class TestImplRoundtrip:
    def test_fidelity_environment_is_pinned(self):
        version = subprocess.run(
            [_CLANG_FORMAT, "--version"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert f"version {CLANG_FORMAT_MAJOR}." in version, (
            f"Priority 1 requires clang-format {CLANG_FORMAT_MAJOR}; got {version}"
        )
        assert len(PRODUCTION_FILES) == 14

    def test_manifest_is_the_complete_production_tree(self):
        source_root = IMPL_SRC / PROJECT_DIR / "cpp_sqlite" / "src"
        discovered = {
            path.relative_to(IMPL_SRC).as_posix()
            for path in source_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".cpp", ".hpp"}
        }
        assert set(PRODUCTION_FILES) == discovered

    def test_golden_source_is_canonically_formatted(self):
        """The golden source is clang-format-canonical up to the final-newline
        boundary (plan constraint 4: comparison is LF plus exactly one final
        newline after canonical formatting; the boundary is not a semantic
        model element, and the read-only golden ends without one)."""
        drift = []
        for relative in PRODUCTION_FILES:
            path = IMPL_SRC / relative
            original = path.read_bytes()
            if _canonical_cpp(path, original) != _canonical_boundary(original):
                drift.append(relative)
        assert not drift, "golden source requires clang-format:\n" + "\n".join(drift)

    def test_indexing_captures_implementation(self, impl_graph):
        """Step 1 proof: the index extracts method bodies (the semantic
        implementation data), not verbatim file text, and the export flag
        is opt-in (the default export stays lean)."""
        rels = _project_rels(impl_graph)
        assert len(rels) == 16
        methods = _methods(impl_graph)
        with_body = [e for e in methods if getattr(e.node, "body", "")]
        with_body_file = [e for e in methods if getattr(e.node, "body_file", "")]
        assert len(with_body) > 0, "index captured no method bodies"
        assert all(getattr(e.node, "body_file", "") for e in with_body)
        assert len(with_body_file) >= len(with_body)
        # no FileNode carries raw source text — the "regurgitate" cheat is gone
        assert all(
            not hasattr(e.node, "source_text")
            for e in impl_graph._all_entries()
            if type(e.node).__name__ == "FileNode"
        )
        # and the export flag is opt-in: the default export strips bodies
        plain = impl_graph.serialize(fields="all")

        def walk(entries):
            for e in entries:
                yield e
                for c in e.get("composes", []):
                    yield from walk([c])

        assert all("body" not in m for m in walk(plain) if m["type"] == "MethodNode")

    def test_indexing_preserves_file_layout_metadata(self, impl_graph):
        """The as-built graph retains source layout needed for byte fidelity."""
        file_node = next(
            entry.node
            for entry in impl_graph._all_entries()
            if type(entry.node).__name__ == "FileNode"
            and getattr(entry.node, "path", "").endswith(
                "DBRepeatedFieldTransferObject.hpp"
            )
        )
        assert file_node.include_directives == [
            "<vector>", "", "<boost/describe.hpp>",
            "<boost/describe/class.hpp>", "",
            '"cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"',
        ]
        assert file_node.namespace_leading_blank_lines == 1
        assert file_node.namespace_trailing_blank_lines == 2
        from codegraph.codegen.context import CodegenContextBuilder

        context = CodegenContextBuilder().build(impl_graph).files[file_node.path]
        assert context["namespace_leading_blank_lines"] == 1
        assert context["namespace_trailing_blank_lines"] == 2
        from codegraph.codegen.pack import TemplatePack

        pack = TemplatePack(language="cpp")
        document = pack.render_document(context)
        assert "};\n\n\n} // namespace cpp_sqlite" in document
        rendered = pack.render_file(context)
        assert "};\n\n\n} // namespace cpp_sqlite" in rendered

    def test_codegen_saves_every_project_file(self, impl_graph, tmp_path_factory):
        """Step 2 — export with implementation, codegen SAVES the tree to
        the output directory (every project file is written)."""
        save_dir = tmp_path_factory.mktemp("impl-generated")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        result = generate(data, output_dir=save_dir)
        missing = [rel for rel in PRODUCTION_FILES if not (save_dir / rel).is_file()]
        assert not missing, f"codegen did not save:\n{missing}"
        assert len(result.files) >= len(PRODUCTION_FILES)

    def test_codegen_uses_semantic_bodies(self, impl_graph, tmp_path_factory):
        """The generated .cpp files are populated from the graph's method
        bodies (Jinja), not from verbatim file text."""
        save_dir = tmp_path_factory.mktemp("impl-semantic")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        result = generate(data, output_dir=save_dir)
        db = (save_dir / "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.cpp")
        text = db.read_text(encoding="utf-8")
        assert "Database::Database(" in text  # out-of-line body reached the .cpp
        assert "sqlite3_open_v2" in text      # body content, not a stub
        assert "TODO(codegen): implementation body" not in text

    def test_canonical_byte_identity(self, impl_graph, tmp_path_factory):
        """The Priority 1 gate: every production file is byte-identical
        after applying the pinned canonical formatter to both boundaries."""
        save_dir = tmp_path_factory.mktemp("impl-drift")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        generate(data, output_dir=save_dir)
        report = compare_manifest(
            IMPL_SRC,
            save_dir,
            PRODUCTION_FILES,
            normalize=_canonical_cpp,
        )
        assert report.is_identical, report.describe()

    def test_viewable_artifact_refreshed(self, impl_graph, tmp_path_factory):
        """The viewable ``cpp_sqlite_generated/`` tree is mirrored from
        the committed impl fixture (deterministic) so the fast suite's
        ``test_saved_output_is_in_sync`` pin holds.  Fresh-index output
        can differ in member ORDER across index runs (sqlite row order
        is not stable) — the artifact is pinned to the committed export
        to stay byte-stable."""
        import json as _json

        impl_json = (IMPL_SRC.parent / "cpp_sqlite_one_hop_impl.json").read_text(
            encoding="utf-8"
        )
        save_dir = tmp_path_factory.mktemp("impl-generated-mirror")
        generate(_json.loads(impl_json), output_dir=save_dir)

        if ARTIFACT.exists():
            shutil.rmtree(ARTIFACT)
        shutil.copytree(save_dir / "tests", ARTIFACT / "tests")
        rels = _project_rels(impl_graph)
        for rel in rels:
            assert (ARTIFACT / rel).is_file()


class TestDriftInventory:
    """Work package 1 — deterministic drift diagnosis.

    These tests never weaken the final acceptance gate; they make the
    mechanical implementation loop deterministic by recording, per
    production file, the structured nodes + spans, residuals, parser
    problems and canonical first-difference line.
    """

    def _inventory(self, impl_graph, tmp_path_factory):
        save_dir = tmp_path_factory.mktemp("impl-inventory")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        generate(data, output_dir=save_dir)
        return build_drift_inventory(
            impl_graph,
            IMPL_SRC,
            save_dir,
            PRODUCTION_FILES,
            normalize=_canonical_cpp,
        )

    def test_inventory_covers_every_production_file(self, impl_graph, tmp_path_factory):
        inventory = self._inventory(impl_graph, tmp_path_factory)
        assert set(inventory) == set(PRODUCTION_FILES)
        for file_rel, info in inventory.items():
            assert not info["missing"], f"{file_rel} missing from generated tree"
            assert "structured" in info and "residuals" in info
            assert "parser_problems" in info and "recomputed_problems" in info
            assert "first_different_line" in info

    def test_inventory_is_deterministic_for_drifting_files(
        self, impl_graph, tmp_path_factory
    ):
        """Every drifting file's inventory is complete and stable: the
        residual list is line-sorted, parser problems are reported verbatim,
        and the recomputed sweep agrees with the parser report."""
        inventory = self._inventory(impl_graph, tmp_path_factory)
        drifting = [
            rel for rel, info in inventory.items()
            if info["first_different_line"] is not None
        ]
        # Every production file is either canonical-matched or drifting —
        # the inventory must account for all 14 (monotonic progress is
        # enforced by ``EXPECTED_MATCHED`` in the progress test).
        matched = [rel for rel, info in inventory.items()
                   if info["first_different_line"] is None]
        assert len(drifting) + len(matched) == len(PRODUCTION_FILES)
        assert len(matched) >= len(EXPECTED_MATCHED)
        for file_rel in drifting:
            info = inventory[file_rel]
            prev_start = 0
            for residual in info["residuals"]:
                assert residual["start_line"] >= prev_start
                prev_start = residual["start_line"]
                assert residual["preview"].startswith(("'", '"'))            # Parser-reported problems and the graph-derived sweep must agree
            # on the crossing overlaps for this file (both deterministic).
            assert (
                sorted(info["parser_problems"]) == sorted(info["recomputed_problems"])
            ), file_rel

    def test_no_residual_contains_structured_declaration(
        self, impl_graph, tmp_path_factory
    ):
        """WP1 rule: residual fragments never swallow a structured
        declaration — every indexed compound/member line stays out of every
        residual in the same file."""
        inventory = self._inventory(impl_graph, tmp_path_factory)
        for file_rel in inventory:
            _assert_no_residual_invasion(impl_graph, IMPL_SRC, file_rel)

    def test_matched_inventory_never_regresses(self, impl_graph, tmp_path_factory):
        """Monotonic progress: the canonical-matched set is a superset of the
        committed expectation.  Update ``EXPECTED_MATCHED`` only when a file
        genuinely becomes identical; never lower it."""
        save_dir = tmp_path_factory.mktemp("impl-progress")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        generate(data, output_dir=save_dir)
        report = compare_manifest(
            IMPL_SRC,
            save_dir,
            PRODUCTION_FILES,
            normalize=_canonical_cpp,
        )
        assert EXPECTED_MATCHED.issubset(set(report.matched)), (
            "matched inventory regressed:\n"
            + "\n".join(sorted(EXPECTED_MATCHED - set(report.matched)))
        )
        assert len(report.matched) >= len(EXPECTED_MATCHED)
