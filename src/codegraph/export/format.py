"""Unified import/export for codegraph in multiple formats.

Provides a single entry point for human-readable (PlantUML, Markdown)
and machine-readable (JSON) serialization.

Formats
-------
- ``"markdown"`` / ``"md"`` — human-readable Markdown document
- ``"plantuml"`` / ``"puml"`` — PlantUML class diagram
- ``"json"`` / ``"json_nested"`` — machine-readable JSON (via
  :meth:`LayerGraph.serialize` / :meth:`LayerGraph.deserialize`)

Example::

    from codegraph.export.format import export_graph, import_graph

    puml = export_graph(graph, format="plantuml")
    md = export_graph(graph, format="markdown")
    json_str = export_graph(graph, format="json")

    graph2 = import_graph(puml, format="plantuml")
    graph3 = import_graph(md, format="markdown")
"""

from __future__ import annotations

from codegraph.graph import LayerGraph


def export_graph(graph: LayerGraph, format: str = "markdown",
                 fields: str = "llm", **kwargs: object) -> str:
    """Export a :class:`LayerGraph` to a string in the given format.

    Args:
        graph: The :class:`LayerGraph` to export.
        format: Target format — ``"markdown"``, ``"md"``, ``"plantuml"``,
            ``"puml"``, ``"json"``, or ``"json_nested"``.
        fields: Which property fields to include for node details.
            ``"llm"`` (default) — only ``_llm_fields``.
            ``"all"`` — every defined property.
        **kwargs: Format-specific options.
            ``public_only`` (bool) — Markdown only: hide non-public
            members (default ``True``).

    Returns:
        A string in the requested format.

    Raises:
        ValueError: If *format* is not recognized.
    """
    fmt = format.lower()

    if fmt in ("markdown", "md"):
        from codegraph.export.markdown import export_markdown
        public_only = kwargs.get("public_only", True)
        return export_markdown(graph, fields=fields,
                              public_only=bool(public_only))

    if fmt in ("plantuml", "puml"):
        from codegraph.export.plantuml import export_plantuml
        return export_plantuml(graph, fields=fields)

    if fmt in ("json", "json_nested"):
        import json
        return json.dumps(graph.serialize(fields=fields), indent=2,
                          sort_keys=True)

    raise ValueError(
        f"Unknown export format {format!r}. "
        f"Supported: markdown, plantuml, json"
    )


def import_graph(text: str, format: str = "markdown",
                 tags: frozenset[str] | None = None,
                 strict: bool = False) -> LayerGraph:
    """Import a string in the given format into a :class:`LayerGraph`.

    Args:
        text: The string to parse.
        format: Source format — ``"markdown"``, ``"md"``, ``"plantuml"``,
            ``"puml"``, ``"json"``, or ``"json_nested"``.
        tags: Tags to apply to every imported node (Markdown, PlantUML).
            Defaults to ``frozenset({"design"})``.  Ignored for JSON
            (tags are deserialized from the data).
        strict: If ``True``, raise :class:`PlantUMLParseError` on
            structural errors (Markdown, PlantUML).  Ignored for JSON.

    Returns:
        A :class:`LayerGraph` containing the parsed nodes and
        relationships.

    Raises:
        ValueError: If *format* is not recognized.
        PlantUMLParseError: In strict mode, when structural errors are
            found in Markdown or PlantUML input.
    """
    fmt = format.lower()

    if fmt in ("markdown", "md"):
        from codegraph.export.markdown import import_markdown
        return import_markdown(text, tags=tags, strict=strict)

    if fmt in ("plantuml", "puml"):
        from codegraph.export.plantuml import import_plantuml
        return import_plantuml(text, tags=tags, strict=strict)

    if fmt in ("json", "json_nested"):
        import json
        data = json.loads(text) if isinstance(text, str) else text
        return LayerGraph.deserialize(data)

    raise ValueError(
        f"Unknown import format {format!r}. "
        f"Supported: markdown, plantuml, json"
    )
