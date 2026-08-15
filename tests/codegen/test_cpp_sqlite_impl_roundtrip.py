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
3. **match the existing code** — every saved file is compared against
   the original source.  This is the *semantic* reconstruction: codegen
   populates Jinja templates from the CodeGraphNode representation, not
   from verbatim file text.  Byte-for-byte fidelity is the goal the
   suite measures toward; ``test_byte_fidelity_gaps_pinned`` pins the
   current drift so any regression (or improvement) is explicit.

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

_DOXYGEN_INDEX = shutil.which("doxygen-index")

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
]


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

    def test_codegen_saves_every_project_file(self, impl_graph, tmp_path_factory):
        """Step 2 — export with implementation, codegen SAVES the tree to
        the output directory (every project file is written)."""
        save_dir = tmp_path_factory.mktemp("impl-generated")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        result = generate(data, output_dir=save_dir)
        rels = _project_rels(impl_graph)
        missing = [rel for rel in rels if not (save_dir / rel).is_file()]
        assert not missing, f"codegen did not save:\n{missing}"
        assert len(result.files) >= len(rels)

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

    def test_byte_fidelity_gaps_pinned(self, impl_graph, tmp_path_factory):
        """Step 3 — byte-compare against the original sources.

        This is the *exposed-issues* pin: the semantic reconstruction is
        not yet byte-for-byte.  Every project file currently differs
        (provenance header, guard naming, doc-comment re-wrap, system
        includes, brace/indent style, …).  As those gaps are fixed, this
        assertion must be tightened — the drift set should shrink, and
        this test will fail to remind us to update the pin.
        """
        save_dir = tmp_path_factory.mktemp("impl-drift")
        data = impl_graph.serialize(fields="all", export_implementation=True)
        generate(data, output_dir=save_dir)
        rels = _project_rels(impl_graph)
        drift = [
            rel for rel in rels
            if (save_dir / rel).read_bytes() != (IMPL_SRC / rel).read_bytes()
        ]
        assert drift == rels, (
            f"byte-fidelity pin changed — drift is now {len(drift)}/{len(rels)} "
            f"files (was all {len(rels)}); update this pin:\n{drift}"
        )

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
