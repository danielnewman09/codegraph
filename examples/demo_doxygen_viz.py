#!/usr/bin/env python3
"""Demo: visualize doxygen-parsed codebase graphs as Cytoscape.js HTML.

Reads doxygen JSON output (from doxygen-index's ParseResult format) and
converts it to codegraph's LayerGraph format, then generates an interactive
Cytoscape.js HTML graph.

Usage::

    python examples/demo_doxygen_viz.py ../doxygen-dependency-parser/build/ticketing_parse/backend_migrated.json
    python examples/demo_doxygen_viz.py ../doxygen-dependency-parser/build/ticketing_parse/frontend_migrated.json

Output:  ``demo_doxygen.html`` — open in any browser.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jinja2
from markupsafe import Markup

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "src" / "codegraph" / "templates"


# ── Node-type mapping: doxygen kind → codegraph Node type ──────────────
_KIND_TO_TYPE: dict[str, str] = {
    "class": "ClassNode",
    "struct": "ClassNode",
    "interface": "InterfaceNode",
    "enum": "EnumNode",
    "enum_class": "EnumNode",
    "union": "UnionNode",
    "concept": "ConceptNode",
    "method": "MethodNode",
    "function": "FunctionNode",
    "attribute": "AttributeNode",
    "variable": "AttributeNode",
    "enumvalue": "EnumValueNode",
    "define": "DefineNode",
    "module": "ModuleNode",
    "namespace": "NamespaceNode",
    "file": "FileNode",
}


def _node_type_from_kind(kind: str) -> str:
    """Map a doxygen 'kind' to a codegraph Node type name."""
    return _KIND_TO_TYPE.get(kind, "ClassNode")  # fallback


def _kind_from_type(node_type: str) -> str:
    """Inverse of _node_type_from_kind."""
    for kind, ntype in _KIND_TO_TYPE.items():
        if ntype == node_type:
            return kind
    return ""


def convert_doxygen_to_layer_graph(
    dox: dict, tag: str = "as-built"
) -> list[dict]:
    """Convert a doxygen ParseResult JSON dict to LayerGraph-compatible
    node dicts with edges.

    Args:
        dox: The parsed doxygen JSON dict (keys: metadata, files,
            namespaces, classes, methods, attributes, ...).
        tag: Provenance tag for all nodes (``"as-built"``, ``"dependency"``).

    Returns:
        A list of serialized CodeGraphNode dicts with ``type``, properties,
        and ``edges`` arrays.  Suitable for ``LayerGraph.deserialize()``.
    """
    nodes: list[dict] = []

    # ── Build a refid → node index for cross-referencing ───────────────
    refid_to_node: dict[str, dict] = {}

    def _add_node(node_data: dict, node_type: str) -> dict:
        """Add a node and register its refid."""
        kind = node_data.get("kind", _kind_from_type(node_type))
        serialized = {
            "type": node_type,
            "name": node_data.get("name", ""),
            "qualified_name": (
                node_data.get("qualified_name", "")
                or node_data.get("refid", "")
                or node_data.get("name", "")
            ),
            "kind": kind,
            "tags": [tag],
            "edges": [],
        }
        # Guard: Cytoscape requires non-empty string IDs
        if not serialized["qualified_name"]:
            serialized["qualified_name"] = f"{node_type}_{len(nodes)}"
        # Copy relevant fields
        for field in ("refid", "visibility", "brief_description",
                       "type_signature", "argsstring"):
            if field in node_data:
                serialized[field] = node_data[field]

        # FileNode uses 'refid' as its UID; fall back to 'name' if refid is empty
        if node_type == "FileNode":
            refid_val = node_data.get("refid", "") or node_data.get("name", "")
            serialized["refid"] = refid_val
            serialized["path"] = node_data.get("path", "") or node_data.get("name", "")
            serialized["qualified_name"] = refid_val  # for UID resolution

        nodes.append(serialized)
        refid = node_data.get("refid", "")
        if refid:
            refid_to_node[refid] = serialized
        return serialized

    # ── Files ──────────────────────────────────────────────────────────
    for f in dox.get("files", []):
        f["kind"] = "file"
        _add_node(f, "FileNode")

    # ── Namespaces ─────────────────────────────────────────────────────
    for ns in dox.get("namespaces", []):
        _add_node(ns, "NamespaceNode")

    # ── Classes, interfaces, enums, unions, concepts ───────────────────
    for cat, ntype in [
        ("classes", "ClassNode"),
        ("interfaces", "InterfaceNode"),
        ("enums", "EnumNode"),
        ("unions", "UnionNode"),
        ("concepts", "ConceptNode"),
    ]:
        for item in dox.get(cat, []):
            node = _add_node(item, ntype)
            # Base classes → INHERITS_FROM edges (only if target exists)
            for base_refid in item.get("base_classes", []):
                if base_refid in refid_to_node:
                    node["edges"].append({
                        "relation_type": "INHERITS_FROM",
                        "target_type": "ClassNode",
                        "target_local_id": base_refid,
                    })

    # ── Methods ────────────────────────────────────────────────────────
    for m in dox.get("methods", []):
        node = _add_node(m, "MethodNode")
        # COMPOSES: method belongs to its parent compound
        compound_refid = m.get("compound_refid", "")
        if compound_refid and compound_refid in refid_to_node:
            parent = refid_to_node[compound_refid]
            parent["edges"].append({
                "relation_type": "COMPOSES",
                "target_type": node["type"],
                "target_local_id": node.get("qualified_name", "") or node.get("name", ""),
            })

    # ── Attributes ─────────────────────────────────────────────────────
    for a in dox.get("attributes", []):
        node = _add_node(a, "AttributeNode")
        compound_refid = a.get("compound_refid", "")
        if compound_refid and compound_refid in refid_to_node:
            parent = refid_to_node[compound_refid]
            parent["edges"].append({
                "relation_type": "COMPOSES",
                "target_type": node["type"],
                "target_local_id": node.get("qualified_name", "") or node.get("name", ""),
            })

    # ── Enum values ────────────────────────────────────────────────────
    for ev in dox.get("enum_values", []):
        node = _add_node(ev, "EnumValueNode")
        compound_refid = ev.get("compound_refid", "")
        if compound_refid and compound_refid in refid_to_node:
            parent = refid_to_node[compound_refid]
            parent["edges"].append({
                "relation_type": "COMPOSES",
                "target_type": node["type"],
                "target_local_id": node.get("qualified_name", "") or node.get("name", ""),
            })

    # ── Functions ──────────────────────────────────────────────────────
    for fn in dox.get("functions", []):
        node = _add_node(fn, "FunctionNode")
        compound_refid = fn.get("compound_refid", "")
        if compound_refid and compound_refid in refid_to_node:
            parent = refid_to_node[compound_refid]
            parent["edges"].append({
                "relation_type": "COMPOSES",
                "target_type": node["type"],
                "target_local_id": node.get("qualified_name", "") or node.get("name", ""),
            })

    # ── Defines ────────────────────────────────────────────────────────
    for df in dox.get("defines", []):
        _add_node(df, "DefineNode")

    # ── Module nodes (Python modules) ──────────────────────────────────
    for mod in dox.get("modules", []):
        _add_node(mod, "ModuleNode")

    # ── Includes → DEPENDS_ON edges (file → imported module) ────────
    for inc in dox.get("includes", []):
        file_refid = inc.get("file_refid", "")
        included_refid = inc.get("included_refid", "")
        if not file_refid or not included_refid:
            continue
        # The included_refid may be prefixed with the top-level namespace
        # (e.g. "backend_migrated.agents.decompose_hlr" when node refid is
        # "agents.decompose_hlr").  Try exact match first, then strip prefix.
        tgt_node = refid_to_node.get(included_refid)
        if tgt_node is None:
            # Try stripping the first dot-separated component
            dot_idx = included_refid.find(".")
            if dot_idx > 0:
                stripped = included_refid[dot_idx + 1:]
                tgt_node = refid_to_node.get(stripped)
        if tgt_node is None:
            continue
        src_node = refid_to_node.get(file_refid)
        if src_node is None:
            continue
        src_node["edges"].append({
            "relation_type": "DEPENDS_ON",
            "target_type": tgt_node["type"],
            "target_local_id": tgt_node.get("qualified_name", "") or tgt_node.get("name", ""),
        })

    # ── Invokes → INVOKES edges ────────────────────────────────────────
    for inv in dox.get("invokes", []):
        caller_refid = inv.get("caller_refid", "")
        callee_refid = inv.get("callee_refid", "")
        if caller_refid in refid_to_node and callee_refid in refid_to_node:
            src_node = refid_to_node[caller_refid]
            tgt_node = refid_to_node[callee_refid]
            src_node["edges"].append({
                "relation_type": "INVOKES",
                "target_type": tgt_node["type"],
                "target_local_id": tgt_node.get("qualified_name", "") or tgt_node.get("name", ""),
            })

    # ── Invoked-by (reverse of invokes) ────────────────────────────────
    for inv in dox.get("invoked_by", []):
        caller_refid = inv.get("caller_refid", "")
        callee_refid = inv.get("callee_refid", "")
        if caller_refid in refid_to_node and callee_refid in refid_to_node:
            src_node = refid_to_node[caller_refid]
            tgt_node = refid_to_node[callee_refid]
            src_node["edges"].append({
                "relation_type": "INVOKES",
                "target_type": tgt_node["type"],
                "target_local_id": tgt_node.get("qualified_name", "") or tgt_node.get("name", ""),
            })

    return nodes


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python examples/demo_doxygen_viz.py <doxygen.json>")
        print()
        print("  doxygen.json  Path to a doxygen ParseResult JSON file")
        print("                (e.g. ../doxygen-dependency-parser/build/")
        print("                ticketing_parse/backend_migrated.json)")
        sys.exit(1)

    # ── Late imports (after path validation) ──────────────────────────
    from codegraph.graph import LayerGraph
    from codegraph.viz.transform import layer_graph_to_cytoscape
    from codegraph.viz.styles import cy_stylesheet

    input_path = Path(sys.argv[1]).resolve()
    output_path = input_path.with_name(
        f"demo_{input_path.stem}.html"
    )

    # ── Load doxygen JSON ──────────────────────────────────────────────
    with open(input_path) as f:
        dox = json.load(f)

    total_entries = sum(
        len(dox.get(k, []))
        for k in ("files", "namespaces", "classes", "interfaces",
                  "enums", "unions", "concepts", "methods", "attributes",
                  "enum_values", "defines", "functions", "modules")
    )
    print(f"Loaded {total_entries} doxygen entries from {input_path.name}")

    # ── Convert to LayerGraph format ───────────────────────────────────
    nodes_data = convert_doxygen_to_layer_graph(dox, tag="as-built")
    print(f"  → {len(nodes_data)} codegraph nodes")

    graph = LayerGraph.deserialize(nodes_data)

    # ── Transform to Cytoscape elements ────────────────────────────────
    cy_data = layer_graph_to_cytoscape(graph)
    print(f"  → {len(cy_data['nodes'])} Cytoscape nodes, "
          f"{len(cy_data['edges'])} edges")

    # ── Build stylesheet ───────────────────────────────────────────────
    styles = cy_stylesheet(size="large")

    # ── Render HTML ────────────────────────────────────────────────────
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("graph.html.j2")

    html = template.render(
        title=f"Codegraph — {input_path.stem}",
        tag="as-built",
        elements_json=Markup(
            json.dumps(cy_data["nodes"] + cy_data["edges"])
        ),
        styles_json=Markup(json.dumps(styles)),
    )

    output_path.write_text(html, encoding="utf-8")
    print(f"  → wrote {output_path.stat().st_size:,} bytes to {output_path}")
    print(f"\nOpen {output_path} in a browser.")


if __name__ == "__main__":
    main()
