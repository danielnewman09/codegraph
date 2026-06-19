"""Lookup tools — container, alias, and dependency-API lookups.

Seed the dependency lookup with standard library containers, build
alias maps for C++ typedefs, and list available dependency-API classes.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.tools.dispatcher import CodeGraphDispatcher

log = logging.getLogger(__name__)

# Curated qualified names for standard containers used as mechanism values.
_STD_CONTAINER_QNAMES: list[str] = [
    "std::vector",
    "std::list",
    "std::deque",
    "std::array",
    "std::set",
    "std::map",
    "std::unordered_set",
    "std::unordered_map",
    "std::stack",
    "std::queue",
    "std::priority_queue",
    "std::shared_ptr",
    "std::unique_ptr",
    "std::weak_ptr",
    "std::string",
    "std::optional",
    "std::variant",
]

# Hardcoded fallback alias map for common C++ typedefs.
_STD_ALIAS_MAP: dict[str, str] = {
    "std::string": "std::basic_string",
    "std::wstring": "std::basic_string",
    "std::u16string": "std::basic_string",
    "std::u32string": "std::basic_string",
    "std::string_view": "std::basic_string_view",
    "std::wstring_view": "std::basic_string_view",
    "std::u16string_view": "std::basic_string_view",
    "std::u32string_view": "std::basic_string_view",
}

# ── Tool schemas ──────────────────────────────────────────────────────────

CONTAINER_LOOKUP_SCHEMA = {
    "name": "container_lookup",
    "description": (
        "Seed the design context with standard library containers and "
        "smart-pointer types. Queries Neo4j for cppreference-indexed types "
        "and populates the dependency lookup map with bare-name → qualified-name "
        "mappings. Call this once before starting a design to ensure "
        "`std::vector`, `std::map`, etc. are resolvable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "container_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of qualified container names to seed. "
                    "Defaults to a curated list of common std types."
                ),
            },
        },
        "required": [],
    },
}


ALIAS_LOOKUP_SCHEMA = {
    "name": "alias_lookup",
    "description": (
        "Build an alias map from developer-friendly C++ type names to their "
        "underlying cppreference qualified names. Queries Neo4j for type_alias "
        "members plus a hardcoded fallback for common typedefs. "
        "Returns a mapping suitable for the design pipeline's alias_lookup parameter."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


GET_CONTAINER_INFO_SCHEMA = {
    "name": "get_container_info",
    "description": (
        "Return class-info dicts for the curated container/smart-pointer set. "
        "Each dict has qualified_name, name, kind, source, and description keys "
        "— suitable for inclusion in the design prompt's dependency API section."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "container_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of qualified container names. "
                    "Defaults to the curated standard list."
                ),
            },
        },
        "required": [],
    },
}


DEPENDENCY_LIST_SCHEMA = {
    "name": "dependency_list",
    "description": (
        "List all available dependency-API classes (from cppreference, boost, "
        "and other indexed sources) with their qualified names, kinds, and "
        "descriptions. Use this to understand what external types are available "
        "for reference in your design."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "Filter by source: 'cppreference', 'boost', or 'all'."
                ),
            },
            "kind": {
                "type": "string",
                "description": (
                    "Filter by node kind: 'class', 'struct', 'interface', 'enum', "
                    "'function', or leave empty for all kinds."
                ),
            },
            "query": {
                "type": "string",
                "description": "Optional substring filter on qualified_name.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 50).",
            },
        },
        "required": [],
    },
}


# ── Internal helpers ──────────────────────────────────────────────────────

def _query_container_nodes(ctx, container_qnames: list[str]) -> list[dict]:
    """Query Neo4j for container nodes and return bare-name→qn mappings."""
    lookup: dict[str, str] = {}
    infos: list[dict] = []

    try:
        with ctx.session() as session:
            result = session.run(
                "MATCH (n:CompoundNode) "
                "WHERE n.qualified_name IN $names "
                "RETURN n.qualified_name AS qn, n.name AS name, "
                "n.kind AS kind, n.source AS source, "
                "n.brief_description AS brief",
                parameters={"names": container_qnames},
            )
            for record in result:
                qn = record["qn"]
                bare = record["name"] or qn.rsplit("::", 1)[-1]
                # Populate the lookup: both bare → qn and qn → qn
                lookup[bare] = qn
                lookup[qn] = qn
                infos.append({
                    "qualified_name": qn,
                    "name": bare,
                    "kind": record["kind"] or "class",
                    "source": record["source"] or "cppreference",
                    "description": record["brief"] or f"Standard library type: {qn}",
                })
    except Exception:
        log.warning("Failed to query Neo4j for container lookup", exc_info=True)

    return infos


def _query_alias_nodes(ctx) -> dict[str, str]:
    """Query Neo4j for type_alias members and return alias → target map."""
    alias_map: dict[str, str] = dict(_STD_ALIAS_MAP)

    try:
        with ctx.session() as session:
            result = session.run(
                "MATCH (m:MemberNode {source: 'cppreference', kind: 'typedef'}) "
                "RETURN m.qualified_name AS qn, m.name AS name"
            )
            for record in result:
                qn = record["qn"]
                name = record["name"]
                if qn and name:
                    if "::" in qn:
                        parent = qn.rsplit("::", 1)[0]
                        alias_name = f"{parent}::{name}"
                    else:
                        alias_name = name
                    alias_map[alias_name] = qn
    except Exception:
        log.warning("Failed to query Neo4j for type aliases", exc_info=True)

    return alias_map


# ── Handlers ──────────────────────────────────────────────────────────────

def handle_container_lookup(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Seed the dispatcher's dependency_lookup with standard containers."""
    container_names = tool_input.get("container_names", [])
    if not container_names:
        container_names = _STD_CONTAINER_QNAMES

    infos = _query_container_nodes(ctx, container_names)

    # Populate the dispatcher's dependency_lookup
    for info in infos:
        qn = info["qualified_name"]
        bare = info["name"]
        ctx.dependency_lookup[bare] = qn
        ctx.dependency_lookup[qn] = qn

    return json.dumps({
        "seeded": True,
        "count": len(infos),
        "containers": [
            {"qualified_name": i["qualified_name"], "name": i["name"]}
            for i in infos
        ],
    })


def handle_alias_lookup(ctx: CodeGraphDispatcher, _tool_input: dict) -> str:
    """Build and return the alias lookup map."""
    alias_map = _query_alias_nodes(ctx)
    # Return a small summary rather than the full map (could be large)
    return json.dumps({
        "alias_count": len(alias_map),
        "sample": {
            k: v for i, (k, v) in enumerate(alias_map.items()) if i < 20
        },
    })


def handle_get_container_info(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """Return class-info dicts for containers."""
    container_names = tool_input.get("container_names", [])
    if not container_names:
        container_names = _STD_CONTAINER_QNAMES

    infos = _query_container_nodes(ctx, container_names)
    return json.dumps({"containers": infos})


def handle_dependency_list(ctx: CodeGraphDispatcher, tool_input: dict) -> str:
    """List available dependency-API classes from Neo4j."""
    source = tool_input.get("source", "all")
    kind = tool_input.get("kind")
    query = tool_input.get("query")
    limit = int(tool_input.get("limit", 50))

    results: list[dict] = []

    cypher = (
        "MATCH (n:CompoundNode) "
        "WHERE n.source IN ['cppreference', 'boost'] "
    )
    params: dict = {}

    if kind and kind != "all":
        cypher += "AND n.kind = $kind "
        params["kind"] = kind

    if source and source != "all":
        cypher += "AND n.source = $source "
        params["source"] = source

    if query:
        cypher += "AND toLower(n.qualified_name) CONTAINS toLower($query) "
        params["query"] = query

    cypher += (
        "RETURN n.qualified_name AS qn, n.name AS name, "
        "n.kind AS kind, n.source AS source, n.brief_description AS brief "
        "ORDER BY n.qualified_name "
        "LIMIT $limit"
    )
    params["limit"] = limit

    try:
        with ctx.session() as session:
            for record in session.run(cypher, params):
                results.append({
                    "qualified_name": record["qn"],
                    "name": record["name"] or record["qn"].rsplit("::", 1)[-1],
                    "kind": record["kind"] or "class",
                    "source": record["source"] or "",
                    "description": record["brief"] or "",
                })
    except Exception:
        log.warning("dependency_list: Neo4j query failed", exc_info=True)

    return json.dumps({"dependencies": results, "count": len(results)})


# ── Registration ──────────────────────────────────────────────────────────

def register_all(dispatcher: CodeGraphDispatcher) -> None:
    """Register all lookup tools on a :class:`CodeGraphDispatcher`."""
    disp = dispatcher
    disp.register(
        "container_lookup", CONTAINER_LOOKUP_SCHEMA,
        lambda inp: handle_container_lookup(disp, inp),
    )
    disp.register(
        "alias_lookup", ALIAS_LOOKUP_SCHEMA,
        lambda inp: handle_alias_lookup(disp, inp),
    )
    disp.register(
        "get_container_info", GET_CONTAINER_INFO_SCHEMA,
        lambda inp: handle_get_container_info(disp, inp),
    )
    disp.register(
        "dependency_list", DEPENDENCY_LIST_SCHEMA,
        lambda inp: handle_dependency_list(disp, inp),
    )
