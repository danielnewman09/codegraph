#!/usr/bin/env python3
"""Demo: visualize codegraph LayerGraph JSON as Cytoscape.js HTML.

Reads a LayerGraph-compatible JSON file (list of serialized node dicts
with ``type`` and optional ``composes``/``edges``) and generates an
interactive Cytoscape.js HTML graph — no Neo4j required.

Usage::

    python examples/demo_layergraph_viz.py path/to/layergraph.json
    python examples/demo_layergraph_viz.py ../doxygen-dependency-parser/build/codegraph_parse/codegraph_layergraph.json

Output:  ``<input_name>.html`` — open in any browser.
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


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python examples/demo_layergraph_viz.py <layergraph.json>")
        print()
        print("  layergraph.json  LayerGraph-compatible JSON (list of serialized")
        print("                   node dicts with type + composes/edges)")
        sys.exit(1)

    # ── Late imports ──────────────────────────────────────────────────
    from codegraph.graph import LayerGraph
    from codegraph.viz.transform import layer_graph_to_cytoscape
    from codegraph.viz.styles import cy_stylesheet

    input_path = Path(sys.argv[1]).resolve()
    output_path = input_path.with_name(
        f"demo_{input_path.stem}.html"
    )

    # ── Load and filter LayerGraph JSON ───────────────────────────────
    with open(input_path) as f:
        nodes_data = json.load(f)

    # Keep only top-level entries with composes (FileNodes carrying
    # the composition tree).  Orphan ParameterNodes and
    # ImplementationNodes are implementation details that don't
    # contribute to the structural graph.
    #
    # Also prefix FileNode refids to avoid key collisions with
    # NamespaceNode qualified_names that share the same value.
    # ── Filter and normalise ─────────────────────────────────────────
    for item in nodes_data:
        # Remap parser tags to codegraph's valid tag vocabulary
        item["tags"] = [
            "as-built" if t == "codebase" else t
            for t in item.get("tags", [])
        ]
        if not item.get("tags"):
            item["tags"] = ["as-built"]

        if item["type"] == "FileNode":
            old_refid = item.get("refid", item.get("name", ""))
            item["refid"] = f"file:{old_refid}"
            item["kind"] = "file"

    nodes_data = [
        n for n in nodes_data
        if n.get("composes") or n["type"] not in ("ParameterNode", "ImplementationNode")
    ]

    print(f"Loaded {len(nodes_data)} structural nodes from {input_path.name}")

    # ── Deserialize (pure Python, no Neo4j) ────────────────────────────
    graph = LayerGraph.deserialize(nodes_data)

    # Count all entries (depth-first)
    total = sum(1 for _ in graph._all_entries())
    print(f"  → {total} total entries in composition tree")

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

    tag = next(iter(graph.tags)) if graph.tags else "design"

    html = template.render(
        title=f"Codegraph — {input_path.stem}",
        tag=tag,
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
