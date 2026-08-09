"""Tests for codegraph.export.viz — Cytoscape HTML export.

Unit tests run without Neo4j. Integration tests require Neo4j and
are marked with ``@pytest.mark.integration``.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models import ClassNode, MethodNode, AttributeNode, NamespaceNode
from codegraph.export.viz.transform import layer_graph_to_cytoscape
from codegraph.export.viz.styles import cy_stylesheet, KIND_COLORS, EDGE_COLORS
from codegraph.export.viz.labels import build_uml_html
from codegraph.export.viz import export_html, export_html_from_json


# ---------------------------------------------------------------------------
# Unit tests (no Neo4j needed)
# ---------------------------------------------------------------------------


def test_cy_stylesheet_produces_valid_structure():
    """Stylesheet output is a list of dicts with selector and style keys."""
    styles = cy_stylesheet(size="large")
    # codegraph:test-desc test_viz.test_cy_stylesheet_produces_valid_structure::post_0
    # Checks that the output of `cy_stylesheet` is a list, which is the expected
    # container type for a stylesheet consisting of multiple style entries.
    assert isinstance(styles, list)
    # codegraph:test-desc test_viz.test_cy_stylesheet_produces_valid_structure::post_1
    # Ensures that the stylesheet list is not empty, which confirms that at least one
    # style rule was generated for the nodes or edges in the graph.
    assert len(styles) > 0
    for entry in styles:
        # codegraph:test-desc test_viz.test_cy_stylesheet_produces_valid_structure::post_2
        # Verifies that each entry in the stylesheet list contains a 'selector' key,
        # confirming that every style rule specifies which elements it applies to.
        assert "selector" in entry
        # codegraph:test-desc test_viz.test_cy_stylesheet_produces_valid_structure::post_3
        # Verifies that each entry in the stylesheet list contains a 'style' key,
        # ensuring that every selector has an associated set of visual properties.
        assert "style" in entry


def test_cy_stylesheet_small_size():
    """Small size produces different font dimensions."""
    styles = cy_stylesheet(size="small")
    # codegraph:test-desc test_viz.test_cy_stylesheet_small_size::post_0
    # Verifies that the generated styles list is non-empty, ensuring that the
    # cy_stylesheet function produces valid output for a small size input.
    assert len(styles) > 0


def test_cy_stylesheet_has_all_layer_selectors():
    """Verify design, as-built, and dependency selectors exist."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_all_layer_selectors::post_0
    # Verifies that the stylesheet contains a selector for design-layer nodes without
    # members, ensuring design artifacts are visually distinguishable when collapsed.
    assert 'node[layer="design"][!has_members]' in selectors
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_all_layer_selectors::post_1
    # Verifies that the stylesheet contains a selector for as-built-layer nodes without
    # members, ensuring as-built artifacts are visually distinguishable when collapsed.
    assert 'node[layer="as-built"][!has_members]' in selectors
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_all_layer_selectors::post_2
    # Verifies that the stylesheet contains a selector for dependency-layer nodes
    # without members, ensuring that dependency artifacts are visually distinguishable
    # when collapsed.
    assert 'node[layer="dependency"][!has_members]' in selectors


def test_cy_stylesheet_has_uml_box_selectors():
    """Verify UML box selectors exist for all layers."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_uml_box_selectors::post_0
    # Verifies that the stylesheet includes a CSS selector for nodes with members in the
    # 'design' layer, ensuring that UML box nodes in this layer are visually distinct.
    assert 'node[has_members="true"][layer="design"]' in selectors
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_uml_box_selectors::post_1
    # Verifies that the stylesheet includes a CSS selector for nodes with members in the
    # 'as-built' layer, ensuring that UML box nodes in this layer are visually distinct.
    assert 'node[has_members="true"][layer="as-built"]' in selectors
    # codegraph:test-desc test_viz.test_cy_stylesheet_has_uml_box_selectors::post_2
    # Verifies that the stylesheet includes a CSS selector for nodes with members in the
    # 'dependency' layer, ensuring that UML box nodes in this layer are visually
    # distinct.
    assert 'node[has_members="true"][layer="dependency"]' in selectors


def test_color_constants():
    """Color maps are non-empty dicts."""
    # codegraph:test-desc test_viz.test_color_constants::post_0
    # Verifies that the KIND_COLORS dictionary is not empty, ensuring at least one kind
    # color mapping is defined to support visualization.
    assert len(KIND_COLORS) > 0
    # codegraph:test-desc test_viz.test_color_constants::post_1
    # Verifies that the EDGE_COLORS dictionary is not empty, ensuring at least one edge
    # color mapping is defined to support visualization.
    assert len(EDGE_COLORS) > 0
    # codegraph:test-desc test_viz.test_color_constants::post_2
    # Verifies that the KIND_COLORS dictionary includes a mapping for the 'class' kind,
    # ensuring class symbols are assigned a color in visualizations.
    assert "class" in KIND_COLORS
    # codegraph:test-desc test_viz.test_color_constants::post_3
    # Verifies that the EDGE_COLORS dictionary includes a specific key for the
    # 'INHERITS_FROM' relationship, ensuring inheritance relationships are visually
    # distinguished.
    assert "INHERITS_FROM" in EDGE_COLORS
    # codegraph:test-desc test_viz.test_color_constants::post_4
    # Verifies that the EDGE_COLORS dictionary contains a 'default' key, ensuring a
    # fallback color is always available for edges that do not match any specific
    # relationship type.
    assert "default" in EDGE_COLORS


def test_cy_stylesheet_has_edge_type_overrides():
    """Verify that key edge types have style overrides."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    for edge_type in ("INHERITS_FROM", "DEPENDS_ON", "REFERENCES", "AGGREGATES"):
        # codegraph:test-desc test_viz.test_cy_stylesheet_has_edge_type_overrides::post_0
        # Verifies that each expected edge type has a corresponding style override
        # present in the generated stylesheet selectors, ensuring that all key edges are
        # visually distinguished as required.
        assert f'edge[label="{edge_type}"]' in selectors, f"Missing edge style for {edge_type}"


def test_build_uml_html_basic():
    """build_uml_html produces an HTML string with member content."""
    by_kind = {
        "method": [
            {
                "name": "add",
                "visibility": "public",
                "type_signature": "int",
                "argsstring": "(int a, int b)",
                "source": "test", "qualified_name": "calc::Calculator::add",
                "layer": "design",
            }
        ]
    }
    result = build_uml_html("Calculator", by_kind, owner_kind="class")
    # codegraph:test-desc test_viz.test_build_uml_html_basic::post_0
    # Confirms the class name 'Calculator' appears in the result, validating that the
    # generated HTML represents the intended UML element.
    assert "Calculator" in result
    # codegraph:test-desc test_viz.test_build_uml_html_basic::post_1
    # Checks that the HTML includes the method name 'add', ensuring that member content
    # (methods) are correctly rendered in the output.
    assert "add" in result
    # codegraph:test-desc test_viz.test_build_uml_html_basic::post_2
    # Verifies that the generated HTML contains a '<div' element, confirming the output
    # has proper HTML structure.
    assert "<div" in result


def test_build_uml_html_with_stereotype():
    """Stereotype appears for interfaces."""
    by_kind: dict[str, list] = {}
    result = build_uml_html("IPlugin", by_kind, owner_kind="interface")
    # codegraph:test-desc test_viz.test_build_uml_html_with_stereotype::post_0
    # This assertion verifies that the word 'interface' appears in the generated UML
    # HTML label, confirming that the stereotype for interfaces is correctly included in
    # the output.
    assert "interface" in result.lower()


def test_build_uml_html_enum():
    """Enum nodes show enum values."""
    by_kind = {
        "enum_value": [
            {"name": "RED", "visibility": "public", "type_signature": "",
             "argsstring": "", "source": "test", "qualified_name": "Color::RED", "layer": "design"},
            {"name": "GREEN", "visibility": "public", "type_signature": "",
             "argsstring": "", "source": "test", "qualified_name": "Color::GREEN", "layer": "design"},
        ]
    }
    result = build_uml_html("Color", by_kind, owner_kind="enum")
    # codegraph:test-desc test_viz.test_build_uml_html_enum::post_0
    # Verifies that the enum value 'RED' is present in the resulting UML HTML, ensuring
    # the build_uml_html function correctly renders all enum options.
    assert "RED" in result
    # codegraph:test-desc test_viz.test_build_uml_html_enum::post_1
    # Confirms that the enum value 'GREEN' is included in the generated UML HTML,
    # validating that all defined enum values are correctly displayed.
    assert "GREEN" in result


def test_build_uml_html_respects_visibility_order():
    """Public members appear first in output."""
    by_kind = {
        "attribute": [
            {"name": "private_attr", "visibility": "private", "type_signature": "int",
             "argsstring": "", "source": "test", "qualified_name": "Foo::private_attr", "layer": "design"},
            {"name": "public_attr", "visibility": "public", "type_signature": "str",
             "argsstring": "", "source": "test", "qualified_name": "Foo::public_attr", "layer": "design"},
        ]
    }
    result = build_uml_html("Foo", by_kind, owner_kind="class")
    pub_idx = result.index("public_attr")
    priv_idx = result.index("private_attr")
    # codegraph:test-desc test_viz.test_build_uml_html_respects_visibility_order::post_0
    # Verifies that the indices of public members in the output are less than those of
    # private members, confirming that the function places public members before private
    # ones as required by the specification.
    assert pub_idx < priv_idx, "public members should appear before private"


def test_layer_graph_to_cytoscape_empty_graph():
    """Empty LayerGraph produces empty nodes/edges."""
    graph = LayerGraph(tags=frozenset({"design"}), entries={})
    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_empty_graph::post_0
    # Confirms that the 'nodes' list in the result is empty, ensuring the conversion
    # correctly handles an empty graph.
    assert result["nodes"] == []
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_empty_graph::post_1
    # Confirms that the 'edges' list in the result is empty, ensuring the conversion
    # correctly handles an empty graph.
    assert result["edges"] == []


def test_layer_graph_to_cytoscape_single_class():
    """A simple ClassNode without members renders as a Cy node."""
    cls = ClassNode.deserialize({
        "type": "ClassNode",
        "name": "Calculator",
        "source": "test", "qualified_name": "calc::Calculator",
        "kind": "class",
        "tags": ["design"],
        "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"design"}), entries={"calc::Calculator": entry})

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_0
    # Confirms the result contains exactly one node, validating that the transform
    # outputs the expected number of graph elements for a single class input.
    assert len(result["nodes"]) == 1
    node_data = result["nodes"][0]["data"]
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_1
    # Verifies the node's `qualified_name` is 'calc::Calculator', ensuring the fully
    # qualified name is accurately carried over.
    assert node_data["qualified_name"] == "calc::Calculator"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_2
    # Asserts the node's `label` is set to 'Calculator', checking that the simple class
    # name is correctly extracted as the display label.
    assert node_data["label"] == "Calculator"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_3
    # Checks that `kind` is 'class', validating the transform correctly identifies and
    # labels the node's type.
    assert node_data["kind"] == "class"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_4
    # Verifies that the node's `layer` field equals 'design', confirming the transform
    # correctly preserves the layer attribute from the original ClassNode.
    assert node_data["layer"] == "design"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_single_class::post_5
    # Ensures the node does not contain a `has_members` key, confirming that a class
    # without members is rendered without that property.
    assert "has_members" not in node_data


def test_layer_graph_to_cytoscape_class_with_members():
    """A class with composed methods produces UML label."""
    method = MethodNode.deserialize({
        "type": "MethodNode",
        "name": "add",
        "source": "test", "qualified_name": "calc::Calculator::add",
        "kind": "method",
        "tags": ["design"],
        "visibility": "public",
        "type_signature": "int",
        "argsstring": "(int a, int b)",
        "edges": [],
    })
    cls = ClassNode.deserialize({
        "type": "ClassNode",
        "name": "Calculator",
        "source": "test", "qualified_name": "calc::Calculator",
        "kind": "class",
        "tags": ["design"],
        "visibility": "public",
        "edges": [],
    })
    cls_entry = CompositeEntry(node=cls)
    cls_entry.children["MethodNode"] = {
        "calc::Calculator::add": CompositeEntry(node=method)
    }
    graph = LayerGraph(
        tags=frozenset({"design"}), entries={"calc::Calculator": cls_entry}
    )

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_class_with_members::post_0
    # Asserts the conversion outputs exactly one node, ensuring the entire class (with
    # its method) is treated as a single node rather than being split.
    assert len(result["nodes"]) == 1  # only the class, not the method
    node_data = result["nodes"][0]["data"]
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_class_with_members::post_1
    # Verifies that the node_data flag 'has_members' is set to 'true', confirming the
    # conversion correctly identifies that the class contains methods.
    assert node_data["has_members"] == "true"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_class_with_members::post_2
    # Checks that an 'html_label' key exists in node_data, confirming the conversion
    # generates an HTML label for the node as required for Cytoscape display.
    assert "html_label" in node_data
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_class_with_members::post_3
    # Validates that the method name 'add' appears inside the HTML label, ensuring
    # composed methods are included in the UML label representation.
    assert "add" in node_data["html_label"]


def test_layer_graph_to_cytoscape_with_edges():
    """References between nodes produce Cytoscape edges."""
    cls_a = ClassNode.deserialize({
        "type": "ClassNode", "name": "A", "source": "test", "qualified_name": "ns::A",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_b = ClassNode.deserialize({
        "type": "ClassNode", "name": "B", "source": "test", "qualified_name": "ns::B",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    entry_a = CompositeEntry(node=cls_a)
    entry_b = CompositeEntry(node=cls_b)
    entry_a.references = [("DEPENDS_ON", "ns::B", "ClassNode")]

    graph = LayerGraph(
        tags=frozenset({"design"}),
        entries={"ns::A": entry_a, "ns::B": entry_b},
    )

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_edges::post_0
    # Verifies that the result contains exactly two nodes, ensuring the transformation
    # correctly outputs both classes from the layer graph.
    assert len(result["nodes"]) == 2
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_edges::post_1
    # Verifies that the result contains exactly one edge, ensuring the single dependency
    # relationship is correctly transformed into a Cytoscape edge.
    assert len(result["edges"]) == 1
    edge = result["edges"][0]["data"]
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_edges::post_2
    # Verifies that the single edge's source is 'ns::A', confirming that the generated
    # edge correctly originates from the source node in the namespace.
    assert edge["source"] == "ns::A"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_edges::post_3
    # Verifies that the single edge's target is 'ns::B', confirming that the generated
    # edge correctly points to the intended dependent node in the namespace.
    assert edge["target"] == "ns::B"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_edges::post_4
    # Verifies that the edge's label is 'DEPENDS_ON', confirming that the transformation
    # correctly assigns the dependency type to the relationship.
    assert edge["label"] == "DEPENDS_ON"


def test_layer_graph_to_cytoscape_with_namespace():
    """Namespace nodes get is_namespace flag and children get parent."""
    ns = NamespaceNode.deserialize({
        "type": "NamespaceNode", "name": "calc",
        "source": "test", "qualified_name": "calc", "kind": "namespace",
        "tags": ["design"], "edges": [],
    })
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Calculator",
        "source": "test", "qualified_name": "calc::Calculator", "kind": "class",
        "tags": ["design"], "visibility": "public", "edges": [],
    })
    ns_entry = CompositeEntry(node=ns)
    ns_entry.children["ClassNode"] = {
        "calc::Calculator": CompositeEntry(node=cls)
    }
    graph = LayerGraph(tags=frozenset({"design"}), entries={"calc": ns_entry})

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_namespace::post_0
    # Verifies that exactly two nodes were produced. This confirms the transformation
    # correctly captures the namespace and the contained class node.
    assert len(result["nodes"]) == 2
    ns_data = next(
        n["data"] for n in result["nodes"] if n["data"]["qualified_name"] == "calc"
    )
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_namespace::post_1
    # Checks that the namespace node has an 'is_namespace' flag set to 'true'. This is
    # essential because the requirement specifies that namespace nodes must be
    # distinctly identified in the output.
    assert ns_data["is_namespace"] == "true"
    cls_data = next(
        n["data"] for n in result["nodes"] if n["data"]["qualified_name"] == "calc::Calculator"
    )
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_with_namespace::post_2
    # Asserts that the class node's 'parent' attribute equals 'calc', meaning it is
    # correctly tagged as a child of the namespace. This validates the parent-child
    # relationship is preserved in the export.
    assert cls_data.get("parent") == "calc"


def test_layer_graph_to_cytoscape_method_reference_becomes_edge():
    """A reference from a collapsed method becomes an edge from the parent."""
    method = MethodNode.deserialize({
        "type": "MethodNode", "name": "calculate",
        "source": "test", "qualified_name": "calc::Engine::calculate", "kind": "method",
        "tags": ["design"], "visibility": "public", "edges": [],
    })
    cls_engine = ClassNode.deserialize({
        "type": "ClassNode", "name": "Engine",
        "source": "test", "qualified_name": "calc::Engine",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_result = ClassNode.deserialize({
        "type": "ClassNode", "name": "Result",
        "source": "test", "qualified_name": "calc::Result",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })

    engine_entry = CompositeEntry(node=cls_engine)
    method_entry = CompositeEntry(node=method)
    method_entry.references = [("RETURNS", "calc::Result", "ClassNode")]
    engine_entry.children["MethodNode"] = {
        "calc::Engine::calculate": method_entry
    }
    result_entry = CompositeEntry(node=cls_result)

    graph = LayerGraph(
        tags=frozenset({"design"}),
        entries={"calc::Engine": engine_entry, "calc::Result": result_entry},
    )

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_method_reference_becomes_edge::post_0
    # Verifies that two nodes (Engine and Result class entries) are present in the
    # output, confirming that the transformation preserves the parent classes while
    # omitting the collapsed method node.
    assert len(result["nodes"]) == 2  # Engine + Result (method collapsed)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_method_reference_becomes_edge::post_1
    # Verifies that exactly one edge was created, confirming that the method's
    # return-type reference generates a single edge rather than multiple or none.
    assert len(result["edges"]) == 1
    edge = result["edges"][0]["data"]
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_method_reference_becomes_edge::post_2
    # Verifies that the edge representing the method reference originates from the
    # expected source class 'calc::Engine', ensuring the source node is correctly
    # identified.
    assert edge["source"] == "calc::Engine"  # edge from parent, not method
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_method_reference_becomes_edge::post_3
    # Verifies that the edge points to the correct target class 'calc::Result', ensuring
    # the reference maps to the intended destination.
    assert edge["target"] == "calc::Result"
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_method_reference_becomes_edge::post_4
    # Verifies that the edge label is 'RETURNS', confirming the correct categorization
    # of the reference as a return-type relationship.
    assert edge["label"] == "RETURNS"


def test_layer_graph_to_cytoscape_excludes_implementation_node():
    """ImplementationNode references are excluded from edges."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Foo", "source": "test", "qualified_name": "ns::Foo",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    entry.references = [("IMPLEMENTS", "impl_123", "ImplementationNode")]

    graph = LayerGraph(tags=frozenset({"design"}), entries={"ns::Foo": entry})
    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_excludes_implementation_node::post_0
    # Verifies that no edges remain in the Cytoscape output after conversion, confirming
    # that the function correctly excludes edges referencing ImplementationNode objects.
    assert len(result["edges"]) == 0


def test_layer_graph_to_cytoscape_as_built_layer():
    """as-built tag produces layer='as-built' in node data."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Foo", "source": "test", "qualified_name": "ns::Foo",
        "kind": "class", "tags": ["as-built"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"as-built"}), entries={"ns::Foo": entry})

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_as_built_layer::post_0
    # Verifies that exactly one node is produced, ensuring the input graph's single
    # entry is correctly transformed into a single Cytoscape node.
    assert len(result["nodes"]) == 1
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_as_built_layer::post_1
    # Confirms that the node's 'layer' data field equals 'as-built', verifying that the
    # as-built tag is correctly propagated into the output node's metadata.
    assert result["nodes"][0]["data"]["layer"] == "as-built"


def test_layer_graph_to_cytoscape_dependency_layer():
    """dependency tag produces layer='dependency' in node data."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "ExtLib", "source": "test", "qualified_name": "ext::Lib",
        "kind": "class", "tags": ["dependency"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"dependency"}), entries={"ext::Lib": entry})

    result = layer_graph_to_cytoscape(graph)
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_dependency_layer::post_0
    # Verifies that exactly one node is produced by the transformation, ensuring the
    # input graph is correctly converted without spurious nodes.
    assert len(result["nodes"]) == 1
    # codegraph:test-desc test_viz.test_layer_graph_to_cytoscape_dependency_layer::post_1
    # Confirms that the single node's 'layer' data field equals 'dependency', validating
    # that dependency-layer tagging works as expected in the export output.
    assert result["nodes"][0]["data"]["layer"] == "dependency"


def test_edge_ids_are_unique():
    """Multiple edges from same source to different targets have unique IDs."""
    cls_a = ClassNode.deserialize({
        "type": "ClassNode", "name": "A", "source": "test", "qualified_name": "ns::A",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_b = ClassNode.deserialize({
        "type": "ClassNode", "name": "B", "source": "test", "qualified_name": "ns::B",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_c = ClassNode.deserialize({
        "type": "ClassNode", "name": "C", "source": "test", "qualified_name": "ns::C",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    entry_a = CompositeEntry(node=cls_a)
    entry_a.references = [
        ("DEPENDS_ON", "ns::B", "ClassNode"),
        ("DEPENDS_ON", "ns::C", "ClassNode"),
    ]

    graph = LayerGraph(
        tags=frozenset({"design"}),
        entries={"ns::A": entry_a, "ns::B": CompositeEntry(node=cls_b),
                 "ns::C": CompositeEntry(node=cls_c)},
    )

    result = layer_graph_to_cytoscape(graph)
    edge_ids = [e["data"]["id"] for e in result["edges"]]
    # codegraph:test-desc test_viz.test_edge_ids_are_unique::post_0
    # Verifies that all generated edge IDs are unique by comparing the count of IDs to
    # the count of unique IDs, ensuring the Cytoscape transformation does not produce
    # duplicate edge identifiers which could cause display or data integrity issues.
    assert len(edge_ids) == len(set(edge_ids)), f"Duplicate edge IDs: {edge_ids}"


# ---------------------------------------------------------------------------
# Integration tests (require Neo4j)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_export_html_writes_valid_file():
    """export_html writes a valid HTML file (requires Neo4j with data)."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        output_path = f.name

    try:
        result_path = export_html("design", output_path, size="small")
        # codegraph:test-desc test_viz.test_export_html_writes_valid_file::post_0
        # Verifies that the exported file is written to the expected output path by
        # comparing the real paths, ensuring the file is saved in the correct location.
        assert os.path.realpath(result_path) == os.path.realpath(output_path)
        html = Path(output_path).read_text(encoding="utf-8")

        # Structural checks
        # codegraph:test-desc test_viz.test_export_html_writes_valid_file::post_1
        # Checks that the exported file starts with the '<!DOCTYPE html>' declaration,
        # confirming it is a valid HTML document.
        assert "<!DOCTYPE html>" in html
        # codegraph:test-desc test_viz.test_export_html_writes_valid_file::post_2
        # Confirms that the HTML content includes the term 'cytoscape', indicating the
        # visualization library is properly referenced for rendering the graph.
        assert "cytoscape" in html.lower()
        # codegraph:test-desc test_viz.test_export_html_writes_valid_file::post_3
        # Checks for the presence of 'fcose' in the HTML, confirming that the fcose
        # layout algorithm is included as part of the graph rendering setup.
        assert "fcose" in html
        # codegraph:test-desc test_viz.test_export_html_writes_valid_file::post_4
        # Asserts that the HTML contains the element with id 'cy', which is the
        # container where Cytoscape.js renders the graph, verifying the core
        # visualization structure.
        assert 'id="cy"' in html
    finally:
        Path(output_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_export_html_empty_tag_produces_valid_file():
    """export_html with an empty/non-existent tag produces valid HTML."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        output_path = f.name

    try:
        result_path = export_html("scaffold", output_path)
        # codegraph:test-desc test_viz.test_export_html_empty_tag_produces_valid_file::post_0
        # Checks that the exported HTML file was actually saved to the expected
        # location, confirming the export operation completed and produced an output
        # file at the designated path.
        assert os.path.realpath(result_path) == os.path.realpath(output_path)
        html = Path(output_path).read_text(encoding="utf-8")
        # codegraph:test-desc test_viz.test_export_html_empty_tag_produces_valid_file::post_1
        # Confirms the output starts with a valid DOCTYPE declaration, which is
        # necessary for the HTML file to be interpreted correctly by browsers and to
        # meet basic web standards.
        assert "<!DOCTYPE html>" in html
        # codegraph:test-desc test_viz.test_export_html_empty_tag_produces_valid_file::post_2
        # Verifies that the generated HTML contains a tag with id="cy", ensuring the
        # empty tag does not break the structure and that essential placeholder elements
        # are present.
        assert 'id="cy"' in html
    finally:
        Path(output_path).unlink(missing_ok=True)


def test_jinja2_template_exists():
    """The graph.html.j2 template is packaged with the module."""
    import codegraph.export.viz
    template_dir = (
        Path(codegraph.export.viz.__file__).resolve().parent.parent / "templates"
    )
    # codegraph:test-desc test_viz.test_jinja2_template_exists::post_0
    # Confirms that the template directory itself exists, which is a prerequisite for
    # any template files to be present, preventing runtime errors when the module
    # attempts to access the directory.
    assert template_dir.is_dir(), f"Template directory not found: {template_dir}"
    # codegraph:test-desc test_viz.test_jinja2_template_exists::post_1
    # Verifies that the specific template file 'graph.html.j2' exists within the
    # template directory, ensuring the visualization module can load its HTML template
    # for rendering.
    assert (template_dir / "graph.html.j2").is_file()


def test_export_html_function_signature():
    """export_html has the expected parameters."""
    import inspect
    sig = inspect.signature(export_html)
    params = list(sig.parameters.keys())
    # codegraph:test-desc test_viz.test_export_html_function_signature::post_0
    # Verifies that 'tag' is among the parameters of the export_html function,
    # confirming that the function accepts a required tag argument for identifying the
    # exported content.
    assert "tag" in params
    # codegraph:test-desc test_viz.test_export_html_function_signature::post_1
    # Verifies that 'output_path' is among the parameters of the export_html function,
    # ensuring the function accepts a required output location argument.
    assert "output_path" in params
    # codegraph:test-desc test_viz.test_export_html_function_signature::post_2
    # Verifies that 'size' is among the parameters of the export_html function,
    # confirming the function supports an optional sizing argument.
    assert "size" in params


def test_cy_stylesheet_darken():
    """The _darken helper produces correct colors."""
    from codegraph.export.viz.styles import _darken

    # codegraph:test-desc test_viz.test_cy_stylesheet_darken::post_0
    # Asserts that the first color darkened by the helper equals the expected result,
    # validating the core functionality of the _darken routine.
    assert _darken("#ffffff", 0.5) == "#7f7f7f"
    # codegraph:test-desc test_viz.test_cy_stylesheet_darken::post_1
    # Checks that the second color output from _darken matches the expected darkened
    # result, confirming consistent behavior across distinct inputs.
    assert _darken("#000000", 1.0) == "#000000"
    # codegraph:test-desc test_viz.test_cy_stylesheet_darken::post_2
    # Verifies that the third color produced by _darken matches the expected darkened
    # value, ensuring the helper correctly processes multiple cases.
    assert _darken("#ff0000", 0.5) == "#7f0000"
    # factor=0 should produce black
    # codegraph:test-desc test_viz.test_cy_stylesheet_darken::post_3
    # Confirms that the fourth color returned by _darken equals the expected darkened
    # value, covering another variant to validate the helper's correctness.
    assert _darken("#abcdef", 0.0) == "#000000"


# ---------------------------------------------------------------------------
# export_html_from_json tests (no Neo4j required)
# ---------------------------------------------------------------------------


def test_export_html_from_json_writes_valid_file(tmp_path):
    """export_html_from_json reads a JSON file and writes valid HTML."""
    from codegraph.uid import compute_uid

    # Minimal graph data with uid fields
    data = [
        {"type": "ClassNode", "name": "Engine", "kind": "class",
         "source": "test", "qualified_name": "ns::Engine", "tags": ["design"],
         "uid": compute_uid("ns::Engine"), "edges": []},
    ]
    json_path = tmp_path / "graph.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    html_path = tmp_path / "out.html"
    result = export_html_from_json(str(json_path), str(html_path), title="test")

    # codegraph:test-desc test_viz.test_export_html_from_json_writes_valid_file::post_0
    # Verifies that the function returns the correct file path to the generated HTML
    # file, confirming that the output was written to the expected location.
    assert os.path.realpath(result) == os.path.realpath(str(html_path))
    html = html_path.read_text(encoding="utf-8")
    # codegraph:test-desc test_viz.test_export_html_from_json_writes_valid_file::post_1
    # Checks that the generated HTML starts with a DOCTYPE declaration, ensuring the
    # file is a valid HTML document and can be interpreted by browsers.
    assert "<!DOCTYPE html>" in html
    # codegraph:test-desc test_viz.test_export_html_from_json_writes_valid_file::post_2
    # Confirms that the HTML content includes the word 'cytoscape', indicating that the
    # visualization library is properly referenced in the output.
    assert "cytoscape" in html.lower()
    # codegraph:test-desc test_viz.test_export_html_from_json_writes_valid_file::post_3
    # Asserts that the HTML contains an element with id='cy', which is the container
    # where Cytoscape.js renders the graph, verifying the structural integrity of the
    # visualization.
    assert 'id="cy"' in html
    # codegraph:test-desc test_viz.test_export_html_from_json_writes_valid_file::post_4
    # Validates that the HTML includes the data content 'ns::Engine', confirming that
    # the exported visualization correctly represents the original JSON data.
    assert "ns::Engine" in html  # node appears in the graph


def test_export_html_from_json_uses_filename_as_title(tmp_path):
    """When title is None, the JSON filename stem is used."""
    data = [
        {"type": "NamespaceNode", "name": "ns", "kind": "namespace",
         "source": "test", "qualified_name": "ns", "tags": ["design"],
         "uid": "x", "edges": []},
    ]
    json_path = tmp_path / "my_project.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    html_path = tmp_path / "out.html"
    export_html_from_json(str(json_path), str(html_path))

    html = html_path.read_text(encoding="utf-8")
    # codegraph:test-desc test_viz.test_export_html_from_json_uses_filename_as_title::post_0
    # Verifies that the string 'my_project' appears in the generated HTML, confirming
    # that the export function uses the JSON filename stem as the HTML title when no
    # explicit title is provided.
    assert "my_project" in html


def test_export_html_from_json_function_signature():
    """export_html_from_json has the expected parameters."""
    import inspect
    sig = inspect.signature(export_html_from_json)
    params = list(sig.parameters.keys())
    # codegraph:test-desc test_viz.test_export_html_from_json_function_signature::post_0
    # Validates that 'json_path' is a parameter of export_html_from_json, confirming the
    # function requires an input JSON file path.
    assert "json_path" in params
    # codegraph:test-desc test_viz.test_export_html_from_json_function_signature::post_1
    # Verifies that 'output_path' is a parameter of export_html_from_json, ensuring the
    # function accepts a path for the generated HTML output.
    assert "output_path" in params
    # codegraph:test-desc test_viz.test_export_html_from_json_function_signature::post_2
    # Ensures 'title' is a parameter of export_html_from_json, validating that the
    # function allows customization of the output's title.
    assert "title" in params
    # codegraph:test-desc test_viz.test_export_html_from_json_function_signature::post_3
    # Checks that 'size' is a parameter of export_html_from_json, confirming that the
    # function can accept size constraints for the output.
    assert "size" in params


# ---------------------------------------------------------------------------
# CLI config tests
# ---------------------------------------------------------------------------


def test_cli_config_loads_valid_toml(tmp_path):
    """load_config reads .codegraph.toml and returns HtmlExportConfig."""
    from codegraph.export.viz.cli_config import load_config

    (tmp_path / ".codegraph.toml").write_text(
        '[project]\nname = "mygraph"\noutput_dir = "build"\n',
        encoding="utf-8",
    )
    (tmp_path / "build").mkdir()

    config, project_dir = load_config(tmp_path)
    # codegraph:test-desc test_viz.test_cli_config_loads_valid_toml::post_0
    # Verifies that load_config returns an HtmlExportConfig object, confirming that the
    # function correctly parses a valid TOML file and outputs the expected config type.
    assert config.name == "mygraph"
    # codegraph:test-desc test_viz.test_cli_config_loads_valid_toml::post_1
    # Verifies that the output_dir field in the config matches the expected path
    # (tmp_path / 'build'), ensuring that the TOML's output directory setting is
    # correctly interpreted and stored.
    assert config.output_dir == (tmp_path / "build").resolve()
    # codegraph:test-desc test_viz.test_cli_config_loads_valid_toml::post_2
    # Verifies that the project_dir field in the config equals the temporary directory
    # used for the test, confirming that load_config correctly preserves the directory
    # containing the TOML file.
    assert project_dir == tmp_path


def test_cli_config_missing_file_exits(tmp_path, capsys):
    """Missing .codegraph.toml prints an error and exits."""
    from codegraph.export.viz.cli_config import load_config

    with pytest.raises(SystemExit):
        load_config(tmp_path)


def test_cli_config_missing_name_exits(tmp_path, capsys):
    """Config without 'name' field exits with an error."""
    from codegraph.export.viz.cli_config import load_config

    (tmp_path / ".codegraph.toml").write_text(
        '[project]\noutput_dir = "build"\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        load_config(tmp_path)


def test_cli_config_reads_doxygen_index_toml(tmp_path):
    """load_config falls back to .doxygen-index.toml [codegraph-html]."""
    from codegraph.export.viz.cli_config import load_config

    (tmp_path / ".doxygen-index.toml").write_text(
        '[project]\nname = "codegraph"\nlanguage = "python"\n'
        'input_paths = ["src"]\n\n'
        '[codegraph-html]\noutput_dir = "codegraph"\n',
        encoding="utf-8",
    )
    (tmp_path / "codegraph").mkdir()

    config, project_dir = load_config(tmp_path)
    # codegraph:test-desc test_viz.test_cli_config_reads_doxygen_index_toml::post_0
    # Verifies that the config object is not None, ensuring load_config successfully
    # returned a configuration instance.
    assert config.name == "codegraph"
    # codegraph:test-desc test_viz.test_cli_config_reads_doxygen_index_toml::post_1
    # Confirms that config.output_dir matches the resolved path tmp_path/codegraph,
    # meaning load_config correctly parsed the output directory from the
    # .doxygen-index.toml file.
    assert config.output_dir == (tmp_path / "codegraph").resolve()
    # codegraph:test-desc test_viz.test_cli_config_reads_doxygen_index_toml::post_2
    # Verifies that load_config has set some additional property (the specific operator
    # is unclear) to its expected value, ensuring the fallback configuration is fully
    # applied.
    assert config.source_file == ".doxygen-index.toml"
    # codegraph:test-desc test_viz.test_cli_config_reads_doxygen_index_toml::post_3
    # Checks that project_dir is set to tmp_path, validating that the code correctly
    # assigns the project directory from the test environment rather than from a missing
    # primary config.
    assert project_dir == tmp_path


def test_cli_config_doxygen_index_default_output(tmp_path):
    """.doxygen-index.toml without [codegraph-html] defaults to 'codegraph'."""
    from codegraph.export.viz.cli_config import load_config

    (tmp_path / ".doxygen-index.toml").write_text(
        '[project]\nname = "proj"\n', encoding="utf-8",
    )

    config, _ = load_config(tmp_path)
    # codegraph:test-desc test_viz.test_cli_config_doxygen_index_default_output::post_0
    # Checks that the loaded configuration object is not null or broken, ensuring the
    # load_config function returns a valid config even when optional sections are
    # missing.
    assert config.name == "proj"
    # codegraph:test-desc test_viz.test_cli_config_doxygen_index_default_output::post_1
    # Verifies that the output directory resolves to 'codegraph' under the temporary
    # path, confirming that the default value is applied correctly when no explicit
    # [codegraph-html] section is present in the configuration.
    assert config.output_dir == (tmp_path / "codegraph").resolve()


def test_cli_config_codegraph_toml_takes_precedence(tmp_path):
    """When both configs exist, .codegraph.toml wins."""
    from codegraph.export.viz.cli_config import load_config

    (tmp_path / ".codegraph.toml").write_text(
        '[project]\nname = "primary"\noutput_dir = "out1"\n',
        encoding="utf-8",
    )
    (tmp_path / ".doxygen-index.toml").write_text(
        '[project]\nname = "secondary"\n\n'
        '[codegraph-html]\noutput_dir = "out2"\n',
        encoding="utf-8",
    )
    (tmp_path / "out1").mkdir()

    config, _ = load_config(tmp_path)
    # codegraph:test-desc test_viz.test_cli_config_codegraph_toml_takes_precedence::post_0
    # Verifies that the load_config function returns the value from .codegraph.toml
    # rather than from the other configuration file, confirming that .codegraph.toml
    # takes precedence.
    assert config.name == "primary"
    # codegraph:test-desc test_viz.test_cli_config_codegraph_toml_takes_precedence::post_1
    # Checks that a second configuration key from .codegraph.toml is correctly returned
    # over the corresponding key in the alternative file, reinforcing the precedence
    # rule for all relevant settings.
    assert config.source_file == ".codegraph.toml"
