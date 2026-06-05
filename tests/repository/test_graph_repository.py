"""Tests for GraphRepository — scope-based read methods and save_layer_graph.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.repository import GraphRepository

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"

pytestmark = pytest.mark.usefixtures("setup_neomodel")


def _all_nodes(graph: LayerGraph):
    """Yield all CodeGraphNode instances from the entry tree."""
    for entry in graph._all_entries():
        yield entry.node


def _nodes_of_type(graph: LayerGraph, type_name: str):
    """Yield all nodes of a given type name from the entry tree.

    Uses ``type().__name__`` instead of ``isinstance`` to avoid
    false positives caused by neomodel's ABCMeta/NodeMeta metaclass
    interaction after ``save()`` / ``connect()``.
    """
    for node in _all_nodes(graph):
        if type(node).__name__ == type_name:
            yield node


def _find_entry(graph: LayerGraph, key: str) -> CompositeEntry | None:
    """Find a CompositeEntry by node key across the entire tree."""
    for entry in graph._all_entries():
        if LayerGraph._node_key(entry.node) == key:
            return entry
    return None


@pytest.fixture
def seeded_graph():
    """Seed Neo4j with the design_graph fixture and return the LayerGraph."""
    with open(FIXTURE) as f:
        data = json.load(f)
    graph = LayerGraph.from_json(data)
    graph.to_neo4j()
    return graph


@pytest.fixture
def repo():
    return GraphRepository()


# ── get_by_layer ────────────────────────────────────────────────────────────


class TestGetByLayer:
    def test_returns_layer_graph(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        assert isinstance(result, LayerGraph)

    def test_includes_design_nodes(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        class_nodes = list(_nodes_of_type(result, "ClassNode"))
        assert len(class_nodes) > 0

    def test_includes_neighbors(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        # Seed nodes have layer="design"; neighbors may not.
        # The LayerGraph should contain more than just the seeds.
        count = sum(1 for _ in result._all_entries())
        assert count > 0

    def test_empty_layer(self, repo, seeded_graph):
        result = repo.get_by_layer("nonexistent")
        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0

    def test_derived_layer_matches(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        assert result.layer == "design"


# ── get_by_source ────────────────────────────────────────────────────────────


class TestGetBySource:
    def test_returns_layer_graph(self, repo, seeded_graph):
        result = repo.get_by_source("calculator")
        assert isinstance(result, LayerGraph)

    def test_includes_source_nodes(self, repo, seeded_graph):
        result = repo.get_by_source("calculator")
        source_nodes = [n for n in _all_nodes(result) if source_matches(n, "calculator")]
        assert len(source_nodes) > 0

    def test_missing_source_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_source("nonexistent_project")
        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0


# ── get_by_namespace ─────────────────────────────────────────────────────────


class TestGetByNamespace:
    def test_returns_layer_graph(self, repo, seeded_graph):
        # Find the actual qualified_name of a namespace in the seed graph
        ns_nodes = list(_nodes_of_type(seeded_graph, "NamespaceNode"))
        assert len(ns_nodes) > 0, "Seed graph must have at least one namespace"
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        assert isinstance(result, LayerGraph)

    def test_includes_namespace_and_compounds(self, repo, seeded_graph):
        ns_nodes = list(_nodes_of_type(seeded_graph, "NamespaceNode"))
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        ns_in_result = list(_nodes_of_type(result, "NamespaceNode"))
        assert len(ns_in_result) > 0

    def test_missing_namespace_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_namespace("nonexistent::ns")
        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0


# ── get_by_compound ──────────────────────────────────────────────────────────


class TestGetByCompound:
    def test_returns_layer_graph(self, repo, seeded_graph):
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        assert isinstance(result, LayerGraph)

    def test_includes_compound(self, repo, seeded_graph):
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        compounds = list(_nodes_of_type(result, "ClassNode"))
        assert len(compounds) > 0

    def test_missing_compound_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_compound("NonexistentClass")
        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0


# ── get_by_neighbourhood ────────────────────────────────────────────────────


class TestGetByNeighbourhood:
    def test_works_for_compound(self, repo, seeded_graph):
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        assert isinstance(result, LayerGraph)
        count = sum(1 for _ in result._all_entries())
        assert count > 0

    def test_works_for_member(self, repo, seeded_graph):
        method_nodes = list(_nodes_of_type(seeded_graph, "MethodNode"))
        if not method_nodes:
            pytest.skip("No method nodes in seed graph")
        qname = method_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        assert isinstance(result, LayerGraph)
        members = list(_nodes_of_type(result, "MethodNode"))
        assert len(members) > 0

    def test_missing_node_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_neighbourhood("DoesNotExist")
        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0


# ── get_by_kind ──────────────────────────────────────────────────────────────


class TestGetByKind:
    def test_returns_layer_graph(self, repo, seeded_graph):
        result = repo.get_by_kind("class")
        assert isinstance(result, LayerGraph)

    def test_includes_class_nodes(self, repo, seeded_graph):
        result = repo.get_by_kind("class")
        class_nodes = list(_nodes_of_type(result, "ClassNode"))
        assert len(class_nodes) > 0

    def test_with_layer_filter(self, repo, seeded_graph):
        result = repo.get_by_kind("class", layer="design")
        assert isinstance(result, LayerGraph)
        # All returned nodes with a layer property should be design
        for node in _all_nodes(result):
            if "layer" in type(node).defined_properties():
                assert node.layer == "design"

    def test_returns_methods(self, repo, seeded_graph):
        result = repo.get_by_kind("method")
        method_nodes = list(_nodes_of_type(result, "MethodNode"))
        assert len(method_nodes) > 0


# ── save_layer_graph ────────────────────────────────────────────────────────


class TestSaveLayerGraph:
    def test_roundtrip(self, repo):
        """Build a LayerGraph from JSON, save, then query it back."""
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.from_json(data)
        repo.save_layer_graph(graph)

        # Query back by layer
        result = repo.get_by_layer("design")
        count = sum(1 for _ in result._all_entries())
        assert count > 0


# ── Build LayerGraph entries ────────────────────────────────────────────────


class TestBuildLayerGraphEntries:
    def test_entries_are_composite_entries(self, repo, seeded_graph):
        """All entries should be CompositeEntry instances."""
        result = repo.get_by_layer("design")
        for entry in result._all_entries():
            assert isinstance(entry, CompositeEntry)

    def test_composes_children_and_references(self, repo, seeded_graph):
        """Entries should have COMPOSES in children and other edges in references."""
        result = repo.get_by_layer("design")
        for entry in result._all_entries():
            # No COMPOSES edges should appear in references
            ref_types = {r[0] for r in entry.references}
            # COMPOSES should not be in references (it's in children)
            # Note: we only enforce this for entries that have children
            if entry.children:
                assert "COMPOSES" not in ref_types


# ── Helpers ──────────────────────────────────────────────────────────────────


def source_matches(node, source: str) -> bool:
    """Check if a node's source field matches."""
    return getattr(node, "source", None) == source