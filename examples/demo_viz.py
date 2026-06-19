#!/usr/bin/env python3
"""Demo: generate a Cytoscape.js HTML graph from the Calculator design fixture.

Uses ``LayerGraph.deserialize()`` to load the 27-node Calculator graph from
``tests/data/design_graph.json`` purely in memory — no Neo4j required.
Writes a self-contained ``demo_calculator.html`` that opens in any browser.

Usage::

    python examples/demo_viz.py
    # Opens demo_calculator.html — drag, zoom, explore.
"""

from __future__ import annotations

import json
from pathlib import Path

import jinja2
from markupsafe import Markup

from codegraph.graph import LayerGraph
from codegraph.viz.transform import layer_graph_to_cytoscape
from codegraph.viz.styles import cy_stylesheet

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / "tests" / "data" / "design_graph.json"
TEMPLATE_DIR = PROJECT_ROOT / "src" / "codegraph" / "templates"
OUTPUT = PROJECT_ROOT / "demo_calculator.html"

# ── Load fixture (pure Python, no Neo4j) ───────────────────────────────
with open(FIXTURE) as f:
    nodes_data = json.load(f)

print(f"Loaded {len(nodes_data)} nodes from {FIXTURE.name}")

graph = LayerGraph.deserialize(nodes_data)

# ── Transform to Cytoscape elements ─────────────────────────────────────
cy_data = layer_graph_to_cytoscape(graph)
print(f"  → {len(cy_data['nodes'])} Cytoscape nodes, "
      f"{len(cy_data['edges'])} edges")

# ── Build stylesheet ────────────────────────────────────────────────────
styles = cy_stylesheet(size="large")

# ── Render HTML ─────────────────────────────────────────────────────────
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)
template = env.get_template("graph.html.j2")

html = template.render(
    title="Codegraph Demo — Calculator Design",
    tag="design",
    elements_json=Markup(json.dumps(cy_data["nodes"] + cy_data["edges"])),
    styles_json=Markup(json.dumps(styles)),
)

# ── Write ───────────────────────────────────────────────────────────────
OUTPUT.write_text(html, encoding="utf-8")
print(f"  → wrote {OUTPUT.stat().st_size:,} bytes to {OUTPUT}")
print(f"\nOpen {OUTPUT} in a browser to explore the graph.")
