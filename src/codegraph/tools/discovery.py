"""Discovery tools — browse the codegraph for classes, namespaces,
and search, filtered by source project or kind.

These tools give LLM agents direct read-access to the codegraph
(compounds, members, namespaces, and source listings) for exploring
dependencies and existing code.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.tools.dispatcher import CodeGraphDispatcher

log = logging.getLogger(__name__)

# ── Tool schemas ──────────────────────────────────────────────────────────

SEARCH_SYMBOLS_SCHEMA = {
    "name": "search_symbols",
    "description": (
        "Search the codegraph for compounds (classes, interfaces, enums, etc.) "
        "matching a query string. Searches qualified names. Use this to discover "
        "classes relevant to a requirement or concept. Supports filtering by "
        "source project and kind."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring to search for in compound qualified names.",
            },
            "source": {
                "type": "string",
                "description": "Optional source project filter (e.g., 'cppreference', 'boost').",
            },
            "kind": {
                "type": "string",
                "description": "Optional node kind filter: 'class', 'struct', 'interface', 'enum'.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 30).",
            },
        },
        "required": ["query"],
    },
}


GET_COMPOUND_SCHEMA = {
    "name": "get_compound",
    "description": (
        "Fetch a specific compound (class, interface, enum, etc.) by its fully "
        "qualified name. Returns the compound's details including its methods, "
        "attributes, and brief description. Use this to inspect a class before "
        "deciding to reuse or extend it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": "Fully qualified compound name (e.g., 'std::vector').",
            },
        },
        "required": ["qualified_name"],
    },
}


GET_MEMBER_SCHEMA = {
    "name": "get_member",
    "description": (
        "Fetch a specific member (method, attribute, enum value, etc.) by its "
        "fully qualified name. Returns the member's type signature, visibility, "
        "and brief description."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": (
                    "Fully qualified member name (e.g., 'std::vector::push_back')."
                ),
            },
        },
        "required": ["qualified_name"],
    },
}


BROWSE_NAMESPACE_SCHEMA = {
    "name": "browse_namespace",
    "description": (
        "Browse all compounds within a namespace. Returns a flat list of "
        "classes, interfaces, enums, etc. with their qualified names and "
        "brief descriptions. Use this to discover what types are available "
        "in a given namespace."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Namespace prefix to browse (e.g., 'std', 'boost::asio').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 50).",
            },
        },
        "required": ["namespace"],
    },
}


LIST_SOURCES_SCHEMA = {
    "name": "list_sources",
    "description": (
        "List all available source projects (cppreference, boost, the project's "
        "own code, etc.) with node counts. Use this to discover what codebases "
        "are indexed in the graph."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


LIST_NAMESPACES_SCHEMA = {
    "name": "list_namespaces",
    "description": (
        "List all namespace nodes with entity counts. Returns compact JSON "
        "(qualified_name, name, entity_count, sub_namespace_count) for every "
        "namespace in the graph, sorted by entity_count descending. Use this "
        "to discover which namespaces are large enough to be business components "
        "without pulling the full graph."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


FIND_INHERITANCE_SCHEMA = {
    "name": "find_inheritance",
    "description": (
        "Find the inheritance hierarchy for a compound — its parents (classes "
        "or interfaces it inherits from) and its children (compounds that "
        "inherit from it)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": "Fully qualified compound name.",
            },
        },
        "required": ["qualified_name"],
    },
}


FIND_CALLERS_CALLEES_SCHEMA = {
    "name": "find_callers_and_callees",
    "description": (
        "For a member (method, function), find what calls it (callers) and "
        "what it calls (callees). Returns qualified names of the caller and "
        "callee members."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": "Fully qualified member name.",
            },
        },
        "required": ["qualified_name"],
    },
}

GET_HLR_SUBTREE_SCHEMA = {
    "name": "get_hlr_subtree",
    "description": (
        "Fetch the full requirements subtree for an HLR uid, optionally "
        "filtered by tag.  Returns the HLR, all its LLRs, test nodes, "
        "assertions, test steps, and scaffold/design nodes reachable via "
        "COMPOSES, LEFT_OPERAND, RIGHT_OPERAND, and CALLEE edges.  "
        "When *tag* is provided, only nodes carrying that tag (plus their "
        "ancestors for tree context) are included.  Use this to retrieve "
        "the complete existing picture before decomposing, designing, or "
        "enriching a requirement — or pass ``tag='scaffold'`` to see only "
        "scaffold nodes in the subtree."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "uid": {
                "type": "string",
                "description": "The HLR uid (hex UUID string).",
            },
            "tag": {
                "type": "string",
                "description": (
                    "Optional tag to filter the subtree by.  When provided, "
                    "only nodes that carry this tag (plus their ancestors "
                    "to preserve tree structure) are included.  "
                    "Example: 'scaffold', 'design', 'as-built'."
                ),
            },
        },
        "required": ["uid"],
    },
}


# ── Handlers ──────────────────────────────────────────────────────────────

def _display_name(record: dict) -> str:
    """Short-name fallback: ``name`` or the last qualified-name segment."""
    name = record.get("name")
    if name:
        return name
    return str(record["qualified_name"]).rsplit("::", 1)[-1]


def _with_display_name(record: dict) -> dict:
    record["name"] = _display_name(record)
    return record


def handle_search_symbols(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Search compounds by qualified name substring."""
    query = tool_input.get("query", "")
    source = tool_input.get("source")
    kind = tool_input.get("kind")
    limit = int(tool_input.get("limit", 30))

    try:
        rows = ctx.repo.search_compounds(
            query, source=source, kind=kind, limit=limit
        )
        results = [_with_display_name(r) for r in rows]
        return json.dumps({"results": results, "count": len(results)})
    except Exception:
        log.warning("search_symbols: query failed", exc_info=True)
        return json.dumps({"results": [], "count": 0})


def handle_get_compound(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Fetch a compound node plus its member children."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        compound = ctx.repo.get_compound(qname)
        if compound is None:
            return json.dumps({"error": f"Compound not found: {qname}"})
        _with_display_name(compound)
        compound["members"] = [
            _with_display_name(m) for m in compound.get("members", [])
        ]
        return json.dumps(compound)
    except Exception:
        log.warning("get_compound: query failed", exc_info=True)
        return json.dumps({"error": f"Query failed for {qname}"})


def handle_get_member(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Fetch a single member node."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        member = ctx.repo.get_member(qname)
        if member is None:
            return json.dumps({"error": f"Member not found: {qname}"})
        return json.dumps(_with_display_name(member))
    except Exception:
        log.warning("get_member: query failed", exc_info=True)
        return json.dumps({"error": f"Query failed for {qname}"})


def handle_browse_namespace(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """List compounds within a namespace prefix."""
    namespace = tool_input.get("namespace", "")
    if not namespace:
        return json.dumps({"error": "namespace is required"})
    limit = int(tool_input.get("limit", 50))

    try:
        rows = ctx.repo.browse_namespace(namespace, limit=limit)
        results = [_with_display_name(r) for r in rows]
        return json.dumps({"results": results, "count": len(results)})
    except Exception:
        log.warning("browse_namespace: query failed", exc_info=True)
        return json.dumps({"error": f"Browse failed for {namespace}"})


def handle_list_sources(ctx: CodeGraphDispatcher, _tool_input: dict) -> str:
    """List all source projects with node counts."""
    try:
        rows = ctx.repo.list_sources()
        sources: dict[str, int] = {row["source"]: row["count"] for row in rows}
        return json.dumps({"sources": sources})
    except Exception:
        log.warning("list_sources: query failed", exc_info=True)
        return json.dumps({"error": "Failed to list sources"})


def handle_list_namespaces(ctx: CodeGraphDispatcher, _tool_input: dict) -> str:
    """List all namespace nodes with entity counts."""
    try:
        rows = ctx.repo.list_namespaces()
        return json.dumps({"results": rows, "count": len(rows)})
    except Exception:
        log.warning("list_namespaces: query failed", exc_info=True)
        return json.dumps({"error": "Failed to list namespaces"})


def handle_find_inheritance(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Find parents and children in the inheritance hierarchy."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        result = ctx.repo.find_inheritance(qname)
        result["qualified_name"] = qname
        return json.dumps(result)
    except Exception:
        log.warning("find_inheritance: query failed", exc_info=True)
        return json.dumps({"error": f"Inheritance lookup failed for {qname}"})


def handle_find_callers_callees(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Find callers and callees for a member."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        result = ctx.repo.find_callers_callees(qname)
        result["qualified_name"] = qname
        return json.dumps(result)
    except Exception:
        log.warning("find_callers_and_callees: query failed", exc_info=True)
        return json.dumps({"error": f"Caller/callee lookup failed for {qname}"})


def handle_get_hlr_subtree(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Fetch the full requirements subtree for an HLR uid.

    Uses ``GraphRepository.get_hlr_subtree()`` to do a multi-hop COMPOSES
    traversal, optionally filtered by tag, then serializes the resulting
    LayerGraph to JSON.
    """
    from codegraph.export.format import export_graph

    target_uid = tool_input.get("uid", "")
    if not target_uid:
        return json.dumps({"error": "uid is required"})

    tag = tool_input.get("tag", "")

    try:
        graph = ctx.repo.get_hlr_subtree(target_uid, tag=tag)
        ctx.current_graph = graph  # cache
        result = export_graph(graph, format="json")
        return result
    except Exception as exc:
        log.exception("get_hlr_subtree failed for uid '%s'", target_uid)
        return json.dumps({"error": str(exc)})


# ── Registration ──────────────────────────────────────────────────────────

def register_all(dispatcher: CodeGraphDispatcher) -> None:
    """Register all discovery tools on a :class:`CodeGraphDispatcher`."""
    disp = dispatcher
    disp.register(
        "search_symbols", SEARCH_SYMBOLS_SCHEMA,
        lambda inp: handle_search_symbols(disp, inp),
    )
    disp.register(
        "get_compound", GET_COMPOUND_SCHEMA,
        lambda inp: handle_get_compound(disp, inp),
    )
    disp.register(
        "get_member", GET_MEMBER_SCHEMA,
        lambda inp: handle_get_member(disp, inp),
    )
    disp.register(
        "browse_namespace", BROWSE_NAMESPACE_SCHEMA,
        lambda inp: handle_browse_namespace(disp, inp),
    )
    disp.register(
        "list_sources", LIST_SOURCES_SCHEMA,
        lambda inp: handle_list_sources(disp, inp),
    )
    disp.register(
        "find_inheritance", FIND_INHERITANCE_SCHEMA,
        lambda inp: handle_find_inheritance(disp, inp),
    )
    disp.register(
        "list_namespaces", LIST_NAMESPACES_SCHEMA,
        lambda inp: handle_list_namespaces(disp, inp),
    )
    disp.register(
        "find_callers_and_callees", FIND_CALLERS_CALLEES_SCHEMA,
        lambda inp: handle_find_callers_callees(disp, inp),
    )
    disp.register(
        "get_hlr_subtree", GET_HLR_SUBTREE_SCHEMA,
        lambda inp: handle_get_hlr_subtree(disp, inp),
    )
