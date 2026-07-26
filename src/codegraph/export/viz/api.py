"""Cytoscape.js HTML export for codegraph LayerGraphs.

Provides ``export_html_from_json()`` and ``export_html()`` for writing
self-contained interactive graph visualisations, plus a ``main()``
CLI entry point that reads ``.codegraph.toml`` for configuration.

Usage (from JSON file)::

    from codegraph.export.viz import export_html_from_json

    export_html_from_json("path/to/graph.json", "graph.html")

Usage (from Neo4j)::

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
from codegraph.export.viz.transform import layer_graph_to_cytoscape
from codegraph.export.viz.styles import cy_stylesheet


def export_html_from_json(
    json_path: str | Path,
    output_path: str | Path,
    *,
    title: str | None = None,
    size: str = "large",
    collapse_members: bool = True,
) -> str:
    """Load a LayerGraph from a JSON file, render as self-contained HTML.

    Args:
        json_path: Path to a code-graph JSON file (serialised
            ``LayerGraph`` output — a list of node dicts).
        output_path: Path for the output HTML file.
        title: Page title (defaults to the JSON filename stem).
        size: ``"large"`` (full-page graph) or ``"small"`` (compact).
        collapse_members: When True (default), leaf members are collapsed
            into parent compound UML labels.  When False, every member is
            a separate node — useful for class-scoped views.

    Returns:
        The absolute path to the written HTML file.
    """
    json_path = Path(json_path)
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)

    graph = LayerGraph.deserialize(data)

    if title is None:
        title = json_path.stem

    return _render_html(graph, title, output_path, size=size,
                        collapse_members=collapse_members)


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
    graph = LayerGraph.from_neo4j(tag)
    return _render_html(graph, tag, output_path, size=size)


def _render_html(
    graph: LayerGraph,
    title: str,
    output_path: str | Path,
    *,
    size: str = "large",
    collapse_members: bool = True,
) -> str:
    """Shared renderer — transform graph to Cytoscape, write HTML."""
    # 1. Transform to Cytoscape elements
    cy_data = layer_graph_to_cytoscape(graph, collapse_members=collapse_members)

    # 2. Build stylesheet
    styles = cy_stylesheet(size=size)

    # 3. Load and render template
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
        title=f"Codegraph — {title}",
        tag=title,
        elements_json=Markup(json.dumps(cy_data["nodes"] + cy_data["edges"])),
        styles_json=Markup(json.dumps(styles)),
    )

    # 4. Write output
    out_path = Path(output_path).resolve()
    out_path.write_text(html, encoding="utf-8")

    return str(out_path)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``codegraph-html``.

    Reads ``.codegraph.toml`` (or, failing that, the ``[codegraph-html]``
    section of ``.doxygen-index.toml``) from the current directory (or
    ``--project-dir``) to discover the project name and output
    directory.  The code-graph JSON is expected at
    ``{output_dir}/{name}.json``.  HTML is written to
    ``{output_dir}/{name}.html`` by default, or ``--output`` to
    override.

    Usage::

        codegraph-html                              # auto-detect config
        codegraph-html --project-dir ../my-project  # use config elsewhere
        codegraph-html --output custom.html         # override output path
        codegraph-html --size small                 # compact layout
    """
    import argparse

    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="codegraph-html",
        description="Export a code-graph JSON file as an interactive HTML visualisation.",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="Project root containing .codegraph.toml or .doxygen-index.toml "
             "(default: current directory)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output HTML path (default: {output_dir}/{name}.html)",
    )
    parser.add_argument(
        "--size", default="large", choices=["large", "small"],
        help="Layout size (default: large)",
    )
    args = parser.parse_args(argv)

    from codegraph.export.viz.cli_config import load_config

    config, project_dir = load_config(args.project_dir)

    json_path = config.output_dir / f"{config.name}.json"
    if not json_path.exists():
        print(
            f"Error: code-graph JSON not found: {json_path}\n"
            f"  (configured via {config.source_file} in {project_dir})",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        output_path = config.output_dir / f"{config.name}.html"

    result = export_html_from_json(
        json_path, output_path, title=config.name, size=args.size,
    )
    print(f"Graph written to {result}")


if __name__ == "__main__":
    main()