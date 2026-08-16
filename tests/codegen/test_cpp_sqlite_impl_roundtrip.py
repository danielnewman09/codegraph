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

Skipped when ``doxygen-index`` is unavailable or the source copies are
not materialized (``unit_test_data/`` is gitignored — synced from the
sister repo via ``scripts/sync_codegen_fixtures.py``).  Marked
``integration`` — full-stack (external tool + sqlite backend).
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

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_DOXYGEN_INDEX is None, reason="doxygen-index not on PATH"),
    pytest.mark.skipif(
        not (IMPL_SRC / PROJECT_DIR / "cpp_sqlite" / "src").is_dir(),
        reason="cpp-sqlite source copies not materialized "
               "(run scripts/sync_codegen_fixtures.py pull)",
    ),
    pytest.mark.skipif(
        not (IMPL_SRC / PROJECT_DIR / ".doxygen-index.toml").is_file(),
        reason="cpp-sqlite index config missing from source copies",
    ),
    pytest.mark.skipif(
        _CLANG_FORMAT is None,
        reason="clang-format 17 is required for the byte-fidelity contract",
    ),
]


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


@pytest.fixture(scope="module")
def impl_graph(tmp_path_factory):
    """Step 1 — index the real cpp-sqlite source into a temp sqlite backend."""
    db_path = tmp_path_factory.mktemp("impl-rt") / "impl.sqlite3"
    out_dir = tmp_path_factory.mktemp("impl-rt-out")
    env = {**os.environ, "CODEGRAPH_BACKEND": "sqlite", "SQLITE_PATH": str(db_path)}
    proc = subprocess.run(
        [_DOXYGEN_INDEX, "codegraph",
         "--project-dir", PROJECT_DIR,
         "--output-dir", str(out_dir),
         "--neo4j", "--clear", "--yes"],
        cwd=IMPL_SRC,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"doxygen-index failed:\n{proc.stderr[-2000:]}"
    assert db_path.exists(), "doxygen-index did not write the sqlite backend"

    from codegraph.backends import get_backend, set_backend
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

    set_backend(SqliteBackend(SqliteConfig(path=str(db_path))))
    return LayerGraph.from_backend(get_backend(), "as-built")


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
        drift = []
        for relative in PRODUCTION_FILES:
            path = IMPL_SRC / relative
            original = path.read_bytes()
            if _canonical_cpp(path, original) != original:
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
