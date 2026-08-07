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

from codegraph.backends import get_backend

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

def _slim_compound(record: dict) -> dict:
    """Strip heavyweight fields from compound results.

    The discovery agent only needs signatures and brief descriptions.
    """
    drop = {"detailed", "member_refid", "member_brief",
            "_element_id", "_id", "_labels", "_properties"}
    return {k: v for k, v in record.items() if k not in drop}


def _slim_member(record: dict) -> dict:
    """Strip detailed_description from member results."""
    drop = {"detailed", "_element_id", "_id", "_labels", "_properties"}
    return {k: v for k, v in record.items() if k not in drop}


def handle_search_symbols(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Search compounds by qualified name substring."""
    query = tool_input.get("query", "")
    source = tool_input.get("source")
    kind = tool_input.get("kind")
    limit = int(tool_input.get("limit", 30))

    cypher = (
        "MATCH (n:CompoundNode) "
        "WHERE toLower(n.qualified_name) CONTAINS toLower($query) "
    )
    params: dict = {"query": query, "limit": limit}

    if source:
        cypher += "AND n.source = $source "
        params["source"] = source
    if kind:
        cypher += "AND n.kind = $kind "
        params["kind"] = kind

    cypher += (
        "RETURN n.qualified_name AS qn, n.name AS name, "
        "n.kind AS kind, n.source AS source, "
        "n.brief_description AS brief "
        "ORDER BY n.qualified_name "
        "LIMIT $limit"
    )

    results: list[dict] = []
    try:
        rows, _ = get_backend().execute_raw(cypher, params)
        for record in rows:
            results.append(_slim_compound({
                "qualified_name": record["qn"],
                "name": record["name"] or record["qn"].rsplit("::", 1)[-1],
                "kind": record["kind"],
                "source": record["source"],
                "brief_description": record["brief"],
            }))
    except Exception:
        log.warning("search_symbols: query failed", exc_info=True)

    return json.dumps({"results": results, "count": len(results)})


def handle_get_compound(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Fetch a compound node plus its member children."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        # Fetch the compound node
        rows, _ = get_backend().execute_raw(
            "MATCH (n:CompoundNode {qualified_name: $qname}) "
            "RETURN n.qualified_name AS qn, n.name AS name, "
            "n.kind AS kind, n.source AS source, "
            "n.brief_description AS brief", {"qname": qname},
        )
        record = rows[0] if rows else None
        if not record:
            return json.dumps({"error": f"Compound not found: {qname}"})

        compound = _slim_compound({
            "qualified_name": record["qn"],
            "name": record["name"] or record["qn"].rsplit("::", 1)[-1],
            "kind": record["kind"],
            "source": record["source"],
            "brief_description": record["brief"],
        })

        # Fetch member children
        members_rows, _ = get_backend().execute_raw(
            "MATCH (p:CompoundNode {qualified_name: $qname})"
            "-[:COMPOSES]->(m:MemberNode) "
            "RETURN m.qualified_name AS qn, m.name AS name, "
            "m.kind AS kind, m.visibility AS visibility, "
            "m.type_signature AS type_sig, m.brief_description AS brief "
            "ORDER BY m.kind, m.name", {"qname": qname},
        )
        members: list[dict] = []
        for m in member_rows:
            members.append(_slim_member({
                "qualified_name": m["qn"],
                "name": m["name"],
                "kind": m["kind"],
                "visibility": m["visibility"],
                "type_signature": m["type_sig"],
                "brief_description": m["brief"],
            }))
        compound["members"] = members
        compound["member_count"] = len(members)

        return json.dumps(compound)
    except Exception:
        log.warning("get_compound: Neo4j query failed", exc_info=True)
        return json.dumps({"error": f"Query failed for {qname}"})


def handle_get_member(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Fetch a single member node."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        rows, _ = get_backend().execute_raw(
            "MATCH (m:MemberNode {qualified_name: $qname}) "
            "RETURN m.qualified_name AS qn, m.name AS name, "
            "m.kind AS kind, m.visibility AS visibility, "
            "m.type_signature AS type_sig, m.argsstring AS args, "
            "m.brief_description AS brief", {"qname": qname},
        )
        record = rows[0] if rows else None
        if not record:
            return json.dumps({"error": f"Member not found: {qname}"})

        return json.dumps(_slim_member({
            "qualified_name": record["qn"],
            "name": record["name"],
            "kind": record["kind"],
            "visibility": record["visibility"],
            "type_signature": record["type_sig"],
            "argsstring": record["args"],
            "brief_description": record["brief"],
        }))
    except Exception:
        log.warning("get_member: query failed", exc_info=True)
        return json.dumps({"error": f"Query failed for {qname}"})


def handle_browse_namespace(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """List compounds within a namespace prefix."""
    namespace = tool_input.get("namespace", "")
    if not namespace:
        return json.dumps({"error": "namespace is required"})
    limit = int(tool_input.get("limit", 50))

    # Match namespace prefix — e.g., 'std' matches 'std::vector', 'std::chrono::...'
    try:
        rows, _ = get_backend().execute_raw(
            "MATCH (n:CompoundNode) "
            "WHERE n.qualified_name STARTS WITH $ns "
            "RETURN n.qualified_name AS qn, n.name AS name, "
            "n.kind AS kind, n.source AS source, "
            "n.brief_description AS brief "
            "ORDER BY n.qualified_name "
            "LIMIT $limit",
            {
                "ns": namespace + "::" if "::" not in namespace else namespace,
                "limit": limit,
            },
        )
        results: list[dict] = []
        for record in rows:
            results.append(_slim_compound({
                "qualified_name": record["qn"],
                "name": record["name"] or record["qn"].rsplit("::", 1)[-1],
                "kind": record["kind"],
                "source": record["source"],
                "brief_description": record["brief"],
            }))
        return json.dumps({"results": results, "count": len(results)})
    except Exception:
        log.warning("browse_namespace: query failed", exc_info=True)
        return json.dumps({"error": f"Browse failed for {namespace}"})


def handle_list_sources(ctx: CodeGraphDispatcher, _tool_input: dict) -> str:
    """List all source projects with node counts."""
    try:
        rows = get_backend().graph.list_sources()
        sources: dict[str, int] = {row["source"]: row["count"] for row in rows}
        return json.dumps({"sources": sources})
    except Exception:
        log.warning("list_sources: query failed", exc_info=True)
        return json.dumps({"error": "Failed to list sources"})


def handle_list_namespaces(ctx: CodeGraphDispatcher, _tool_input: dict) -> str:
    """List all namespace nodes with entity counts."""
    try:
        rows, _ = get_backend().execute_raw(
            "MATCH (n:NamespaceNode) "
            "OPTIONAL MATCH (n)-[:COMPOSES]->(c) "
            "WHERE c.kind IN ['class','interface','enum','union','struct','concept','module','function','namespace'] "
            "WITH n, count(c) AS entity_count "
            "OPTIONAL MATCH (n)-[:COMPOSES]->(s:NamespaceNode) "
            "RETURN n.qualified_name AS qualified_name, n.name AS name, "
            "entity_count, count(s) AS sub_namespace_count "
            "ORDER BY entity_count DESC"
        )
        results: list[dict] = []
        for record in rows:
            results.append({
                "qualified_name": record["qualified_name"],
                "name": record["name"],
                "entity_count": record["entity_count"],
                "sub_namespace_count": record["sub_namespace_count"],
            })
        return json.dumps({"results": results, "count": len(results)})
    except Exception:
        log.warning("list_namespaces: query failed", exc_info=True)
        return json.dumps({"error": "Failed to list namespaces"})


def handle_find_inheritance(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Find parents and children in the inheritance hierarchy."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        # Parents (what this compound inherits from / realizes)
        parents_rows, _ = get_backend().execute_raw(
            "MATCH (n:CompoundNode {qualified_name: $qname})"
            "-[:INHERITS_FROM|REALIZES]->(p:CompoundNode) "
            "RETURN p.qualified_name AS qn, p.kind AS kind", {"qname": qname},
        )
        parents = [
            {"qualified_name": r["qn"], "kind": r["kind"]}
            for r in parents_rows
        ]

        # Children (what inherits from this)
        children_rows, _ = get_backend().execute_raw(
            "MATCH (c:CompoundNode)-[:INHERITS_FROM|REALIZES]->"
            "(n:CompoundNode {qualified_name: $qname}) "
            "RETURN c.qualified_name AS qn, c.kind AS kind", {"qname": qname},
        )
        children = [
            {"qualified_name": r["qn"], "kind": r["kind"]}
            for r in children_rows
        ]

        return json.dumps({
            "qualified_name": qname,
            "parents": parents,
            "children": children,
        })
    except Exception:
        log.warning("find_inheritance: Neo4j query failed", exc_info=True)
        return json.dumps({"error": f"Inheritance lookup failed for {qname}"})


def handle_find_callers_callees(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Find callers and callees for a member."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"error": "qualified_name is required"})

    try:
        # Callees — what this member calls
        callees_rows, _ = get_backend().execute_raw(
            "MATCH (m:MemberNode {qualified_name: $qname})"
            "-[:INVOKES]->(c:MemberNode) "
            "RETURN c.qualified_name AS qn, c.kind AS kind", {"qname": qname},
        )
        callees = [
            {"qualified_name": r["qn"], "kind": r["kind"]}
            for r in callees_rows
        ]

        # Callers — what calls this member
        callers_rows, _ = get_backend().execute_raw(
            "MATCH (c:MemberNode)-[:INVOKES]->"
            "(m:MemberNode {qualified_name: $qname}) "
            "RETURN c.qualified_name AS qn, c.kind AS kind", {"qname": qname},
        )
        callers = [
            {"qualified_name": r["qn"], "kind": r["kind"]}
            for r in callers_rows
        ]

        return json.dumps({
            "qualified_name": qname,
            "callees": callees,
            "callers": callers,
        })
    except Exception:
        log.warning("find_callers_and_callees: Neo4j query failed", exc_info=True)
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
