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


class TestCompositeEntryToDict:
    """Tests for CompositeEntry.to_dict()."""

    def test_entry_to_dict_fields_all(self):
        node = ClassNode(qualified_name="ns::Widget", name="Widget", kind="class", layer="design")
        entry = CompositeEntry(node=node)
        result = entry.to_dict(fields="all")
        assert result["type"] == "ClassNode"
        assert result["qualified_name"] == "ns::Widget"
        assert result["name"] == "Widget"
        assert result["kind"] == "class"
        assert result["layer"] == "design"
        # All ClassNode properties should be present
        assert "component_id" in result
        assert "file_path" in result

    def test_entry_to_dict_fields_llm(self):
        node = ClassNode(qualified_name="ns::Widget", name="Widget", kind="class", visibility="public")
        entry = CompositeEntry(node=node)
        result = entry.to_dict(fields="llm")
        assert result["type"] == "ClassNode"
        assert result["qualified_name"] == "ns::Widget"
        # LLM fields only
        assert "visibility" in result
        # Non-LLM fields should be absent
        assert "layer" not in result
        assert "component_id" not in result

    def test_entry_to_dict_with_children(self):
        ns_node = NamespaceNode(qualified_name="calc", name="calc", kind="namespace")
        class_node = ClassNode(qualified_name="calc::Widget", name="Widget", kind="class")
        method_node = MethodNode(qualified_name="calc::Widget::draw", name="draw", kind="method")

        method_entry = CompositeEntry(node=method_node)
        class_entry = CompositeEntry(
            node=class_node,
            children={"MethodNode": {"calc::Widget::draw": method_entry}},
        )
        ns_entry = CompositeEntry(
            node=ns_node,
            children={"ClassNode": {"calc::Widget": class_entry}},
        )

        result = ns_entry.to_dict(fields="all")
        assert "composes" in result
        assert len(result["composes"]) == 1
        class_result = result["composes"][0]
        assert class_result["type"] == "ClassNode"
        assert "composes" in class_result
        method_result = class_result["composes"][0]
        assert method_result["type"] == "MethodNode"

    def test_entry_to_dict_with_references(self):
        class_node = ClassNode(qualified_name="ns::Widget", name="Widget", kind="class")
        file_node = FileNode(name="widget.h", path="/src/widget.h", refid="file-widget")

        entry = CompositeEntry(
            node=class_node,
            references=[("DEFINED_IN", "file-widget", "FileNode")],
        )
        result = entry.to_dict(fields="all")
        assert "references" in result
        assert len(result["references"]) == 1
        assert result["references"][0] == ["DEFINED_IN", "file-widget", "FileNode"]

    def test_entry_to_dict_without_children_or_references(self):
        node = ClassNode(qualified_name="ns::Widget", name="Widget", kind="class")
        entry = CompositeEntry(node=node)
        result = entry.to_dict(fields="all")
        assert "composes" not in result
        assert "references" not in result


class TestCompositeEntryFromDict:
    """Tests for CompositeEntry.from_dict()."""

    def test_from_dict_roundtrip_with_to_dict_all(self):
        ns_node = NamespaceNode(qualified_name="calc", name="calc", kind="namespace", description="A namespace")
        class_node = ClassNode(qualified_name="calc::Widget", name="Widget", kind="class", visibility="public")
        ns_entry = CompositeEntry(
            node=ns_node,
            references=[("GROUPS", "calc::Widget", "ClassNode")],
        )
        class_entry = CompositeEntry(
            node=class_node,
            children={},
            references=[("DEFINED_IN", "file-widget", "FileNode")],
        )
        ns_entry.children = {"ClassNode": {"calc::Widget": class_entry}}

        data = ns_entry.to_dict(fields="all")
        restored = CompositeEntry.from_dict(data)

        assert isinstance(restored.node, NamespaceNode)
        assert restored.node.qualified_name == "calc"
        assert restored.node.description == "A namespace"
        assert len(restored.references) == 1
        assert restored.references[0] == ("GROUPS", "calc::Widget", "ClassNode")
        assert "ClassNode" in restored.children
        child = restored.children["ClassNode"]["calc::Widget"]
        assert isinstance(child.node, ClassNode)
        assert child.node.qualified_name == "calc::Widget"
        assert len(child.references) == 1
        assert child.references[0] == ("DEFINED_IN", "file-widget", "FileNode")

    def test_from_dict_with_children(self):
        data = {
            "type": "NamespaceNode",
            "qualified_name": "calc",
            "name": "calc",
            "kind": "namespace",
            "composes": [
                {
                    "type": "ClassNode",
                    "qualified_name": "calc::Widget",
                    "name": "Widget",
                    "kind": "class",
                }
            ],
        }
        entry = CompositeEntry.from_dict(data)
        assert isinstance(entry.node, NamespaceNode)
        assert "ClassNode" in entry.children
        assert "calc::Widget" in entry.children["ClassNode"]
        child = entry.children["ClassNode"]["calc::Widget"]
        assert isinstance(child.node, ClassNode)

    def test_from_dict_with_references(self):
        data = {
            "type": "ClassNode",
            "qualified_name": "ns::Widget",
            "name": "Widget",
            "kind": "class",
            "references": [
                ["DEFINED_IN", "file-widget", "FileNode"],
                ["REALIZES", "ns::IWidget", "InterfaceNode"],
            ],
        }
        entry = CompositeEntry.from_dict(data)
        assert len(entry.references) == 2
        assert entry.references[0] == ("DEFINED_IN", "file-widget", "FileNode")
        assert entry.references[1] == ("REALIZES", "ns::IWidget", "InterfaceNode")

    def test_from_dict_nested_children(self):
        data = {
            "type": "NamespaceNode",
            "qualified_name": "calc",
            "name": "calc",
            "kind": "namespace",
            "composes": [
                {
                    "type": "ClassNode",
                    "qualified_name": "calc::Widget",
                    "name": "Widget",
                    "kind": "class",
                    "composes": [
                        {
                            "type": "MethodNode",
                            "qualified_name": "calc::Widget::draw",
                            "name": "draw",
                            "kind": "method",
                        }
                    ],
                }
            ],
        }
        entry = CompositeEntry.from_dict(data)
        assert isinstance(entry.node, NamespaceNode)
        class_child = entry.children["ClassNode"]["calc::Widget"]
        assert isinstance(class_child.node, ClassNode)
        method_child = class_child.children["MethodNode"]["calc::Widget::draw"]
        assert isinstance(method_child.node, MethodNode)


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


class TestLayerGraphToDict:
    """Tests for LayerGraph.to_dict()."""

    def test_to_dict_fields_all(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result = graph.to_dict(fields="all")
        assert result["layer"] == "design"
        assert "entries" in result
        assert len(result["entries"]) > 0

    def test_to_dict_all_includes_all_properties(self):
        """to_dict(fields='all') includes non-LLM properties like layer, component_id."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result = graph.to_dict(fields="all")

        # Find the CalculatorEngine entry (nested under its namespace)
        engine = _find_entry(graph, "calc::CalculatorEngine")
        assert engine is not None
        engine_dict = engine.to_dict(fields="all")
        # Properties that serialize() would omit but to_dict(fields='all') includes
        assert "layer" in engine_dict
        assert "file_path" in engine_dict
        assert "line_number" in engine_dict

    def test_to_dict_fields_llm(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result = graph.to_dict(fields="llm")
        assert result["layer"] == "design"
        assert len(result["entries"]) > 0

    def test_to_dict_llm_excludes_non_llm_fields(self):
        """to_dict(fields='llm') omits non-LLM properties like layer, component_id."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result = graph.to_dict(fields="llm")

        # Walk entries recursively checking for non-LLM fields
        def _check_llm_only(entries):
            for entry_data in entries:
                # Non-LLM fields should not be present
                assert "component_id" not in entry_data
                assert "file_path" not in entry_data
                if "composes" in entry_data:
                    _check_llm_only(entry_data["composes"])

        _check_llm_only(result["entries"])

    def test_to_dict_preserves_composition_structure(self):
        """to_dict output has composes nesting matching to_json structure."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result = graph.to_dict(fields="all")

        # Namespace should have composes
        calc_entries = [e for e in result["entries"] if e.get("qualified_name") == "calc"]
        assert len(calc_entries) == 1
        calc_entry = calc_entries[0]
        assert "composes" in calc_entry
        # CalculatorEngine should be in composes
        engine_entries = [c for c in calc_entry["composes"] if c.get("qualified_name") == "calc::CalculatorEngine"]
        assert len(engine_entries) == 1

    def test_to_dict_roundtrip_all(self):
        """from_json(data) -> to_dict(fields='all') -> from_dict -> to_dict(fields='all'), compare."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result1 = graph.to_dict(fields="all")

        # Roundtrip through from_dict
        restored = LayerGraph.from_dict(result1)
        result2 = restored.to_dict(fields="all")

        # Same number of root entries
        assert len(result1["entries"]) == len(result2["entries"])
        # Same total entry count
        assert _count_all_entries(graph) == _count_all_entries(restored)

    def test_to_dict_roundtrip_llm(self):
        """from_json(data) -> to_dict(fields='llm') -> from_dict -> to_dict(fields='llm'), compare."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result1 = graph.to_dict(fields="llm")

        restored = LayerGraph.from_dict(result1)
        result2 = restored.to_dict(fields="llm")

        assert len(result1["entries"]) == len(result2["entries"])


class TestLayerGraphFromDict:
    """Tests for LayerGraph.from_dict()."""

    def test_from_dict_with_layer_and_entries(self):
        """from_dict accepts {"layer": ..., "entries": [...]} format."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        dict_data = graph.to_dict(fields="all")
        restored = LayerGraph.from_dict(dict_data)
        assert restored.layer == "design"
        assert _count_all_entries(restored) == _count_all_entries(graph)

    def test_from_dict_bare_list_backward_compat(self):
        """from_dict accepts a bare list (legacy from_json format)."""
        with open(FIXTURE) as f:
            data = json.load(f)
        restored = LayerGraph.from_dict(data)
        assert restored.layer == "design"
        assert _count_all_entries(restored) == len(data)

    def test_from_dict_roundtrip_all(self):
        """from_json(data) -> to_dict(fields='all') -> from_dict() -> to_dict(fields='all')."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result1 = graph.to_dict(fields="all")
        restored = LayerGraph.from_dict(result1)
        result2 = restored.to_dict(fields="all")

        assert len(result1["entries"]) == len(result2["entries"])
        assert _count_all_entries(graph) == _count_all_entries(restored)

    def test_from_dict_roundtrip_llm(self):
        """Round-trip with LLM fields."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        result1 = graph.to_dict(fields="llm")
        restored = LayerGraph.from_dict(result1)
        result2 = restored.to_dict(fields="llm")

        assert len(result1["entries"]) == len(result2["entries"])

    def test_from_dict_preserves_all_properties(self):
        """After round-trip with fields='all', non-LLM properties survive."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        dict_data = graph.to_dict(fields="all")
        restored = LayerGraph.from_dict(dict_data)

        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert engine.node.layer == "design"
        # These properties are NOT in _llm_fields but should survive round-trip
        assert hasattr(engine.node, "component_id")
        assert hasattr(engine.node, "file_path")

    def test_from_dict_preserves_composition_structure(self):
        """Children and references survive round-trip."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        dict_data = graph.to_dict(fields="all")
        restored = LayerGraph.from_dict(dict_data)

        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children
        assert "AttributeNode" in engine.children
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEFINED_IN" in ref_types

    def test_from_dict_invalid_layer_raises(self):
        """Passing invalid layer data raises ValueError."""
        dict_data = {
            "layer": "unknown",
            "entries": [
                {"type": "ClassNode", "name": "X", "kind": "class"},
            ],
        }
        with pytest.raises(ValueError, match="Invalid layer"):
            LayerGraph.from_dict(dict_data)


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
        graph = LayerGraph.from_json(data)

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
        graph = LayerGraph.from_json(data)

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
        graph = LayerGraph.from_json(data)

        # "calc::CalculatorEngine::add" is composed by CalculatorEngine, not at root
        assert "calc::CalculatorEngine::add" not in graph.entries
        assert "calc::CalculatorEngine::precision" not in graph.entries
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

        # Serialize (nested format)
        serialized = graph.to_json()
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
            e for e in design._all_entries() if type(e.node).__name__ == "ClassNode"
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
            e for e in design._all_entries() if type(e.node).__name__ == "FileNode"
        ]
        assert len(file_entries) > 0, "FileNodes should be included as neighbors of design nodes"

    def test_incoming_composes_nests_child_under_parent(self):
        """from_neo4j should nest children under parents even when discovered
        via incoming COMPOSES from the child side."""
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.from_json(data).to_neo4j()

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



class TestToJsonNested:
    """Tests for LayerGraph.to_json() nested output format."""

    def test_no_composes_in_edges(self):
        """COMPOSES edges should not appear in any entry's edges array."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

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
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

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
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

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
        """to_json output should be persistable and re-loadable."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = FIXTURE_DIR / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

        # Verify we can roundtrip via from_json
        with open(out_path) as f:
            loaded = json.load(f)
        restored = LayerGraph.from_json(loaded)
        assert _count_all_entries(restored) == _count_all_entries(graph)


class TestFromJsonNested:
    """Tests for LayerGraph.from_json() with nested (composes) format."""

    def test_creates_nodes_from_nested_data(self):
        """Nested format should produce same total entry count as flat format."""
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        graph_flat = LayerGraph.from_json(flat_data)
        graph_flat.to_neo4j()
        nested_data = graph_flat.to_json()

        graph_nested = LayerGraph.from_json(nested_data)
        assert _count_all_entries(graph_nested) == _count_all_entries(graph_flat)

    def test_composes_children_nested(self):
        """COMPOSES from nested data should create nesting under parent."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        nested = graph.to_json()

        restored = LayerGraph.from_json(nested)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children
        assert "AttributeNode" in engine.children

    def test_references_preserved(self):
        """Non-COMPOSES edges should be stored as references after nested parse."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        nested = graph.to_json()

        restored = LayerGraph.from_json(nested)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEPENDS_ON" in ref_types
        assert "DEFINED_IN" in ref_types
        assert "COMPOSES" not in ref_types

    def test_from_dict_with_flat_format_edges(self):
        """from_dict handles flat format with edges arrays."""
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        restored = LayerGraph.from_dict(flat_data)
        assert _count_all_entries(restored) == len(flat_data)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children

    def test_from_dict_with_nested_format_composes(self):
        """from_dict handles nested format with composes/references."""
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        graph = LayerGraph.from_json(flat_data)
        dict_data = graph.to_dict(fields="all")
        restored = LayerGraph.from_dict(dict_data)
        assert _count_all_entries(restored) == _count_all_entries(graph)
        engine = _find_entry(restored, "calc::CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEFINED_IN" in ref_types