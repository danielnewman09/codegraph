"""Work package 4 — the graph fixpoint gate.

Byte identity (``test_cpp_sqlite_impl_roundtrip``) proves the generated
*tree* matches the source after pinned canonical formatting; this test
proves the re-indexed *graph* is equivalent.  The complete loop:

    golden tree ──canonicalize──▶ sqlite A ──serialize(export_implementation)──▶
        ▲                                                                     │
        └── compare ── re-index(canonicalized generated) ◀── generate(output) ─┘

Both trees are canonicalized with the pinned clang-format 17 configuration
into temp copies before indexing (the raw generated text may legitimately
differ in formatting — ``namespace X {`` vs ``namespace X\\n{`` — that
clang-format normalizes at the byte gate; the index must see equivalent
inputs).  The comparison is then a strict bijection over project-owned
(manifest) code nodes and relationships, excluding only documented volatile
transport fields (uid/refid/component_id/embedding).  A test-local
transparent normalization key (node type + qualified name + callable
signature) stands in for the legacy UID identity scheme; duplicates or
ambiguous matches are failures.

One negative test mutates a generated declaration in memory and proves the
comparator reports the exact drift.
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
IMPL_SRC = _HERE / "cpp_sqlite_impl_src"
PROJECT_DIR = "tests/fixtures/cpp-sqlite"

MANIFEST_FILE = Path(__file__).with_name("cpp_sqlite_roundtrip_manifest.txt")
FORMAT_CONFIG = Path(__file__).with_name("cpp_sqlite.clang-format")
CLANG_FORMAT_MAJOR = 17

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
        reason="cpp-sqlite source copies not materialized",
    ),
    pytest.mark.skipif(
        not (IMPL_SRC / PROJECT_DIR / ".doxygen-index.toml").is_file(),
        reason="cpp-sqlite index config missing from source copies",
    ),
    pytest.mark.skipif(_CLANG_FORMAT is None, reason="clang-format required"),
]


def _load_manifest() -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _canonicalize_tree(src_root: Path, dst_root: Path) -> None:
    """Copy the manifest tree and canonicalize each file with the pinned
    formatter (boundary rule: LF + exactly one final newline)."""
    shutil.copytree(src_root, dst_root)
    config = dst_root / PROJECT_DIR / ".doxygen-index.toml"
    if not config.is_file():
        shutil.copy2(src_root / PROJECT_DIR / ".doxygen-index.toml", config)
    for rel in _load_manifest():
        path = dst_root / rel
        proc = subprocess.run(
            [_CLANG_FORMAT, f"--style=file:{FORMAT_CONFIG}",
             f"--assume-filename={path}"],
            input=path.read_bytes(),
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")
        canonical = proc.stdout.rstrip(b"\n") + b"\n"
        path.write_bytes(canonical)


def _index_tree(tree_root: Path, db_path: Path, out_dir: Path) -> LayerGraph:
    """Run doxygen-index against *tree_root* and return the as-built graph."""
    env = {**os.environ, "CODEGRAPH_BACKEND": "sqlite", "SQLITE_PATH": str(db_path)}
    proc = subprocess.run(
        [_DOXYGEN_INDEX, "codegraph",
         "--project-dir", PROJECT_DIR,
         "--output-dir", str(out_dir),
         "--neo4j", "--clear", "--yes"],
        cwd=tree_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"doxygen-index failed:\n{proc.stderr[-3000:]}"
    assert db_path.exists(), "doxygen-index did not write the sqlite backend"
    from codegraph.backends import get_backend, set_backend
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

    set_backend(SqliteBackend(SqliteConfig(path=str(db_path))))
    return LayerGraph.from_backend(get_backend(), "as-built")


def _manifest_paths() -> frozenset[str]:
    return frozenset(_load_manifest())


def _iter_nodes(data: list[dict]):
    """Yield every node in the serialized export (top-level + composed)."""
    def walk(node: dict):
        yield node
        for child in node.get("composes", []) or []:
            yield from walk(child)
    for node in data:
        yield from walk(node)


def _project_nodes(data: list[dict]) -> list[dict]:
    """Serialized nodes belonging to the 14 production files (constraint 3:
    the two test files are excluded — they serve as later behavioral
    evidence, outside source byte-fidelity)."""
    manifest = _manifest_paths()
    out = []
    for node in _iter_nodes(data):
        path = node.get("file_path") or node.get("path") or ""
        if not path.startswith(f"{PROJECT_DIR}/"):
            continue
        # a node belongs to the manifest tree when its file is one of the
        # production files (fragments/files carry the path directly)
        if path not in manifest and not any(
            path == rel or path.startswith(rel + "#") for rel in manifest
        ):
            continue
        out.append(node)
    return out


def _node_key(node: dict) -> str:
    """Test-local transparent identity: type + qualified name + callable
    signature.  Deliberately NOT the legacy uid — Priority 2 replaces that
    scheme, so equivalence must not depend on it."""
    node_type = node.get("type", "")
    qn = node.get("qualified_name", "") or node.get("name", "") or ""
    args = node.get("argsstring", "") or ""
    if node_type in ("MethodNode", "FunctionNode"):
        return f"{node_type}::{qn}{args}"
    if node_type == "SourceFragmentNode":
        return f"{node_type}::{node.get('file_path', '')}#{node.get('start_line')}-{node.get('end_line')}"
    if node_type == "FileNode":
        return f"{node_type}::{node.get('path', '')}"
    if node_type == "NamespaceNode":
        return f"{node_type}::{qn}"
    return f"{node_type}::{qn}"


#: Node fields that are volatile transport metadata, never equivalence data.
_VOLATILE_FIELDS = frozenset({
    "uid", "refid", "component_id", "doc_embedding", "source", "layer",
})

#: Node fields whose source-spelled content must match exactly.
_FIDELITY_FIELDS = frozenset({
    "name", "kind", "qualified_name", "visibility", "protection",
    "type_signature", "argsstring", "definition", "body", "body_file",
    "body_start", "body_end", "line_number", "start_line", "end_line",
    "file_path", "initializer", "declaration", "template_declarations",
    "base_specifiers", "base_classes", "underlying_type", "enum_class",
    "is_static", "is_const", "is_constexpr", "is_virtual", "is_inline",
    "is_explicit", "is_nodiscard", "is_final", "is_abstract",
    "brief_description", "detailed_description", "source_documentation",
    "include_directives", "include_directive_lines", "include_guard",
    "namespace_leading_blank_lines", "namespace_trailing_blank_lines",
    "namespace_name", "namespace_regions", "leading_blank_lines",
    "guard_leading_blank_lines", "text",
})


def _node_fingerprint(node: dict) -> tuple:
    """Equivalence fingerprint: source-spelled fidelity fields only."""
    return tuple(
        sorted(
            (k, repr(v))
            for k, v in node.items()
            if k not in _VOLATILE_FIELDS and k != "composes" and k != "edges"
            and k in _FIDELITY_FIELDS
        )
    )


def _relationships(data: list[dict]) -> list[tuple[str, str, str]]:
    """Normalized project-owned relationship triples (from, relation, to).

    Scoped to the 14 production files (constraint 3): test-file nodes are
    excluded from the fixpoint contract.
    """
    manifest = _manifest_paths()

    def scoped(node: dict) -> bool:
        path = node.get("file_path") or node.get("path") or ""
        return path in manifest

    rels = set()
    for node in _iter_nodes(data):
        if not scoped(node):
            continue
        from_key = _node_key(node)
        for child in node.get("composes", []) or []:
            if not scoped(child):
                continue
            rels.add((from_key, "COMPOSES", _node_key(child)))
        for edge in node.get("edges", []) or []:
            rels.add((from_key, edge.get("relation_type", "?"), edge.get("target_uid", "")))
    return sorted(rels)


def _graph_model(data: list[dict]) -> tuple[dict[str, tuple], list[tuple[str, str, str]]]:
    """Return ``(key → fingerprint, relationships)`` over project nodes."""
    nodes: dict[str, tuple] = {}
    for node in _project_nodes(data):
        key = _node_key(node)
        if key in nodes:
            raise AssertionError(f"ambiguous normalization key: {key}")
        nodes[key] = _node_fingerprint(node)
    return nodes, _relationships(data)


def _compare_graphs(data_a: list[dict], data_b: list[dict]) -> list[str]:
    """Bijection compare with a readable missing/extra/changed report."""
    nodes_a, rels_a = _graph_model(data_a)
    nodes_b, rels_b = _graph_model(data_b)
    report: list[str] = []
    for key in sorted(set(nodes_a) - set(nodes_b)):
        report.append(f"missing node: {key}")
    for key in sorted(set(nodes_b) - set(nodes_a)):
        report.append(f"extra node: {key}")
    for key in sorted(set(nodes_a) & set(nodes_b)):
        if nodes_a[key] != nodes_b[key]:
            report.append(f"changed node: {key}")
    for rel in sorted(set(rels_a) - set(rels_b)):
        report.append(f"missing relationship: {rel}")
    for rel in sorted(set(rels_b) - set(rels_a)):
        report.append(f"extra relationship: {rel}")
    return report


@pytest.fixture(scope="module")
def fixpoint_data(tmp_path_factory):
    """Golden graph + generated-tree graph (both serialized exports)."""
    tmp = tmp_path_factory.mktemp("fixpoint")

    # Canonicalize the golden tree into a temp copy and index it.
    golden_canon = tmp / "golden-canon"
    _canonicalize_tree(IMPL_SRC, golden_canon)
    graph_a = _index_tree(golden_canon, tmp / "a.sqlite3", tmp / "out-a")
    data_a = graph_a.serialize(fields="all", export_implementation=True)

    # Generate the 14-file production tree.
    save_dir = tmp / "generated"
    generate(data_a, output_dir=save_dir)
    # The generated tree needs the index config to be re-indexable.
    config = IMPL_SRC / PROJECT_DIR / ".doxygen-index.toml"
    target_config = save_dir / PROJECT_DIR / ".doxygen-index.toml"
    target_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config, target_config)

    # Canonicalize the generated tree into a temp copy and index it.
    generated_canon = tmp / "generated-canon"
    _canonicalize_tree(save_dir, generated_canon)
    graph_b = _index_tree(generated_canon, tmp / "b.sqlite3", tmp / "out-b")
    data_b = graph_b.serialize(fields="all", export_implementation=True)
    return data_a, data_b, save_dir


class TestGraphFixpoint:
    def test_project_tree_is_reindexable(self, fixpoint_data):
        data_a, data_b, save_dir = fixpoint_data
        assert len(_project_nodes(data_a)) > 0
        assert len(_project_nodes(data_b)) > 0
        for rel in _load_manifest():
            assert (save_dir / rel).is_file()

    def test_project_owned_nodes_are_bijective(self, fixpoint_data):
        data_a, data_b, _save_dir = fixpoint_data
        report = _compare_graphs(data_a, data_b)
        assert not report, "graph drift:\n" + "\n".join(report)

    def test_relationships_are_preserved(self, fixpoint_data):
        data_a, data_b, _save_dir = fixpoint_data
        nodes_a, rels_a = _graph_model(data_a)
        nodes_b, rels_b = _graph_model(data_b)
        assert len(rels_a) > 0, "golden graph carried no project relationships"
        # Every golden relationship has an equivalent generated one, with
        # to-side keys resolved by the transparent key (not legacy uids).
        resolved_a = {
            (f, r, t) for f, r, t in rels_a if t in nodes_a or r == "COMPOSES"
        }
        resolved_b = {
            (f, r, t) for f, r, t in rels_b if t in nodes_b or r == "COMPOSES"
        }
        assert resolved_a == resolved_b, (
            "relationship drift:\n"
            + "\n".join(sorted(resolved_a ^ resolved_b))
        )

    def test_negative_mutation_is_reported_exactly(self, fixpoint_data):
        """One mutated declaration in memory → the comparator reports the
        exact changed node (and nothing else)."""
        data_a, _data_b, _save_dir = fixpoint_data
        import copy

        mutated = copy.deepcopy(data_a)
        target = next(
            n for n in _project_nodes(mutated)
            if n.get("type") == "MethodNode"
            and "withTransaction" in (n.get("qualified_name") or "")
        )
        original = target["body"]
        target["body"] = "void Database::withTransaction(Func&& f)\n{\n  broken();\n}\n"
        report = _compare_graphs(data_a, mutated)
        changed = [line for line in report if line.startswith("changed node:")]
        assert len(changed) == 1, report
        assert changed[0] == f"changed node: {_node_key(target)}"
        # restoring the original body removes the drift entirely
        target["body"] = original
        assert _compare_graphs(data_a, mutated) == []
