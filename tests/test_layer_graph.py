"""Tests for LayerGraph: deserialize, serialize, to_neo4j, _node_key, from_neo4j."""

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

    def test_file_node_dict_uses_refid(self):
        result = LayerGraph._node_key({"type": "FileNode", "refid": "file-main", "path": "/src/main.h", "name": "main.h"})
        assert result == "file-main"

    def test_file_node_dict_falls_back_to_name_without_refid(self):
        result = LayerGraph._node_key({"type": "FileNode", "path": "/src/main.h", "name": "main.h"})
        assert result == "main.h"

    def test_class_node_dict_uses_qualified_name(self):
        result = LayerGraph._node_key({"type": "ClassNode", "qualified_name": "ns::Widget", "name": "Widget"})
        assert result == "ns::Widget"

    def test_class_node_dict_falls_back_to_name_without_qualified_name(self):
        result = LayerGraph._node_key({"type": "ClassNode", "name": "Widget"})
        assert result == "Widget"

    def test_method_node_dict_uses_qualified_name(self):
        result = LayerGraph._node_key({"type": "MethodNode", "qualified_name": "ns::Widget::draw", "name": "draw"})
        assert result == "ns::Widget::draw"

    def test_namespace_node_dict_uses_qualified_name(self):
        result = LayerGraph._node_key({"type": "NamespaceNode", "qualified_name": "calc", "name": "calc"})
        assert result == "calc"

    def test_file_node_instance_uses_refid(self):
        node = FileNode(name="test.h", path="/src/test.h", refid="file-test-h")
        result = LayerGraph._node_key(node)
        assert result == "file-test-h"

    def test_class_node_instance_uses_qualified_name(self):
        node = ClassNode(name="Widget", kind="class", qualified_name="ns::Widget")
        result = LayerGraph._node_key(node)
        assert result == "ns::Widget"

    def test_parameter_node_falls_back_to_name(self):
        """ParameterNode has no UniqueIdProperty, so _node_key falls back to name."""
        from codegraph.models.parameter import ParameterNode
        node = ParameterNode(name="argc", position=0, type="int")
        result = LayerGraph._node_key(node)
        assert result == "argc"


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

    def test_deserialize_invalid_layer_raises(self):
        data = [{"type": "ClassNode", "name": "X", "kind": "class", "layer": "unknown"}]
        with pytest.raises(ValueError, match="Invalid layer"):
            LayerGraph.deserialize(data)


class TestDeserialize:
    """Tests for LayerGraph.deserialize() — pure deserialization, no DB."""

    def test_creates_nodes_from_fixture(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        assert _count_all_entries(graph) == len(data)
        assert graph.layer == "design"

    def test_node_types_are_correct(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        # Spot-check some nodes by finding them in the tree
        engine = _find_entry(graph, "calc::CalculatorEngine")
        assert engine is not None
        assert type(engine.node).__name__ == "ClassNode"

        file_entry = _find_entry(graph, "file-calc-engine")
        assert file_entry is not None
        assert type(file_entry.node).__name__ == "FileNode"

        icalc = _find_entry(graph, "calc::ICalculator")
        assert icalc is not None
        assert type(icalc.node).__name__ == "InterfaceNode"

        add_entry = _find_entry(graph, "calc::CalculatorEngine::add")
        assert add_entry is not None
        assert type(add_entry.node).__name__ == "MethodNode"

    def test_composes_children_nested(self):
        """COMPOSES edges should create nesting under the parent entry."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)

        engine = _find_entry(graph, "calc::CalculatorEngine")
        assert engine is not None
        # CalculatorEngine COMPOSES MethodNode (add, validateInput)
        assert "MethodNode" in engine.children
        assert "calc::CalculatorEngine::add" in engine.children["MethodNode"]
        # CalculatorEngine COMPOSES AttributeNode (precision)
        assert "AttributeNode" in engine.children
        assert "calc::CalculatorEngine::precision" in engine.children["AttributeNode"]

    def test_non_composes_edges_as_references(self):
        """Non-COMPOSES edges should be stored as references, not children."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)

        engine = _find_entry(graph, "calc::CalculatorEngine")
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
        graph = LayerGraph.deserialize(data)

        # "calc::CalculatorEngine::add" is composed by CalculatorEngine, not at root
        assert "calc::CalculatorEngine::add" not in graph.entries
        assert "calc::CalculatorEngine::precision" not in graph.entries
        # NamespaceNode "calc" should be a root entry
        assert "calc" in graph.entries

    def test_layers_are_composite_entries(self):
        """Root entries should be CompositeEntry instances."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        for entry in graph.entries.values():
            assert isinstance(entry, CompositeEntry)

    def test_layer_inference_from_data(self):
        data = [
            {"type": "ClassNode", "name": "MyClass", "kind": "class", "layer": "as-built"},
        ]
        graph = LayerGraph.deserialize(data)
        assert graph.layer == "as-built"

    def test_layer_defaults_to_design(self):
        data = [
            {"type": "ClassNode", "name": "MyClass", "kind": "class"},
        ]
        graph = LayerGraph.deserialize(data)
        assert graph.layer == "design"

    def test_empty_data(self):
        graph = LayerGraph.deserialize([])
        assert len(graph.entries) == 0
        assert graph.layer == "design"


class TestRoundtrip:
    """Integration test: deserialize → to_neo4j → serialize roundtrip."""

    def test_full_graph_roundtrip(self):
        with open(FIXTURE) as f:
            data = json.load(f)

        # Pure deserialization
        graph = LayerGraph.deserialize(data)
        assert _count_all_entries(graph) == len(data)

        # Persist
        graph.to_neo4j()

        # Serialize (nested format)
        serialized = graph.serialize()
        # Root entries only — composed children are nested, not flat
        assert len(serialized) == len(graph.entries)

        # Every node type present in the nested output
        def _collect_types(items: list[dict]) -> set[str]:
            types = set()
            for item in items:
                types.add(item["type"])
                if "composes" in item:
                    types |= _collect_types(item["composes"])
            return types

        types_in_output = _collect_types(serialized)
        types_in_input = {item["type"] for item in data}
        assert types_in_output == types_in_input

        # Write/read roundtrip via JSON
        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = FIXTURE_DIR / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(serialized, f, indent=2)
        with open(out_path) as f:
            loaded = json.load(f)

        # Deserialize back
        restored = LayerGraph.deserialize(loaded)
        assert _count_all_entries(restored) == len(data)

    def test_edge_persistence(self):
        """All fixture edges are present after to_neo4j."""
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.deserialize(data)
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
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()

        # Now fetch via from_neo4j
        design = LayerGraph.from_neo4j("design")
        assert _count_all_entries(design) > 0
        assert design.layer == "design"

        # Should include at least the ClassNode we created
        class_entries = [
            e for e in design._all_entries() if type(e.node).__name__ == "ClassNode"
        ]
        assert len(class_entries) > 0

    def test_includes_neighbors_of_layer_nodes(self):
        """Neighbors of layer-matched nodes are included even if different layer."""
        # FileNodes don't have layer, but are DEFINED_IN targets of design-layer nodes
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.deserialize(data).to_neo4j()

        design = LayerGraph.from_neo4j("design")
        # FileNodes should appear as neighbors
        file_entries = [
            e for e in design._all_entries() if type(e.node).__name__ == "FileNode"
        ]
        assert len(file_entries) > 0, "FileNodes should be included as neighbors of design nodes"

    def test_incoming_composes_nests_child_under_parent(self):
        """from_neo4j should nest children under parents even when discovered
        via incoming COMPOSES from the child side."""
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.deserialize(data).to_neo4j()

        result = LayerGraph.from_neo4j("design")
        # Methods should be nested under their parent ClassNode,
        # not appear as root entries
        add_entry = _find_entry(result, "calc::CalculatorEngine::add")
        assert add_entry is not None
        # The method should NOT be at the root level
        assert "calc::CalculatorEngine::add" not in result.entries
        # The parent class should contain the method
        engine_entry = _find_entry(result, "calc::CalculatorEngine")
        assert engine_entry is not None
        assert "MethodNode" in engine_entry.children



class TestSerializeNested:
    """Tests for LayerGraph.serialize() nested output format."""

    def test_no_composes_in_edges(self):
        """COMPOSES edges should not appear in any entry's edges array."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        def _check_no_composes(items: list[dict]) -> None:
            for item in items:
                for edge in item.get("edges", []):
                    assert edge["relation_type"] != "COMPOSES"
                _check_no_composes(item.get("composes", []))

        _check_no_composes(output)

    def test_composes_key_present_for_parents(self):
        """Entries that compose children should have a composes key."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        # NamespaceNode "calc" composes CalculatorEngine, CalculatorResult,
        # ICalculator, Operation, and formatResult
        calc_entry = next(e for e in output if e.get("name") == "calc")
        assert "composes" in calc_entry
        assert len(calc_entry["composes"]) == 5

        # CalculatorEngine composes methods + attribute
        engine_entry = next(
            c for c in calc_entry["composes"] if c.get("name") == "CalculatorEngine"
        )
        assert "composes" in engine_entry

        # FileNode has no children — no composes key
        file_entry = next(e for e in output if e.get("type") == "FileNode")
        assert "composes" not in file_entry

    def test_composed_children_not_at_root(self):
        """Composed children should not appear as top-level entries."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        # Composed children use qualified_name as keys in nested output;
        # check that short names like "add" don't appear at the root level.
        # (The serialized output uses "name" for display, not the key.)
        root_names = {e.get("name") for e in output}
        # Members are composed by their parent — their names shouldn't be at root
        assert "add" not in root_names
        assert "precision" not in root_names
        # "calc" namespace IS at root
        assert "calc" in root_names

    def test_output_written_to_file(self):
        """serialize output should be persistable and re-loadable."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = FIXTURE_DIR / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

        # Verify we can roundtrip via deserialize
        with open(out_path) as f:
            loaded = json.load(f)
        restored = LayerGraph.deserialize(loaded)
        assert _count_all_entries(restored) == _count_all_entries(graph)


class TestDeserializeNested:
    """Tests for LayerGraph.deserialize() with nested (composes) format."""

    def test_creates_nodes_from_nested_data(self):
        """Nested format should produce same total entry count as flat format."""
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        graph_flat = LayerGraph.deserialize(flat_data)
        graph_flat.to_neo4j()
        nested_data = graph_flat.serialize()

        graph_nested = LayerGraph.deserialize(nested_data)
        assert _count_all_entries(graph_nested) == _count_all_entries(graph_flat)

    def test_composes_children_nested(self):
        """COMPOSES from nested data should create nesting under parent."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        nested = graph.serialize()

        restored = LayerGraph.deserialize(nested)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children
        assert "AttributeNode" in engine.children

    def test_references_preserved(self):
        """Non-COMPOSES edges should be stored as references after nested parse."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        nested = graph.serialize()

        restored = LayerGraph.deserialize(nested)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEPENDS_ON" in ref_types
        assert "DEFINED_IN" in ref_types
        assert "COMPOSES" not in ref_types