"""CodegenContextBuilder.build() end-to-end tests.

Exercises the full orchestration: skip counting, orphan detection (D10),
design file synthesis (D5) with D9 nested-dup exclusion, namespace
nesting by qname, and as-built FileNode passthrough.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from codegraph.codegen.context import CodegenContextBuilder
from codegraph.graph import LayerGraph



def _deser(data):
    return LayerGraph.deserialize(data)



GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"

SYNTHETIC = [
    {
        "type": "NamespaceNode",
        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:namespace:qualified_name=cpp_sqlite',
        "name": "cpp_sqlite",
        "qualified_name": "cpp_sqlite",
        "kind": "namespace",
        "source": "test",
        "tags": ["design"],
        "composes": [
            {
                "type": "ClassNode",
                "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:class:qualified_name=cpp_sqlite%3A%3AMigrationManager',
                "name": "MigrationManager",
                "qualified_name": "cpp_sqlite::MigrationManager",
                "kind": "class",
                "visibility": "public",
                "source": "test",
                "tags": ["design"],
                "composes": [
                    {
                        "type": "MethodNode",
                        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:method:qualified_name=cpp_sqlite%3A%3AMigrationManager%3A%3Aapply:canonical_signature=lang%3Acpp%7C%28%29',
                        "name": "apply",
                        "qualified_name": "cpp_sqlite::MigrationManager::apply",
                        "kind": "method",
                        "type_signature": "MigrationResult apply()",
                        "argsstring": "()",
                        "visibility": "public",
                        "source": "test",
                        "tags": ["design"],
                    },
                    {
                        "type": "AttributeNode",
                        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3AMigrationManager%3A%3Adb_',
                        "name": "db_",
                        "qualified_name": "cpp_sqlite::MigrationManager::db_",
                        "kind": "attribute",
                        "type_signature": "Database&",
                        "visibility": "private",
                        "source": "test",
                        "tags": ["design"],
                    },
                ],
            },
            {
                "type": "EnumNode",
                "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:enum:qualified_name=cpp_sqlite%3A%3AMigrationErrorCode',
                "name": "MigrationErrorCode",
                "qualified_name": "cpp_sqlite::MigrationErrorCode",
                "kind": "enum",
                "source": "test",
                "tags": ["design"],
            },
        ],
    },
    {
        "type": "AttributeNode",  # orphaned stub (D10)
        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=MigrationManager%3A%3Aversion1_reapplied',
        "name": "version1_reapplied",
        "qualified_name": "MigrationManager::version1_reapplied",
        "kind": "attribute",
        "type_signature": "",
        "source": "test",
        "tags": ["design"],
    },
    {
        "type": "LiteralNode",
        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:literal:qualified_name=literal%3A%3Atrue',
        "value": "true",
        "value_type": "boolean",
        "qualified_name": "literal::true",
        "source": "test",
        "tags": ["design"],
    },
]


class TestBuildDesign:
    def test_file_synthesis_and_skip_counts(self):
        graph = _deser(SYNTHETIC)
        out = CodegenContextBuilder().build(graph)
        # one header per compound: MigrationManager + MigrationErrorCode
        assert set(out.files) == {
            "include/cpp_sqlite/MigrationManager.hpp",
            "include/cpp_sqlite/MigrationErrorCode.hpp",
        }
        assert out.skipped == {"LiteralNode": 1, "AttributeNode": 1}  # orphan
        assert any("orphaned members skipped" in w for w in out.warnings)
        assert out.graph_tags == frozenset({"design"})

    def test_file_context_shape(self):
        graph = _deser(SYNTHETIC)
        out = CodegenContextBuilder().build(graph)
        ctx = out.files["include/cpp_sqlite/MigrationManager.hpp"]
        assert ctx["type"] == "FileNode"
        assert ctx["guard"] == "INCLUDE_CPP_SQLITE_MIGRATIONMANAGER_HPP"
        assert ctx["language"] == "cpp"
        assert ctx["forward_decls"] == []
        ns = ctx["namespaces"]
        assert ns == [{"name": "cpp_sqlite", "blocks": [ctx["namespaces"][0]["blocks"][0]], "namespaces": []}]
        cls = ns[0]["blocks"][0]
        assert cls["type"] == "ClassNode"
        assert cls["name"] == "MigrationManager"
        sections = [(s["access"], [m["name"] for m in s["members"]]) for s in cls["sections"]]
        assert sections == [("public", ["apply"]), ("private", ["db_"])]
        assert cls["sections"][0]["members"][0]["declaration"] == "MigrationResult apply()"

    def test_std_library_references_not_emitted(self):
        graph = _deser([{
            "type": "NamespaceNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:namespace:qualified_name=std',
            "name": "std",
            "qualified_name": "std",
            "kind": "namespace",
            "source": "test",
            "tags": ["design"],
            "composes": [{
                "type": "ClassNode",
                "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:class:qualified_name=std%3A%3Avector',
                "name": "vector",
                "qualified_name": "std::vector",
                "kind": "class",
                "source": "test",
                "tags": ["design"],
            }],
        }])
        out = CodegenContextBuilder().build(graph)
        assert out.files == {}


class TestBuildGoldens:
    """Real-data smoke: the builders handle both fixture encodings."""

    def test_split_golden(self):
        graph = _deser(
            json.loads((GOLDEN_DIR / "design_layergraph.json").read_text())
        )
        out = CodegenContextBuilder().build(graph)
        assert "include/cpp_sqlite/MigrationManager.hpp" in out.files
        mm = out.files["include/cpp_sqlite/MigrationManager.hpp"]
        cls = mm["namespaces"][0]["blocks"][0]
        methods = [m for s in cls["sections"] for m in s["members"] if m["type"] == "MethodNode"]
        apply = next(m for m in methods if m["name"] == "apply")
        assert apply["declaration"] == "MigrationResult apply()"
        # Phase 3: test nodes render instead of being skipped — one .cpp per test.
        assert "tests/test_duplicate_version_rejected.cpp" in out.files
        assert out.skipped.get("TestNode", 0) == 0

    def test_full_decl_golden_d9_dedup(self):
        """D9: nested duplicate structs are excluded from top-level files."""
        graph = _deser(
            json.loads((GOLDEN_DIR / "design_layergraph_full_decl.json").read_text())
        )
        out = CodegenContextBuilder().build(graph)
        assert "include/cpp_sqlite/MigrationResult.hpp" not in out.files
        assert "include/cpp_sqlite/SchemaMismatch.hpp" not in out.files
        assert "include/cpp_sqlite/SchemaVerificationResult.hpp" not in out.files
        # 5 namespace compounds (3 dedup'd) + 2 root classes + 2 enums
        # + 9 test .cpp (Phase 3 test export) = 16
        assert len(out.files) == 16
        assert out.skipped.get("AttributeNode", 0) == 23  # spec's stranded figure

    def test_full_decl_verbatim_emission(self):
        graph = _deser(
            json.loads((GOLDEN_DIR / "design_layergraph_full_decl.json").read_text())
        )
        out = CodegenContextBuilder().build(graph)
        ctx = out.files["include/cpp_sqlite/Migration.hpp"]
        cls = ctx["namespaces"][0]["blocks"][0]
        methods = [m for s in cls["sections"] for m in s["members"] if m["type"] == "MethodNode"]
        get_version = next(m for m in methods if m["name"] == "getVersion")
        assert get_version["declaration"] == "virtual int getVersion() const = 0"
        assert get_version["virtual"] is True
        assert get_version["role"] == "method"


class TestBuildAsBuilt:
    def test_file_node_passthrough(self):
        graph = _deser([
            {
                "type": "FileNode",
                "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:file:normalized_repository_path=cpp_sqlite%2Fsrc%2Fcpp_sqlite%2FMigration.hpp',
                "name": "Migration.hpp",
                "path": "cpp_sqlite/src/cpp_sqlite/Migration.hpp",
                "language": "C++",
                "source": "test",
                "tags": ["as-built"],
            },
            {
                "type": "ClassNode",
                "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:class:qualified_name=cpp_sqlite%3A%3AMigration',
                "name": "Migration",
                "qualified_name": "cpp_sqlite::Migration",
                "kind": "class",
                "file_path": "cpp_sqlite/src/cpp_sqlite/Migration.hpp",
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        out = CodegenContextBuilder().build(graph)
        assert set(out.files) == {"cpp_sqlite/src/cpp_sqlite/Migration.hpp"}
        ctx = out.files["cpp_sqlite/src/cpp_sqlite/Migration.hpp"]
        assert ctx["generated_banner"] is False
        assert ctx["language"] == "cpp"
        assert ctx["guard"] == "CPP_SQLITE_SRC_CPP_SQLITE_MIGRATION_HPP"
        assert ctx["namespaces"][0]["name"] == "cpp_sqlite"
        assert ctx["namespaces"][0]["blocks"][0]["name"] == "Migration"


class TestNamespaceNesting:
    """qname → namespace nesting must survive ``::`` inside template args
    and three-or-more scope levels (regression: nested namespaces were
    stored as sibling keys of the parent node and silently dropped).
    """

    def _file_ctx(self, qnames: list[str]):
        nodes = [
            {
                "type": "ClassNode",
                "canonical_key": (
                    "cg:v1:repository:codegraph-suite%2Fcodegraph:class:"
                    f"qualified_name={quote(qn, safe='')}"
                ),
                "name": qn.split("::")[-1],
                "qualified_name": qn,
                "kind": "struct",
                "file_path": "inc/x.hpp",
                "source": "test",
                "tags": ["as-built"],
            }
            for qn in qnames
        ]
        graph = _deser([
            {
                "type": "FileNode",
                "canonical_key": "cg:v1:repository:codegraph-suite%2Fcodegraph:file:normalized_repository_path=inc%2Fx.hpp",
                "name": "x.hpp",
                "path": "inc/x.hpp",
                "source": "test",
                "tags": ["as-built"],
            },
            *nodes,
        ])
        return CodegenContextBuilder().build(graph).files["inc/x.hpp"]

    def test_template_args_containing_scope(self):
        qn = "cpp_sqlite::IsVector< std::vector< T, Allocator > >"
        ctx = self._file_ctx([qn])
        assert len(ctx["namespaces"]) == 1
        ns = ctx["namespaces"][0]
        assert ns["name"] == "cpp_sqlite"
        assert [b["qualified_name"] for b in ns["blocks"]] == [qn]
        assert ns["namespaces"] == []

    def test_three_level_nesting(self):
        ctx = self._file_ctx(["a::b::Thing", "a::Other"])
        assert [ns["name"] for ns in ctx["namespaces"]] == ["a"]
        a = ctx["namespaces"][0]
        assert [b["name"] for b in a["blocks"]] == ["Other"]
        assert [ns["name"] for ns in a["namespaces"]] == ["b"]
        assert [b["name"] for b in a["namespaces"][0]["blocks"]] == ["Thing"]

    def test_scope_parts(self):
        from codegraph.codegen.context import _scope_parts

        assert _scope_parts("cpp_sqlite::IsVector< std::vector< T > >") == [
            "cpp_sqlite", "IsVector< std::vector< T > >"
        ]
        assert _scope_parts("a::b::c") == ["a", "b", "c"]
        assert _scope_parts("solo") == ["solo"]
