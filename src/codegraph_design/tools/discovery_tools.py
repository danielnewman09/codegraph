"""Tools for design discovery — search requirements, traverse dependencies,
assemble context documents.

Each tool has a ``SCHEMA`` dict and a ``handle_*(ctx, tool_input)``
function registered by ``register_all(dispatcher)`` on a
:class:`DesignDiscoveryDispatcher`.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

SEARCH_REQUIREMENTS_SCHEMA = {
    "name": "search_requirements",
    "description": (
        "Search HLRs and LLRs by a keyword or phrase in their description "
        "field. Returns matching requirement summaries (refid, description, "
        "layer, tags, component). Useful for discovering requirements by "
        "concept or feature area before designing a new feature."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search text — matched case-insensitively against requirement descriptions.",
            },
            "scope": {
                "type": "string",
                "enum": ["hlr", "llr", "both"],
                "default": "both",
            },
            "limit": {
                "type": "integer",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}


GET_HLR_DEPENDENCIES_SCHEMA = {
    "name": "get_hlr_dependencies",
    "description": (
        "Traverse outgoing DEPENDS_ON edges from an HLR to discover other "
        "HLRs it depends on. Returns dependent HLR refids, names, descriptions, "
        "and components. Use this to understand which requirements must be "
        "satisfied before designing this HLR."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refid": {
                "type": "string",
                "description": "The refid of the HLR whose dependencies to retrieve.",
            },
            "direction": {
                "type": "string",
                "enum": ["outgoing", "incoming", "both"],
                "default": "outgoing",
                "description": "outgoing = what this HLR depends on; incoming = what depends on this HLR.",
            },
        },
        "required": ["refid"],
    },
}


LIST_REQUIREMENTS_SCHEMA = {
    "name": "list_requirements",
    "description": (
        "List all high-level requirements (HLRs), optionally filtered by "
        "component name and/or tag. Returns summary dicts with refid, name, "
        "description, and tags. Use this as a starting point to discover what "
        "HLRs exist before drilling into specific ones."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "component_name": {"type": "string"},
            "tag": {"type": "string", "description": "Filter by tag: 'design', 'as-built', etc."},
        },
        "required": [],
    },
}


GET_REQUIREMENT_TRACES_SCHEMA = {
    "name": "get_requirement_traces",
    "description": (
        "Retrieve all COMPOSES edges from an HLR or LLR to design-graph "
        "nodes (classes, interfaces, enums, methods). Shows which design "
        "elements this requirement composes — i.e., which code implements "
        "or satisfies the requirement."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refid": {"type": "string", "description": "The refid of the HLR or LLR."},
        },
        "required": ["refid"],
    },
}


BUILD_DESIGN_CONTEXT_SCHEMA = {
    "name": "build_design_context",
    "description": (
        "Assemble a structured context document from discovered requirements "
        "and code. Given a feature description and optional component name, "
        "returns a markdown document containing: matching requirements, "
        "related requirements via DEPENDS_ON, existing code from namespace/"
        "compound discovery, inter-component boundaries, and dependency APIs. "
        "Inject this context into a design agent's prompt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "feature_description": {
                "type": "string",
                "description": "Description of the feature being designed.",
            },
            "component_name": {
                "type": "string",
                "description": "Optional component name to scope the discovery.",
            },
        },
        "required": ["feature_description"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════


def _serialize_hlr_brief(hlr) -> dict:
    return {
        "refid": hlr.refid,
        "name": hlr.name or "",
        "description": hlr.description,
        "tags": list(hlr.tags) if hlr.tags else [],
    }


def _serialize_llr_brief(llr) -> dict:
    return {
        "refid": llr.refid,
        "name": llr.name or "",
        "description": llr.description,
        "tags": list(llr.tags) if llr.tags else [],
    }


def _serialize_design_links(node) -> list[dict]:
    """Collect all COMPOSES edges from a requirement node to design nodes."""
    links = []
    for target in node.design_compounds.all():
        links.append({
            "target_qualified_name": target.qualified_name,
            "target_name": target.name or "",
            "target_kind": getattr(target, "kind", type(target).__name__),
            "target_type": type(target).__name__,
        })
    return links


# ══════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════


def handle_search_requirements(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Search HLRs and/or LLRs by description keyword."""
    from codegraph_requirements.models import HLR, LLR

    query = tool_input.get("query", "")
    scope = tool_input.get("scope", "both")
    limit = int(tool_input.get("limit", 20))

    if not query:
        return json.dumps({"error": "query is required", "results": []})

    query_lower = query.lower()
    results: list[dict] = []

    try:
        if scope in ("hlr", "both"):
            for hlr in HLR.nodes.all():
                if query_lower in (hlr.description or "").lower():
                    comp_nodes = hlr.component.all()
                    comp_name = comp_nodes[0].name if comp_nodes else ""
                    results.append({
                        "type": "HLR",
                        "component": comp_name,
                        **_serialize_hlr_brief(hlr),
                    })
                    if len(results) >= limit:
                        break

        if scope in ("llr", "both") and len(results) < limit:
            for llr in LLR.nodes.all():
                if query_lower in (llr.description or "").lower():
                    parent_hlrs = llr.hlr.all()
                    comp_name = ""
                    if parent_hlrs:
                        comp_nodes = parent_hlrs[0].component.all()
                        comp_name = comp_nodes[0].name if comp_nodes else ""
                    results.append({
                        "type": "LLR",
                        "component": comp_name,
                        **_serialize_llr_brief(llr),
                    })
                    if len(results) >= limit:
                        break
    except Exception as exc:
        log.exception("Failed to search requirements for query '%s'", query)
        return json.dumps({"error": f"Search error: {exc}", "results": []})

    return json.dumps({"query": query, "scope": scope, "count": len(results), "results": results})


def handle_get_hlr_dependencies(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Traverse DEPENDS_ON edges from an HLR."""
    from codegraph_requirements.models import HLR

    refid = tool_input.get("refid", "")
    direction = tool_input.get("direction", "outgoing")

    if not refid:
        return json.dumps({"error": "refid is required"})

    hlr = HLR.nodes.get_or_none(refid=refid)
    if hlr is None:
        return json.dumps({"error": f"HLR with refid '{refid}' not found"})

    def _serialize_dep(other_hlr, direction_label):
        comp_nodes = other_hlr.component.all()
        return {
            "refid": other_hlr.refid,
            "name": other_hlr.name or "",
            "description": other_hlr.description,
            "component": comp_nodes[0].name if comp_nodes else "",
            "tags": list(other_hlr.tags) if other_hlr.tags else [],
            "direction": direction_label,
        }

    results: list[dict] = []
    try:
        if direction in ("outgoing", "both"):
            for dep in hlr.depends_on_hlrs.all():
                results.append(_serialize_dep(dep, "outgoing"))
        if direction in ("incoming", "both"):
            for dep in hlr.depended_on_by_hlrs.all():
                results.append(_serialize_dep(dep, "incoming"))
    except Exception as exc:
        log.exception("Failed to get HLR dependencies for %s", refid)
        return json.dumps({"error": f"Traversal error: {exc}"})

    return json.dumps({"refid": refid, "count": len(results), "dependencies": results})


def handle_list_requirements(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """List all HLRs, optionally filtered by component and tag."""
    from codegraph_requirements.models import HLR

    component_name = tool_input.get("component_name")
    tag = tool_input.get("tag")

    results: list[dict] = []

    try:
        all_hlrs = HLR.nodes.all()
        for hlr in all_hlrs:
            if tag and (not hlr.tags or tag not in hlr.tags):
                continue
            comp_name = ""
            if component_name:
                comp_nodes = hlr.component.all()
                comp_name = comp_nodes[0].name if comp_nodes else ""
                if comp_name != component_name:
                    continue
            results.append(_serialize_hlr_brief(hlr))
    except Exception as exc:
        log.exception("Failed to list requirements")
        return json.dumps({"error": f"List error: {exc}", "results": []})

    return json.dumps({"count": len(results), "hlrs": results})


def handle_get_requirement_traces(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Retrieve all COMPOSES edges from an HLR or LLR to design nodes."""
    from codegraph_requirements.models import HLR, LLR

    refid = tool_input.get("refid", "")
    if not refid:
        return json.dumps({"error": "refid is required"})

    node = HLR.nodes.get_or_none(refid=refid)
    req_type = "HLR"
    if node is None:
        node = LLR.nodes.get_or_none(refid=refid)
        req_type = "LLR"
    if node is None:
        return json.dumps({"error": f"No HLR or LLR found with refid '{refid}'"})

    try:
        design_links = _serialize_design_links(node)
        return json.dumps({
            "refid": refid, "type": req_type,
            "description": node.description, "design_links": design_links,
        })
    except Exception as exc:
        log.exception("Failed to serialize design links for refid '%s'", refid)
        return json.dumps({"error": f"Serialization error: {exc}"})


def handle_build_design_context(ctx: DesignDiscoveryDispatcher, tool_input: dict) -> str:
    """Assemble a structured context document from discovered requirements and code."""
    feature_description = tool_input.get("feature_description", "")
    component_name = tool_input.get("component_name", "")

    if not feature_description:
        return json.dumps({"error": "feature_description is required"})

    lines: list[str] = []
    lines.append("# Design Context")
    lines.append("")
    lines.append(f"**Feature**: {feature_description}")
    if component_name:
        lines.append(f"**Component**: {component_name}")
    lines.append("")

    # 1. Search for related requirements
    lines.append("## Related Requirements")
    search_result = json.loads(handle_search_requirements(ctx, {
        "query": feature_description, "scope": "both", "limit": 20,
    }))
    if search_result.get("results"):
        for req in search_result["results"]:
            lines.append(f"- [{req['type']}] {req.get('name', '')}: {req['description'][:200]}")
            if req.get("component"):
                lines.append(f"  - Component: {req['component']}")
    else:
        lines.append("_No matching requirements found._")
    lines.append("")

    # 2. List all requirements in the component (if specified)
    if component_name:
        lines.append(f"## Requirements in Component: {component_name}")
        list_result = json.loads(handle_list_requirements(ctx, {
            "component_name": component_name,
        }))
        if list_result.get("hlrs"):
            for hlr in list_result["hlrs"]:
                lines.append(f"- {hlr.get('name', '')}: {hlr['description'][:200]}")
        else:
            lines.append("_No requirements found in this component._")
        lines.append("")

    # 3. Inter-component boundaries
    if ctx.intercomponent_classes:
        lines.append("## Inter-Component Boundaries")
        for cls in ctx.intercomponent_classes:
            lines.append(f"- {cls.get('qualified_name', '')} ({cls.get('kind', 'class')})")
        lines.append("")

    # 4. Dependency APIs
    if ctx.dependency_apis:
        lines.append("## Dependency APIs")
        for bare, qname in ctx.dependency_apis.items():
            lines.append(f"- {bare} → {qname}")
        lines.append("")

    # 5. Prior designs
    if ctx.prior_designs:
        lines.append("## Prior Designs")
        for bare, qname in ctx.prior_designs.items():
            lines.append(f"- {bare} → {qname}")
        lines.append("")

    return json.dumps({"context": "\n".join(lines)})


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════


def register_all(dispatcher: DesignDiscoveryDispatcher) -> None:
    """Register all discovery tools on a DesignDiscoveryDispatcher."""
    disp = dispatcher
    disp.register(
        "search_requirements", SEARCH_REQUIREMENTS_SCHEMA,
        lambda inp: handle_search_requirements(disp, inp),
    )
    disp.register(
        "get_hlr_dependencies", GET_HLR_DEPENDENCIES_SCHEMA,
        lambda inp: handle_get_hlr_dependencies(disp, inp),
    )
    disp.register(
        "list_requirements", LIST_REQUIREMENTS_SCHEMA,
        lambda inp: handle_list_requirements(disp, inp),
    )
    disp.register(
        "get_requirement_traces", GET_REQUIREMENT_TRACES_SCHEMA,
        lambda inp: handle_get_requirement_traces(disp, inp),
    )
    disp.register(
        "build_design_context", BUILD_DESIGN_CONTEXT_SCHEMA,
        lambda inp: handle_build_design_context(disp, inp),
    )