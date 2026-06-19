"""Graph query tools — fetch codegraph views from Neo4j.

Each tool has a ``SCHEMA`` dict (JSON Schema for the LLM) and a
``handle(ctx, tool_input)`` function.
"""

import json


# ── graph_fetch ────────────────────────────────────────────────────────────

FETCH_SCHEMA = {
    "name": "graph_fetch",
    "description": (
        "Fetch all nodes with a given tag plus their 1-hop neighbors. "
        "Returns the full design view serialized in the requested format. "
        "Use this as the starting point to understand the current state "
        "of the codebase for a given view (e.g., 'design', 'as-built')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tag": {
                "type": "string",
                "description": "Tag to query: 'design', 'as-built', 'dependency'.",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": (
                    "Output format. 'markdown' (default) gives a human-readable "
                    "description with public API and relationships. 'plantuml' "
                    "gives a class diagram. 'json' gives the raw serialized data."
                ),
            },
            "public_only": {
                "type": "boolean",
                "default": True,
                "description": (
                    "For markdown: show only public API (methods/attributes with "
                    "visibility 'public' or unset). Set false for all members."
                ),
            },
        },
        "required": ["tag"],
    },
}


def handle_fetch(ctx, tool_input: dict) -> str:
    """Fetch graph by tag and cache it."""
    from codegraph.tools.dispatcher import _serialize_graph

    tag = tool_input["tag"]
    fmt = tool_input.get("format", "markdown")
    public_only = tool_input.get("public_only", True)

    try:
        graph = ctx.repo.get_by_tag(tag)
        ctx.current_graph = graph
        return _serialize_graph(graph, fmt, public_only)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_fetch_namespace ──────────────────────────────────────────────────

FETCH_NAMESPACE_SCHEMA = {
    "name": "graph_fetch_namespace",
    "description": (
        "Fetch a namespace and all entities it composes (classes, interfaces, "
        "enums, functions) plus their 1-hop neighbors. Use this to drill into "
        "a specific module."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": "Fully qualified namespace name (e.g. 'calc', 'ui').",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": "Output format.",
            },
        },
        "required": ["qualified_name"],
    },
}


def handle_fetch_namespace(ctx, tool_input: dict) -> str:
    qname = tool_input["qualified_name"]
    fmt = tool_input.get("format", "markdown")

    try:
        graph = ctx.repo.get_by_namespace(qname)
        ctx.current_graph = graph
        from codegraph.tools.dispatcher import _serialize_graph
        return _serialize_graph(graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_fetch_neighborhood ───────────────────────────────────────────────

FETCH_NEIGHBORHOOD_SCHEMA = {
    "name": "graph_fetch_neighborhood",
    "description": (
        "Fetch a specific node (compound, member, or namespace) and its "
        "1-hop neighborhood. Use this to deeply inspect a specific class, "
        "method, or namespace and its immediate relationships."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": (
                    "Fully qualified name of the node (e.g. "
                    "'calc::CalculatorEngine', 'calc::CalculatorEngine::add')."
                ),
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": "Output format.",
            },
        },
        "required": ["qualified_name"],
    },
}


def handle_fetch_neighborhood(ctx, tool_input: dict) -> str:
    qname = tool_input["qualified_name"]
    fmt = tool_input.get("format", "markdown")

    try:
        graph = ctx.repo.get_by_neighbourhood(qname)
        ctx.current_graph = graph
        from codegraph.tools.dispatcher import _serialize_graph
        return _serialize_graph(graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_fetch_by_source ──────────────────────────────────────────────────

FETCH_BY_SOURCE_SCHEMA = {
    "name": "graph_fetch_by_source",
    "description": (
        "Fetch all nodes from a given source project plus their neighbors. "
        "Use this to see the complete graph for a specific project or dependency."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source project name (e.g. 'codegraph', 'llvm').",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": "Output format.",
            },
        },
        "required": ["source"],
    },
}


def handle_fetch_by_source(ctx, tool_input: dict) -> str:
    source = tool_input["source"]
    fmt = tool_input.get("format", "markdown")

    try:
        graph = ctx.repo.get_by_source(source)
        ctx.current_graph = graph
        from codegraph.tools.dispatcher import _serialize_graph
        return _serialize_graph(graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_fetch_compound ─────────────────────────────────────────────────

FETCH_COMPOUND_SCHEMA = {
    "name": "graph_fetch_compound",
    "description": (
        "Fetch a specific compound node (class, interface, enum, union, "
        "module) by its qualified name, plus 1-hop neighbors. Use this to "
        "inspect a single class or interface in detail."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": (
                    "Fully qualified compound name (e.g. 'calc::CalculatorEngine')."
                ),
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": "Output format.",
            },
        },
        "required": ["qualified_name"],
    },
}


def handle_fetch_compound(ctx, tool_input: dict) -> str:
    qname = tool_input["qualified_name"]
    fmt = tool_input.get("format", "markdown")

    try:
        graph = ctx.repo.get_by_compound(qname)
        ctx.current_graph = graph
        from codegraph.tools.dispatcher import _serialize_graph
        return _serialize_graph(graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── graph_fetch_by_kind ───────────────────────────────────────────────────

FETCH_BY_KIND_SCHEMA = {
    "name": "graph_fetch_by_kind",
    "description": (
        "Fetch all nodes of a given kind (e.g. 'class', 'method', 'enum'), "
        "optionally filtered by tag, plus their 1-hop neighbors. Use this to "
        "list all classes or all methods in the codebase."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": (
                    "Node kind to filter by: 'class', 'struct', 'interface', "
                    "'enum', 'union', 'module', 'concept', 'method', "
                    "'attribute', 'enumvalue', 'function', 'define', 'namespace'."
                ),
            },
            "tag": {
                "type": "string",
                "description": "Optional tag to further filter results.",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plantuml", "json"],
                "default": "markdown",
                "description": "Output format.",
            },
        },
        "required": ["kind"],
    },
}


def handle_fetch_by_kind(ctx, tool_input: dict) -> str:
    kind = tool_input["kind"]
    tag = tool_input.get("tag")
    fmt = tool_input.get("format", "markdown")

    try:
        graph = ctx.repo.get_by_kind(kind, tag=tag)
        ctx.current_graph = graph
        from codegraph.tools.dispatcher import _serialize_graph
        return _serialize_graph(graph, fmt)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Registration ───────────────────────────────────────────────────────────


def register_all(dispatcher) -> None:
    """Register all query tools on a dispatcher."""
    dispatcher.register(
        "graph_fetch", FETCH_SCHEMA,
        lambda inp: handle_fetch(dispatcher, inp),
    )
    dispatcher.register(
        "graph_fetch_namespace", FETCH_NAMESPACE_SCHEMA,
        lambda inp: handle_fetch_namespace(dispatcher, inp),
    )
    dispatcher.register(
        "graph_fetch_neighborhood", FETCH_NEIGHBORHOOD_SCHEMA,
        lambda inp: handle_fetch_neighborhood(dispatcher, inp),
    )
    dispatcher.register(
        "graph_fetch_compound", FETCH_COMPOUND_SCHEMA,
        lambda inp: handle_fetch_compound(dispatcher, inp),
    )
    dispatcher.register(
        "graph_fetch_by_kind", FETCH_BY_KIND_SCHEMA,
        lambda inp: handle_fetch_by_kind(dispatcher, inp),
    )
    dispatcher.register(
        "graph_fetch_by_source", FETCH_BY_SOURCE_SCHEMA,
        lambda inp: handle_fetch_by_source(dispatcher, inp),
    )
