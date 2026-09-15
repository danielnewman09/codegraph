"""Compact residual-fragment fidelity gate (plan Phase 4.2/4.3).

The fixture ``tests/codegen/fixtures/source_fragments/`` mixes structured
declarations (a documented class, methods, attributes) with unmodeled
constructs that MUST survive as ``SourceFragmentNode`` residuals — a
forward declaration, a namespace-level ``using`` alias, and their doc
comments.  The loop:

    fixture ──index(EXTRACT_ONLY)──▶ as-built graph ──serialize──▶ generate ──▶
        ▲                                                             │
        └──────────── canonical byte-compare (clang-format) ◀──────────┘

Asserts:

* the residual inventory is deterministic (exact fragments, texts,
  locations, placements);
* ordinary structured code never appears inside a fragment;
* the canonical generated tree is byte-identical to the fixture source
  (header and .cpp — the .cpp exercises the implementation-body path
  alongside fragments).

Requires ``doxygen`` and clang-format 17.  Marked ``integration`` — full-stack
external-tool gate, ~1s.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from codegraph.codegen import generate, index_generated_tree
from codegraph.codegen.fidelity import compare_manifest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "source_fragments"

#: Deterministic residual inventory for the committed fixture.  Line numbers
#: are 1-based inclusive spans in the committed sources.
EXPECTED_FRAGMENTS = {
    "include/cpp_sqlite/Widget.hpp": [
        {
            "start_line": 9,
            "end_line": 12,
            "placement": "cpp_sqlite",
            "text": (
                "// A forward declaration kept out of the graph.\n"
                "class Database;\n"
                "/** Identifiers are plain 32-bit values. */\n"
                "using WidgetId = std::uint32_t;\n"
            ),
        },
    ],
}

FORMAT_CONFIG = Path(__file__).with_name("cpp_sqlite.clang-format")
CLANG_FORMAT_MAJOR = 17


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


@pytest.fixture(scope="module", autouse=True)
def required_external_tools() -> None:
    assert shutil.which("doxygen"), "doxygen is required; check PATH"
    assert _CLANG_FORMAT, "clang-format is required; check CLANG_FORMAT or PATH"


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
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    return proc.stdout.rstrip(b"\n") + b"\n"


def _relative(path: str) -> str:
    if os.path.isabs(path):
        return os.path.relpath(path, FIXTURE_DIR)
    return path


@pytest.fixture(scope="module")
def fragment_graph(tmp_path_factory):
    """Step 1 — index the compact fixture into a temp sqlite backend."""
    out_dir = tmp_path_factory.mktemp("frag-rt-out")
    indexed = index_generated_tree(
        FIXTURE_DIR,
        project_id="source-fragments",
        repository_id="fixture",
        source="source-fragments",
        input_paths=(FIXTURE_DIR / "include", FIXTURE_DIR / "src"),
        output_dir=out_dir,
    )
    assert indexed.success, indexed.diagnostics
    assert indexed.persisted is False
    return indexed.graph


class TestResidualInventory:
    def test_fragment_inventory_is_deterministic(self, fragment_graph):
        fragments = [
            e.node for e in fragment_graph._all_entries()
            if type(e.node).__name__ == "SourceFragmentNode"
        ]
        inventory: dict[str, list[dict]] = {}
        for fragment in fragments:
            rel = _relative(fragment.file_path)
            inventory.setdefault(rel, []).append({
                "start_line": fragment.start_line,
                "end_line": fragment.end_line,
                "placement": fragment.placement,
                "text": fragment.text,
            })
        assert inventory == EXPECTED_FRAGMENTS

    def test_no_structured_declaration_inside_fragments(self, fragment_graph):
        for entry in fragment_graph._all_entries():
            node = entry.node
            if type(node).__name__ != "SourceFragmentNode":
                continue
            text = node.text or ""
            assert "class Widget" not in text
            assert "struct Widget" not in text
            assert "WidgetId id()" not in text

    def test_structured_nodes_keep_source_spans(self, fragment_graph):
        from codegraph.models.compound import ClassNode as _C  # noqa: F401

        widget = next(
            e.node for e in fragment_graph._all_entries()
            if type(e.node).__name__ == "ClassNode"
            and getattr(e.node, "qualified_name", "") == "cpp_sqlite::Widget"
        )
        assert (widget.start_line, widget.end_line) == (13, 25)


class TestByteIdentity:
    def test_canonical_byte_identity(self, fragment_graph, tmp_path_factory):
        """The gate: every fixture file is byte-identical after the pinned
        canonical formatter is applied to both boundaries."""
        save_dir = tmp_path_factory.mktemp("frag-drift")
        data = fragment_graph.serialize(fields="all", export_implementation=True)
        generate(data, output_dir=save_dir)

        files = [
            "include/cpp_sqlite/Widget.hpp",
            "src/Widget.cpp",
        ]
        for rel in files:
            generated = save_dir / rel
            assert generated.is_file(), f"codegen did not save {rel}"
        report = compare_manifest(
            FIXTURE_DIR,
            save_dir,
            files,
            normalize=_canonical_cpp,
        )
        assert report.is_identical, report.describe()
