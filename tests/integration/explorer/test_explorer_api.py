"""Tests for the explorer query layer (:mod:`codegraph.explorer.api`).

The LayerGraphSource is backend-agnostic (works over any LayerGraph) and
its children/scope/coverage payloads drive the web UI — these tests pin
the JSON contract the SPA depends on.
"""

import json

from codegraph.graph import LayerGraph
from codegraph.explorer.api import LayerGraphSource

FIXTURE = "tests/pipelines/unit_test_data/design_layergraph.json"


def _source():
    with open(FIXTURE, encoding="utf-8") as f:
        graph = LayerGraph.deserialize(json.load(f))
    return LayerGraphSource(graph, source_name="design_layergraph.json")


class TestExplorerApi:
    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_meta
    # Verifies meta reports source, tags, and per-type counts.
    def test_meta(self):
        m = _source().meta()
        assert m["source"] == "design_layergraph.json"
        assert "design" in m["tags"]
        assert m["counts"]["LLR"] == 4
        assert m["counts"]["TestNode"] == 9

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_namespaces
    # Verifies root namespace discovery and search filtering.
    def test_namespaces(self):
        src = _source()
        ns = src.namespaces()
        assert any(n["qname"] == "cpp_sqlite" for n in ns)
        # search filter
        filtered = src.namespaces("cpp")
        assert [n["qname"] for n in filtered] == ["cpp_sqlite"]
        assert src.namespaces("zzz") == []

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_children_tree
    # Verifies the tree level: namespaces, classes (with req/test
    # badges), and requirements mapped to the namespace.
    def test_children_tree(self):
        d = _source().children("cpp_sqlite")
        assert d["qname"] == "cpp_sqlite"
        assert d["parent"] is None
        assert isinstance(d["namespaces"], list)
        classes = {c["name"]: c for c in d["classes"]}
        assert "MigrationManager" in classes
        mm = classes["MigrationManager"]
        # badges: the verification scope for MigrationManager
        assert mm["requirements"] == 4
        assert mm["tests"] == 9
        # classes without tests carry zero badges, not missing keys
        assert classes["Database"]["tests"] == 0
        reqs = {r["qname"]: r for r in d["requirements"]}
        assert "llr_migration_apply" in reqs
        assert reqs["llr_migration_apply"]["test_count"] == 3

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_children_classnode_only
    # Verifies the tree's class list contains ONLY ClassNode-labeled
    # objects (no concepts, interfaces, enums, functions, defines).
    def test_children_classnode_only(self):
        d = _source().children("cpp_sqlite")
        assert d["classes"], "expected at least one class"
        assert all(c["kind"] == "ClassNode" for c in d["classes"])
        # the fixture also contains ConceptNodes etc. — none may leak
        kinds = {c["kind"] for c in d["classes"]}
        assert kinds == {"ClassNode"}

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_children_unknown
    # Verifies an unknown namespace yields empty children, not an error.
    def test_children_unknown(self):
        d = _source().children("nope::nope")
        assert d["classes"] == []
        assert d["namespaces"] == []
        assert d["requirements"] == []

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_scope_namespace
    # Verifies a namespace is a valid scope target: the namespace's own
    # subtree renders as an as-built (COLLAPSED) diagram.
    def test_scope_namespace(self):
        d = _source().scope("cpp_sqlite")
        assert d["puml"].startswith("@startuml")
        assert 'package "cpp_sqlite"' in d["puml"]
        assert '"Database"' in d["puml"]
        assert '"MigrationManager"' in d["puml"]
        # no verification scaffolding in the namespace view
        assert "<<test>>" not in d["puml"]

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_scope_puml
    # Verifies the class-scoped export shows the class + neighbours but
    # NO test/requirement scaffolding (those live in the req/tests
    # panel, not the diagram).
    def test_scope_puml(self):
        d = _source().scope("cpp_sqlite::MigrationManager")
        assert d["puml"].startswith("@startuml")
        assert '"MigrationManager"' in d["puml"]
        assert '"Database"' in d["puml"]  # neighbour visible
        # no requirement/test scaffolding in the diagram
        assert "llr_migration_apply <<llr>>" not in d["puml"]
        assert "<<test>>" not in d["puml"]
        assert ": verifies" not in d["puml"]

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_scope_unknown
    # Verifies unknown scope class returns an error payload.
    def test_scope_unknown(self):
        d = _source().scope("app::Missing")
        assert d["puml"] == ""
        assert "error" in d

    # codegraph:test-desc test_explorer_api.TestExplorerApi.test_coverage_payload
    # Verifies the coverage JSON contract the req/tests panel renders:
    # requirements with full narration, tests with steps and derived
    # assertion conditions.
    def test_coverage_payload(self):
        d = _source().coverage("cpp_sqlite::MigrationManager")
        assert d["class"]["name"] == "MigrationManager"
        assert d["counts"] == {"requirements": 4, "tests": 9}
        req0 = d["requirements"][0]
        assert req0["description"].startswith("The `MigrationManager` shall")
        test0 = req0["tests"][0]
        assert test0["steps"][0]["description"]  # action narration
        conds = {a["name"]: a["condition"] for a in test0["assertions"]}
        # derived conditions present (is_true renders as "is true")
        assert any(" is true" in c or " == " in c for c in conds.values())
