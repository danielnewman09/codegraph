"""Format conversion tools — export/import between markdown, plantuml, json.

Each tool has a ``SCHEMA`` dict (JSON Schema for the LLM) and a
``handle(ctx, tool_input)`` function.
"""

import json


# ── graph_format_export ────────────────────────────────────────────────────

EXPORT_SCHEMA = {
    "name": "graph_format_export",
    "description": (
        "Export the currently fetched graph (from a previous graph_fetch call) "
        "to a different format. Use this to convert between markdown, plantuml, "
        "and json without re-querying Neo4j."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "description": "Target format.",
            },
        },
        "required": ["format"],
    },
}


def handle_export(ctx, tool_input: dict) -> str:
    from codegraph.tools.dispatcher import _serialize_graph

    fmt = tool_input["format"]

    if ctx.current_graph is None:
        return json.dumps({
            "error": "No graph loaded. Call graph_fetch first."
        })

    try:
        return _serialize_graph(ctx.current_graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_format_import ────────────────────────────────────────────────────

IMPORT_SCHEMA = {
    "name": "graph_format_import",
    "description": (
        "Import a markdown or plantuml diagram into a graph. Use this to "
        "read a manually written or LLM-generated design diagram into the "
        "codegraph data structures for comparison or further processing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The markdown or plantuml text to import.",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml"],
                "description": "Source format of the text.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags to apply to imported nodes (default: ['design']).",
            },
        },
        "required": ["text", "format"],
    },
}


def handle_import(ctx, tool_input: dict) -> str:
    from codegraph.export.format import import_graph as format_import_graph

    text = tool_input["text"]
    fmt = tool_input["format"]
    tags_raw = tool_input.get("tags")

    try:
        tags: frozenset[str] | None = None
        if tags_raw:
            tags = frozenset(tags_raw)

        graph = format_import_graph(text, format=fmt, tags=tags)
        ctx.current_graph = graph

        node_count = sum(1 for _ in graph._all_entries())
        return json.dumps({
            "imported": True,
            "node_count": node_count,
            "tags": list(graph.tags),
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_save ─────────────────────────────────────────────────────────────

SAVE_SCHEMA = {
    "name": "graph_save",
    "description": (
        "Persist the currently loaded graph (from a previous graph_fetch "
        "or graph_format_import call) to Neo4j. Use this after modifying "
        "a design to write the changes back."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle_save(ctx, tool_input: dict) -> str:
    if ctx.current_graph is None:
        return json.dumps({
            "error": "No graph loaded. Call graph_fetch or graph_format_import first."
        })

    try:
        ctx.repo.save_layer_graph(ctx.current_graph)
        node_count = sum(1 for _ in ctx.current_graph._all_entries())
        return json.dumps({
            "saved": True,
            "node_count": node_count,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Registration ───────────────────────────────────────────────────────────


def register_all(dispatcher) -> None:
    """Register all format tools on a dispatcher."""
    dispatcher.register(
        "graph_format_export", EXPORT_SCHEMA,
        lambda inp: handle_export(dispatcher, inp),
    )
    dispatcher.register(
        "graph_format_import", IMPORT_SCHEMA,
        lambda inp: handle_import(dispatcher, inp),
    )
    dispatcher.register(
        "graph_save", SAVE_SCHEMA,
        lambda inp: handle_save(dispatcher, inp),
    )
