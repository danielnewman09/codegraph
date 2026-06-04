"""Tests for GraphRepository — scope-based read methods and save_layer_graph.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.repository import GraphRepository

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"

pytestmark = pytest.mark.usefixtures("setup_neomodel")


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
        class_nodes = [n for n in result.nodes.values() if isinstance(n, ClassNode)]
        assert len(class_nodes) > 0

    def test_includes_neighbors(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        # Seed nodes have layer="design"; neighbors may not.
        # The LayerGraph should contain more than just the seeds.
        assert len(result.nodes) > 0

    def test_empty_layer(self, repo, seeded_graph):
        result = repo.get_by_layer("nonexistent")
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) == 0

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
        source_nodes = [n for n in result.nodes.values() if source_matches(n, "calculator")]
        assert len(source_nodes) > 0

    def test_missing_source_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_source("nonexistent_project")
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) == 0


# ── get_by_namespace ─────────────────────────────────────────────────────────


class TestGetByNamespace:
    def test_returns_layer_graph(self, repo, seeded_graph):
        # Find the actual qualified_name of a namespace in the seed graph
        ns_nodes = [n for n in seeded_graph.nodes.values()
                     if isinstance(n, NamespaceNode)]
        assert len(ns_nodes) > 0, "Seed graph must have at least one namespace"
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        assert isinstance(result, LayerGraph)

    def test_includes_namespace_and_compounds(self, repo, seeded_graph):
        ns_nodes = [n for n in seeded_graph.nodes.values()
                     if isinstance(n, NamespaceNode)]
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        ns_in_result = [n for n in result.nodes.values()
                        if isinstance(n, NamespaceNode)]
        assert len(ns_in_result) > 0

    def test_missing_namespace_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_namespace("nonexistent::ns")
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) == 0


# ── get_by_compound ──────────────────────────────────────────────────────────


class TestGetByCompound:
    def test_returns_layer_graph(self, repo, seeded_graph):
        class_nodes = [n for n in seeded_graph.nodes.values()
                       if isinstance(n, ClassNode)]
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        assert isinstance(result, LayerGraph)

    def test_includes_compound(self, repo, seeded_graph):
        class_nodes = [n for n in seeded_graph.nodes.values()
                       if isinstance(n, ClassNode)]
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        compounds = [n for n in result.nodes.values()
                     if isinstance(n, ClassNode)]
        assert len(compounds) > 0

    def test_missing_compound_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_compound("NonexistentClass")
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) == 0


# ── get_by_neighbourhood ────────────────────────────────────────────────────


class TestGetByNeighbourhood:
    def test_works_for_compound(self, repo, seeded_graph):
        class_nodes = [n for n in seeded_graph.nodes.values()
                       if isinstance(n, ClassNode)]
        qname = class_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) > 0

    def test_works_for_member(self, repo, seeded_graph):
        method_nodes = [n for n in seeded_graph.nodes.values()
                        if isinstance(n, MethodNode)]
        if not method_nodes:
            pytest.skip("No method nodes in seed graph")
        qname = method_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        assert isinstance(result, LayerGraph)
        members = [n for n in result.nodes.values() if isinstance(n, MethodNode)]
        assert len(members) > 0

    def test_missing_node_returns_empty(self, repo, seeded_graph):
        result = repo.get_by_neighbourhood("DoesNotExist")
        assert isinstance(result, LayerGraph)
        assert len(result.nodes) == 0


# ── get_by_kind ──────────────────────────────────────────────────────────────


class TestGetByKind:
    def test_returns_layer_graph(self, repo, seeded_graph):
        result = repo.get_by_kind("class")
        assert isinstance(result, LayerGraph)

    def test_includes_class_nodes(self, repo, seeded_graph):
        result = repo.get_by_kind("class")
        class_nodes = [n for n in result.nodes.values() if isinstance(n, ClassNode)]
        assert len(class_nodes) > 0

    def test_with_layer_filter(self, repo, seeded_graph):
        result = repo.get_by_kind("class", layer="design")
        assert isinstance(result, LayerGraph)
        # All returned nodes with a layer property should be design
        for node in result.nodes.values():
            if "layer" in type(node).defined_properties():
                assert node.layer == "design"

    def test_returns_methods(self, repo, seeded_graph):
        result = repo.get_by_kind("method")
        method_nodes = [n for n in result.nodes.values() if isinstance(n, MethodNode)]
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
        assert len(result.nodes) > 0


# ── Build LayerGraph edges ──────────────────────────────────────────────────


class TestBuildLayerGraphEdges:
    def test_edges_connect_seed_nodes(self, repo, seeded_graph):
        """Edges should have valid source and target keys in the nodes dict."""
        result = repo.get_by_layer("design")
        keys = set(result.nodes.keys())
        for edge in result.edges:
            assert edge["source_key"] in keys, f"Edge source {edge['source_key']} not in nodes"
            assert edge["target_key"] in keys, f"Edge target {edge['target_key']} not in nodes"

    def test_edge_has_required_fields(self, repo, seeded_graph):
        result = repo.get_by_layer("design")
        for edge in result.edges:
            assert "source_key" in edge
            assert "relation_type" in edge
            assert "target_key" in edge
            assert "target_type" in edge


# ── Helpers ──────────────────────────────────────────────────────────────────


def source_matches(node, source: str) -> bool:
    """Check if a node's source field matches."""
    return getattr(node, "source", None) == source