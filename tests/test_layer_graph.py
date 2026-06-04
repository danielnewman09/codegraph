"""Tests for LayerGraph: from_json, to_json, to_neo4j, _node_key, from_neo4j."""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, EnumNode, InterfaceNode
from codegraph.models.file import FileNode
from codegraph.models.member import AttributeNode, EnumValueNode, MethodNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode


DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


def _count_all_entries(graph: LayerGraph) -> int:
    """Count all CompositeEntry instances across the entire tree."""
    return sum(1 for _ in graph._all_entries())


def _find_entry(graph: LayerGraph, key: str) -> CompositeEntry | None:
    """Find a CompositeEntry by node key across the entire tree."""
    for entry in graph._all_entries():
        if LayerGraph._node_key(entry.node) == key:
            return entry
    return None


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
        assert _count_all_entries(graph) == len(data)
        assert graph.layer == "design"

    def test_node_types_are_correct(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        # Spot-check some nodes by finding them in the tree
        engine = _find_entry(graph, "CalculatorEngine")
        assert engine is not None
        assert isinstance(engine.node, ClassNode)

        file_entry = _find_entry(graph, "/src/calc/calculator_engine.h")
        assert file_entry is not None
        assert isinstance(file_entry.node, FileNode)

        icalc = _find_entry(graph, "ICalculator")
        assert icalc is not None
        assert isinstance(icalc.node, InterfaceNode)

        add_entry = _find_entry(graph, "add")
        assert add_entry is not None
        assert isinstance(add_entry.node, MethodNode)

    def test_composes_children_nested(self):
        """COMPOSES edges should create nesting under the parent entry."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)

        engine = _find_entry(graph, "CalculatorEngine")
        assert engine is not None
        # CalculatorEngine COMPOSES MethodNode (add, validateInput)
        assert "MethodNode" in engine.children
        assert "add" in engine.children["MethodNode"]
        # CalculatorEngine COMPOSES AttributeNode (precision)
        assert "AttributeNode" in engine.children
        assert "precision" in engine.children["AttributeNode"]

    def test_non_composes_edges_as_references(self):
        """Non-COMPOSES edges should be stored as references, not children."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)

        engine = _find_entry(graph, "CalculatorEngine")
        assert engine is not None
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEPENDS_ON" in ref_types
        assert "DEFINED_IN" in ref_types
        # COMPOSES should NOT be in references
        assert "COMPOSES" not in ref_types

    def test_composed_nodes_not_at_root(self):
        """Nodes composed by another node should not appear as root entries."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)

        # "add" is composed by CalculatorEngine, so it should not be a root entry
        assert "add" not in graph.entries
        assert "precision" not in graph.entries
        # NamespaceNode "calc" should be a root entry
        assert "calc" in graph.entries

    def test_layers_are_composite_entries(self):
        """Root entries should be CompositeEntry instances."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        for entry in graph.entries.values():
            assert isinstance(entry, CompositeEntry)

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
        assert len(graph.entries) == 0
        assert graph.layer == "design"


class TestRoundtrip:
    """Integration test: from_json → to_neo4j → to_json roundtrip."""

    def test_full_graph_roundtrip(self):
        with open(FIXTURE) as f:
            data = json.load(f)

        # Pure deserialization
        graph = LayerGraph.from_json(data)
        assert _count_all_entries(graph) == len(data)

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

        # Deserialize back
        restored = LayerGraph.from_json(loaded)
        assert _count_all_entries(restored) == len(data)

    def test_edge_persistence(self):
        """All fixture edges are present after to_neo4j."""
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.from_json(data)
        graph.to_neo4j()

        flat = graph._flat_index()

        total_fixture_edges = 0
        for node_data in data:
            key = LayerGraph._node_key(node_data)
            entry = flat.get(key)
            assert entry is not None, f"Missing entry for key {key}"
            saved = entry.node
            for edge in node_data.get("edges", []):
                total_fixture_edges += 1
                target_entry = flat.get(edge["target_local_id"])
                assert target_entry is not None, f"Missing target {edge['target_local_id']}"
                target = target_entry.node
                found = [
                    e for e in saved.serialize()["edges"]
                    if e["relation_type"] == edge["relation_type"]
                    and e["target_uid"] == target._uid_value()
                ]
                assert len(found) >= 1, (
                    f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                    f"{edge['target_type']} {edge['target_local_id']}"
                )

        total_live_edges = sum(
            len(entry.node.serialize()["edges"]) for entry in graph._all_entries()
        )
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
        assert _count_all_entries(design) > 0
        assert design.layer == "design"

        # Should include at least the ClassNode we created
        class_entries = [
            e for e in design._all_entries() if isinstance(e.node, ClassNode)
        ]
        assert len(class_entries) > 0

    def test_includes_neighbors_of_layer_nodes(self):
        """Neighbors of layer-matched nodes are included even if different layer."""
        # FileNodes don't have layer, but are DEFINED_IN targets of design-layer nodes
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.from_json(data).to_neo4j()

        design = LayerGraph.from_neo4j("design")
        # FileNodes should appear as neighbors
        file_entries = [
            e for e in design._all_entries() if isinstance(e.node, FileNode)
        ]
        assert len(file_entries) > 0, "FileNodes should be included as neighbors of design nodes"