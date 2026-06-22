"""Tests for codegraph.viz — Cytoscape HTML export.

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
from codegraph.viz.transform import layer_graph_to_cytoscape
from codegraph.viz.styles import cy_stylesheet, KIND_COLORS, EDGE_COLORS
from codegraph.viz.labels import build_uml_html
from codegraph.viz import export_html


# ---------------------------------------------------------------------------
# Unit tests (no Neo4j needed)
# ---------------------------------------------------------------------------


def test_cy_stylesheet_produces_valid_structure():
    """Stylesheet output is a list of dicts with selector and style keys."""
    styles = cy_stylesheet(size="large")
    assert isinstance(styles, list)
    assert len(styles) > 0
    for entry in styles:
        assert "selector" in entry
        assert "style" in entry


def test_cy_stylesheet_small_size():
    """Small size produces different font dimensions."""
    styles = cy_stylesheet(size="small")
    assert len(styles) > 0


def test_cy_stylesheet_has_all_layer_selectors():
    """Verify design, as-built, and dependency selectors exist."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    assert 'node[layer="design"][!has_members]' in selectors
    assert 'node[layer="as-built"][!has_members]' in selectors
    assert 'node[layer="dependency"][!has_members]' in selectors


def test_cy_stylesheet_has_uml_box_selectors():
    """Verify UML box selectors exist for all layers."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    assert 'node[has_members="true"][layer="design"]' in selectors
    assert 'node[has_members="true"][layer="as-built"]' in selectors
    assert 'node[has_members="true"][layer="dependency"]' in selectors


def test_color_constants():
    """Color maps are non-empty dicts."""
    assert len(KIND_COLORS) > 0
    assert len(EDGE_COLORS) > 0
    assert "class" in KIND_COLORS
    assert "INHERITS_FROM" in EDGE_COLORS
    assert "default" in EDGE_COLORS


def test_cy_stylesheet_has_edge_type_overrides():
    """Verify that key edge types have style overrides."""
    styles = cy_stylesheet()
    selectors = {s["selector"] for s in styles}
    for edge_type in ("INHERITS_FROM", "DEPENDS_ON", "REFERENCES", "AGGREGATES"):
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
                "qualified_name": "calc::Calculator::add",
                "layer": "design",
            }
        ]
    }
    result = build_uml_html("Calculator", by_kind, owner_kind="class")
    assert "Calculator" in result
    assert "add" in result
    assert "<div" in result


def test_build_uml_html_with_stereotype():
    """Stereotype appears for interfaces."""
    by_kind: dict[str, list] = {}
    result = build_uml_html("IPlugin", by_kind, owner_kind="interface")
    assert "interface" in result.lower()


def test_build_uml_html_enum():
    """Enum nodes show enum values."""
    by_kind = {
        "enum_value": [
            {"name": "RED", "visibility": "public", "type_signature": "",
             "argsstring": "", "qualified_name": "Color::RED", "layer": "design"},
            {"name": "GREEN", "visibility": "public", "type_signature": "",
             "argsstring": "", "qualified_name": "Color::GREEN", "layer": "design"},
        ]
    }
    result = build_uml_html("Color", by_kind, owner_kind="enum")
    assert "RED" in result
    assert "GREEN" in result


def test_build_uml_html_respects_visibility_order():
    """Public members appear first in output."""
    by_kind = {
        "attribute": [
            {"name": "private_attr", "visibility": "private", "type_signature": "int",
             "argsstring": "", "qualified_name": "Foo::private_attr", "layer": "design"},
            {"name": "public_attr", "visibility": "public", "type_signature": "str",
             "argsstring": "", "qualified_name": "Foo::public_attr", "layer": "design"},
        ]
    }
    result = build_uml_html("Foo", by_kind, owner_kind="class")
    pub_idx = result.index("public_attr")
    priv_idx = result.index("private_attr")
    assert pub_idx < priv_idx, "public members should appear before private"


def test_layer_graph_to_cytoscape_empty_graph():
    """Empty LayerGraph produces empty nodes/edges."""
    graph = LayerGraph(tags=frozenset({"design"}), entries={})
    result = layer_graph_to_cytoscape(graph)
    assert result["nodes"] == []
    assert result["edges"] == []


def test_layer_graph_to_cytoscape_single_class():
    """A simple ClassNode without members renders as a Cy node."""
    cls = ClassNode.deserialize({
        "type": "ClassNode",
        "name": "Calculator",
        "qualified_name": "calc::Calculator",
        "kind": "class",
        "tags": ["design"],
        "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"design"}), entries={"calc::Calculator": entry})

    result = layer_graph_to_cytoscape(graph)
    assert len(result["nodes"]) == 1
    node_data = result["nodes"][0]["data"]
    assert node_data["qualified_name"] == "calc::Calculator"
    assert node_data["label"] == "Calculator"
    assert node_data["kind"] == "class"
    assert node_data["layer"] == "design"
    assert "has_members" not in node_data


def test_layer_graph_to_cytoscape_class_with_members():
    """A class with composed methods produces UML label."""
    method = MethodNode.deserialize({
        "type": "MethodNode",
        "name": "add",
        "qualified_name": "calc::Calculator::add",
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
        "qualified_name": "calc::Calculator",
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
    assert len(result["nodes"]) == 1  # only the class, not the method
    node_data = result["nodes"][0]["data"]
    assert node_data["has_members"] == "true"
    assert "html_label" in node_data
    assert "add" in node_data["html_label"]


def test_layer_graph_to_cytoscape_with_edges():
    """References between nodes produce Cytoscape edges."""
    cls_a = ClassNode.deserialize({
        "type": "ClassNode", "name": "A", "qualified_name": "ns::A",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_b = ClassNode.deserialize({
        "type": "ClassNode", "name": "B", "qualified_name": "ns::B",
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
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
    edge = result["edges"][0]["data"]
    assert edge["source"] == "ns::A"
    assert edge["target"] == "ns::B"
    assert edge["label"] == "DEPENDS_ON"


def test_layer_graph_to_cytoscape_with_namespace():
    """Namespace nodes get is_namespace flag and children get parent."""
    ns = NamespaceNode.deserialize({
        "type": "NamespaceNode", "name": "calc",
        "qualified_name": "calc", "kind": "namespace",
        "tags": ["design"], "edges": [],
    })
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Calculator",
        "qualified_name": "calc::Calculator", "kind": "class",
        "tags": ["design"], "visibility": "public", "edges": [],
    })
    ns_entry = CompositeEntry(node=ns)
    ns_entry.children["ClassNode"] = {
        "calc::Calculator": CompositeEntry(node=cls)
    }
    graph = LayerGraph(tags=frozenset({"design"}), entries={"calc": ns_entry})

    result = layer_graph_to_cytoscape(graph)
    assert len(result["nodes"]) == 2
    ns_data = next(
        n["data"] for n in result["nodes"] if n["data"]["qualified_name"] == "calc"
    )
    assert ns_data["is_namespace"] == "true"
    cls_data = next(
        n["data"] for n in result["nodes"] if n["data"]["qualified_name"] == "calc::Calculator"
    )
    assert cls_data.get("parent") == "calc"


def test_layer_graph_to_cytoscape_method_reference_becomes_edge():
    """A reference from a collapsed method becomes an edge from the parent."""
    method = MethodNode.deserialize({
        "type": "MethodNode", "name": "calculate",
        "qualified_name": "calc::Engine::calculate", "kind": "method",
        "tags": ["design"], "visibility": "public", "edges": [],
    })
    cls_engine = ClassNode.deserialize({
        "type": "ClassNode", "name": "Engine",
        "qualified_name": "calc::Engine",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_result = ClassNode.deserialize({
        "type": "ClassNode", "name": "Result",
        "qualified_name": "calc::Result",
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
    assert len(result["nodes"]) == 2  # Engine + Result (method collapsed)
    assert len(result["edges"]) == 1
    edge = result["edges"][0]["data"]
    assert edge["source"] == "calc::Engine"  # edge from parent, not method
    assert edge["target"] == "calc::Result"
    assert edge["label"] == "RETURNS"


def test_layer_graph_to_cytoscape_excludes_implementation_node():
    """ImplementationNode references are excluded from edges."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Foo", "qualified_name": "ns::Foo",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    entry.references = [("IMPLEMENTS", "impl_123", "ImplementationNode")]

    graph = LayerGraph(tags=frozenset({"design"}), entries={"ns::Foo": entry})
    result = layer_graph_to_cytoscape(graph)
    assert len(result["edges"]) == 0


def test_layer_graph_to_cytoscape_as_built_layer():
    """as-built tag produces layer='as-built' in node data."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "Foo", "qualified_name": "ns::Foo",
        "kind": "class", "tags": ["as-built"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"as-built"}), entries={"ns::Foo": entry})

    result = layer_graph_to_cytoscape(graph)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["data"]["layer"] == "as-built"


def test_layer_graph_to_cytoscape_dependency_layer():
    """dependency tag produces layer='dependency' in node data."""
    cls = ClassNode.deserialize({
        "type": "ClassNode", "name": "ExtLib", "qualified_name": "ext::Lib",
        "kind": "class", "tags": ["dependency"], "visibility": "public",
        "edges": [],
    })
    entry = CompositeEntry(node=cls)
    graph = LayerGraph(tags=frozenset({"dependency"}), entries={"ext::Lib": entry})

    result = layer_graph_to_cytoscape(graph)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["data"]["layer"] == "dependency"


def test_edge_ids_are_unique():
    """Multiple edges from same source to different targets have unique IDs."""
    cls_a = ClassNode.deserialize({
        "type": "ClassNode", "name": "A", "qualified_name": "ns::A",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_b = ClassNode.deserialize({
        "type": "ClassNode", "name": "B", "qualified_name": "ns::B",
        "kind": "class", "tags": ["design"], "visibility": "public",
        "edges": [],
    })
    cls_c = ClassNode.deserialize({
        "type": "ClassNode", "name": "C", "qualified_name": "ns::C",
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
        assert os.path.realpath(result_path) == os.path.realpath(output_path)
        html = Path(output_path).read_text(encoding="utf-8")

        # Structural checks
        assert "<!DOCTYPE html>" in html
        assert "cytoscape" in html.lower()
        assert "fcose" in html
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
        assert os.path.realpath(result_path) == os.path.realpath(output_path)
        html = Path(output_path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert 'id="cy"' in html
    finally:
        Path(output_path).unlink(missing_ok=True)


def test_jinja2_template_exists():
    """The graph.html.j2 template is packaged with the module."""
    import codegraph.viz
    template_dir = (
        Path(codegraph.viz.__file__).resolve().parent.parent / "templates"
    )
    assert template_dir.is_dir(), f"Template directory not found: {template_dir}"
    assert (template_dir / "graph.html.j2").is_file()


def test_export_html_function_signature():
    """export_html has the expected parameters."""
    import inspect
    sig = inspect.signature(export_html)
    params = list(sig.parameters.keys())
    assert "tag" in params
    assert "output_path" in params
    assert "size" in params


def test_cy_stylesheet_darken():
    """The _darken helper produces correct colors."""
    from codegraph.viz.styles import _darken

    assert _darken("#ffffff", 0.5) == "#7f7f7f"
    assert _darken("#000000", 1.0) == "#000000"
    assert _darken("#ff0000", 0.5) == "#7f0000"
    # factor=0 should produce black
    assert _darken("#abcdef", 0.0) == "#000000"
