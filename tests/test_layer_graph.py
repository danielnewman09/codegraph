"""Tests for LayerGraph: from_json, to_json, to_neo4j, _node_key, from_neo4j."""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.models.compound import ClassNode, EnumNode, InterfaceNode
from codegraph.models.file import FileNode
from codegraph.models.member import AttributeNode, EnumValueNode, MethodNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode


DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


class TestNodeKey:
    """Tests for LayerGraph._node_key()."""

    def test_file_node_dict_uses_path(self):
        result = LayerGraph._node_key({"type": "FileNode", "path": "/src/main.h", "name": "main.h"})
        assert result == "/src/main.h"

    def test_class_node_dict_uses_name(self):
        result = LayerGraph._node_key({"type": "ClassNode", "name": "Widget"})
        assert result == "Widget"

    def test_method_node_dict_uses_name(self):
        result = LayerGraph._node_key({"type": "MethodNode", "name": "draw"})
        assert result == "draw"

    def test_file_node_instance_uses_path(self):
        node = FileNode(name="test.h", path="/src/test.h")
        result = LayerGraph._node_key(node)
        assert result == "/src/test.h"

    def test_class_node_instance_uses_name(self):
        node = ClassNode(name="Widget", kind="class")
        result = LayerGraph._node_key(node)
        assert result == "Widget"


class TestLayerValidation:
    """Tests for Layer validation — only 'design', 'as-built', 'dependency' allowed."""

    def test_valid_design(self):
        graph = LayerGraph(layer="design")
        assert graph.layer == "design"

    def test_valid_as_built(self):
        graph = LayerGraph(layer="as-built")
        assert graph.layer == "as-built"

    def test_valid_dependency(self):
        graph = LayerGraph(layer="dependency")
        assert graph.layer == "dependency"

    def test_invalid_layer_raises(self):
        with pytest.raises(ValueError, match="Invalid layer"):
            LayerGraph(layer="production")

    def test_from_json_invalid_layer_raises(self):
        data = [{"type": "ClassNode", "name": "X", "kind": "class", "layer": "unknown"}]
        with pytest.raises(ValueError, match="Invalid layer"):
            LayerGraph.from_json(data)


class TestFromJson:
    """Tests for LayerGraph.from_json() — pure deserialization, no DB."""

    def test_creates_nodes_from_fixture(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        assert len(graph.nodes) == len(data)
        assert graph.layer == "design"

    def test_node_types_are_correct(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        # Spot-check some nodes
        assert isinstance(graph.nodes["CalculatorEngine"], ClassNode)
        assert isinstance(graph.nodes["/src/calc/calculator_engine.h"], FileNode)
        assert isinstance(graph.nodes["ICalculator"], InterfaceNode)
        assert isinstance(graph.nodes["add"], MethodNode)

    def test_edges_are_collected(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        # The fixture has edges (CalculatorEngine COMPOSES add, etc.)
        assert len(graph.edges) > 0
        # Check one specific edge
        engine_edges = [e for e in graph.edges if e["source_key"] == "CalculatorEngine"]
        assert any(e["relation_type"] == "COMPOSES" for e in engine_edges)

    def test_layer_inference_from_data(self):
        data = [
            {"type": "ClassNode", "name": "MyClass", "kind": "class", "layer": "as-built"},
        ]
        graph = LayerGraph.from_json(data)
        assert graph.layer == "as-built"

    def test_layer_defaults_to_design(self):
        data = [
            {"type": "ClassNode", "name": "MyClass", "kind": "class"},
        ]
        graph = LayerGraph.from_json(data)
        assert graph.layer == "design"

    def test_empty_data(self):
        graph = LayerGraph.from_json([])
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        assert graph.layer == "design"


class TestRoundtrip:
    """Integration test: from_json → to_neo4j → to_json roundtrip."""

    def test_full_graph_roundtrip(self):
        with open(FIXTURE) as f:
            data = json.load(f)

        # Pure deserialization
        graph = LayerGraph.from_json(data)
        assert len(graph.nodes) == len(data)

        # Persist
        graph.to_neo4j()

        # Serialize
        serialized = graph.to_json()
        assert len(serialized) == len(data)

        # Every node serialized has the right type
        types_in_output = {item["type"] for item in serialized}
        types_in_input = {item["type"] for item in data}
        assert types_in_output == types_in_input

        # Write/read roundtrip via JSON
        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = FIXTURE_DIR / "graph_integration.json"
        with open(out_path, "w") as f:
            json.dump(serialized, f, indent=2)
        with open(out_path) as f:
            loaded = json.load(f)

        # Deserialize back — from_json handles both target_local_id
        # (fixture format) and target_uid (serialized format)
        restored = LayerGraph.from_json(loaded)
        assert len(restored.nodes) == len(data)

    def test_edge_persistence(self):
        """All fixture edges are present after to_neo4j."""
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.from_json(data)
        graph.to_neo4j()

        total_fixture_edges = 0
        for node_data in data:
            key = LayerGraph._node_key(node_data)
            saved = graph.nodes[key]
            for edge in node_data.get("edges", []):
                total_fixture_edges += 1
                target = graph.nodes[edge["target_local_id"]]
                found = [
                    e for e in saved.serialize()["edges"]
                    if e["relation_type"] == edge["relation_type"]
                    and e["target_uid"] == target._uid_value()
                ]
                assert len(found) >= 1, (
                    f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                    f"{edge['target_type']} {edge['target_local_id']}"
                )

        total_live_edges = sum(len(n.serialize()["edges"]) for n in graph.nodes.values())
        assert total_live_edges >= total_fixture_edges


class TestFromNeo4j:
    """Tests for LayerGraph.from_neo4j()."""

    def test_fetches_design_layer_nodes(self):
        """from_neo4j returns nodes with layer='design' and their neighbors."""
        # Seed some nodes first
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()

        # Now fetch via from_neo4j
        design = LayerGraph.from_neo4j("design")
        assert len(design.nodes) > 0
        assert design.layer == "design"

        # Should include at least the ClassNode we created
        class_nodes = [n for n in design.nodes.values() if isinstance(n, ClassNode)]
        assert len(class_nodes) > 0

    def test_includes_neighbors_of_layer_nodes(self):
        """Neighbors of layer-matched nodes are included even if different layer."""
        # FileNodes don't have layer, but are DEFINED_IN targets of design-layer nodes
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.from_json(data).to_neo4j()

        design = LayerGraph.from_neo4j("design")
        # FileNodes should appear as neighbors
        file_nodes = [n for n in design.nodes.values() if isinstance(n, FileNode)]
        assert len(file_nodes) > 0, "FileNodes should be included as neighbors of design nodes"