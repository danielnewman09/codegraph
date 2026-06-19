"""Cytoscape.js HTML export for codegraph LayerGraphs.

Provides ``export_html()`` for writing self-contained interactive graph
visualisations, and a ``main()`` entry point for CLI usage.

Usage::

    from codegraph.viz import export_html

    export_html("design", "design.html")
    export_html("as-built", "/tmp/asbuilt.html", size="small")
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jinja2
from markupsafe import Markup

from codegraph.graph import LayerGraph
from codegraph.viz.transform import layer_graph_to_cytoscape
from codegraph.viz.styles import cy_stylesheet


def export_html(
    tag: str,
    output_path: str = "graph.html",
    *,
    size: str = "large",
) -> str:
    """Fetch all nodes for *tag* from Neo4j, render as self-contained HTML.

    Args:
        tag: A provenance tag (``"design"``, ``"as-built"``,
            ``"dependency"``).
        output_path: Path for the output HTML file.  Defaults to
            ``"graph.html"`` in the current directory.
        size: ``"large"`` (full-page graph) or ``"small"`` (compact).

    Returns:
        The absolute path to the written HTML file.

    Raises:
        RuntimeError: If the template file cannot be found.
    """
    # 1. Fetch graph from Neo4j
    graph = LayerGraph.from_neo4j(tag)

    # 2. Transform to Cytoscape elements
    cy_data = layer_graph_to_cytoscape(graph)

    # 3. Build stylesheet
    styles = cy_stylesheet(size=size)

    # 4. Load and render template
    template_dir = Path(__file__).resolve().parent.parent / "templates"
    if not template_dir.is_dir():
        raise RuntimeError(
            f"Template directory not found: {template_dir}"
        )
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("graph.html.j2")

    html = template.render(
        title=f"Codegraph — {tag}",
        tag=tag,
        elements_json=Markup(json.dumps(cy_data["nodes"] + cy_data["edges"])),
        styles_json=Markup(json.dumps(styles)),
    )

    # 5. Write output
    out_path = Path(output_path).resolve()
    out_path.write_text(html, encoding="utf-8")

    return str(out_path)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``codegraph-viz``.

    Usage::

        codegraph-viz <tag> [--output <path>] [--size large|small]

    Reads Neo4j credentials from ``.env`` in the current directory
    (via codegraph's existing ``python-dotenv`` setup in ``config.py``).
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: codegraph-viz <tag> [--output <path>] [--size large|small]")
        print()
        print("  tag       Provenance tag: design, as-built, dependency")
        print("  --output  Output path (default: graph.html)")
        print("  --size    large or small (default: large)")
        sys.exit(0)

    tag = argv[0]
    output = "graph.html"
    size = "large"

    # Simple arg parsing
    i = 1
    while i < len(argv):
        if argv[i] == "--output" and i + 1 < len(argv):
            output = argv[i + 1]
            i += 2
        elif argv[i] == "--size" and i + 1 < len(argv):
            size = argv[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {argv[i]}", file=sys.stderr)
            sys.exit(1)

    result = export_html(tag, output, size=size)
    print(f"Graph written to {result}")


if __name__ == "__main__":
    main()
