#!/usr/bin/env python3
"""Ingest a codegraph design Markdown file into Neo4j.

Usage:
    python scripts/ingest_design.py codegraph/requirements/my_design.md

The design file must use the codegraph Markdown format:
    # codegraph: design
    ## Component: `My Component`
    ## Namespace: `pkg.module`
    ### Class: `pkg.module.MyClass`
    ## Relationships
    - `pkg.module.MyClass` → `pkg.module.OtherClass` **depends_on**
"""

import sys
from pathlib import Path

# ── Neo4j connection (set before codegraph imports) ─────────────────────────
from codegraph.backends import get_backend

NEO4J_URL = "bolt://neo4j:codegraph@localhost:7687"


def ingest_design(markdown_path: str, tag: str = "design") -> int:
    """Import a design markdown file and persist to Neo4j.

    Returns the number of nodes ingested.
    """
    db.set_connection(NEO4J_URL)

    from codegraph.export.markdown import MarkdownImporter

    text = Path(markdown_path).read_text(encoding="utf-8")

    importer = MarkdownImporter(tags=frozenset({tag}), strict=False)
    graph = importer.import_markdown(text)

    # Report diagnostics
    if importer.diagnostics:
        print(f"WARNING: {len(importer.diagnostics)} import diagnostic(s):")
        for d in importer.diagnostics:
            print(f"  Line {d.line} [{d.severity}]: {d.message}")
        if any(d.severity == "error" for d in importer.diagnostics):
            print("Aborting due to import errors.")
            return 0

    # Count nodes before ingest
    def count_all(entries):
        total = len(entries)
        for _qname, entry in entries.items():
            for _child_type, children in entry.children.items():
                total += count_all(children)
        return total

    node_count = count_all(graph.entries)

    # Ingest
    graph.to_neo4j()
    print(f"Ingested {node_count} nodes tagged '{tag}' from {markdown_path}")
    return node_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/design.md>")
        sys.exit(1)

    markdown_path = sys.argv[1]
    if not Path(markdown_path).exists():
        print(f"Error: file not found: {markdown_path}")
        sys.exit(1)

    ingest_design(markdown_path)
