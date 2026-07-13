"""Design-validation tools — validate_design, check_class_name, produce_oo_design.

Ported from ticketing-system ``backend_migrated.tools.design_tools``.
Each tool has a ``SCHEMA`` dict and a ``handle_*(ctx, tool_input)``
function registered by ``register_all(dispatcher)``.

Uses the codegraph backend (:class:`GraphRepository`) for Neo4j
queries and reads from the dispatcher's mutable lookups.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from codegraph.graph import LayerGraph

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import DesignToolDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Shared diagram schema — mirrors LayerGraph's JSON serialization format
# ══════════════════════════════════════════════════════════════════════════

def _build_layer_graph_schema() -> dict:
    """Build a JSON Schema that mirrors the LayerGraph serialization format.

    Returns a schema describing ``list[dict]`` — the format accepted by
    ``LayerGraph.deserialize()``.  Each entry has a ``type`` discriminator
    and the LLM-relevant property fields for that CodeGraphNode subclass,
    plus optional ``edges`` and ``composes`` arrays.
    """
    from codegraph.models.compound import (
        ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    )
    from codegraph.models.member import (
        MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    )
    from codegraph.models.namespace import NamespaceNode

    _TYPE_MAP: dict[str, type] = {
        "ClassNode": ClassNode,
        "InterfaceNode": InterfaceNode,
        "EnumNode": EnumNode,
        "UnionNode": UnionNode,
        "ModuleNode": ModuleNode,
        "MethodNode": MethodNode,
        "AttributeNode": AttributeNode,
        "EnumValueNode": EnumValueNode,
        "FunctionNode": FunctionNode,
        "DefineNode": DefineNode,
        "NamespaceNode": NamespaceNode,
    }

    _PROP_TYPE_MAP: dict[str, str | dict] = {
        "StringProperty":     {"type": "string"},
        "UniqueIdProperty":   {"type": "string"},
        "IntegerProperty":    {"type": "integer"},
        "BooleanProperty":    {"type": "boolean"},
        "ArrayProperty":      {"type": "array", "items": {"type": "string"}},
        "FloatProperty":      {"type": "number"},
        "JSONProperty":       {},
    }

    node_schemas: list[dict] = []

    for type_name, node_cls in sorted(_TYPE_MAP.items()):
        props: dict[str, dict] = {}
        required: list[str] = []

        for field_name in sorted(node_cls._llm_fields):
            prop_def = None
            for pname, pdef in node_cls.__all_properties__:
                if pname == field_name:
                    prop_def = pdef
                    break

            if prop_def is not None:
                prop_type_name = type(prop_def).__name__
                json_type = _PROP_TYPE_MAP.get(prop_type_name, {})
                if json_type:
                    desc = getattr(prop_def, "description", "") or ""
                    field_schema: dict = dict(json_type)
                    if desc:
                        field_schema["description"] = desc
                    props[field_name] = field_schema

                if getattr(prop_def, "required", False) or field_name in (
                    "name", "qualified_name", "kind",
                ):
                    required.append(field_name)
            else:
                if field_name == "tags":
                    props[field_name] = {
                        "type": "array", "items": {"type": "string"},
                        "description": "Tags applied to this node (e.g. 'design').",
                    }
                else:
                    props[field_name] = {"type": "string"}

        props["type"] = {"type": "string", "const": type_name}

        node_schema: dict = {
            "type": "object",
            "properties": props,
            "required": required + ["type"],
        }

        node_schema["properties"]["edges"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relation_type": {
                        "type": "string",
                        "description": "Relationship label (e.g. INHERITS_FROM, REALIZES, DEPENDS_ON, INVOKES).",
                    },
                    "target_uid": {
                        "type": "string",
                        "description": "Unique identifier of the target node (typically qualified_name).",
                    },
                    "target_type": {
                        "type": "string",
                        "description": "Type discriminator of the target node (e.g. 'ClassNode', 'MethodNode').",
                    },
                },
                "required": ["relation_type", "target_uid", "target_type"],
            },
            "description": "Non-composition edges from this node to other nodes.",
        }

        node_schemas.append(node_schema)

    nodes_array = {
        "type": "array",
        "items": {
            "oneOf": node_schemas,
            "discriminator": {
                "propertyName": "type",
            },
        },
        "minItems": 1,
        "description": (
            "A list of CodeGraphNode dicts in the LayerGraph serialization format. "
            "Compound nodes (ClassNode, InterfaceNode, EnumNode) may include a "
            "'composes' array containing their member children (MethodNode, "
            "AttributeNode, EnumValueNode). Edges represent cross-references "
            "like INHERITS_FROM, REALIZES, DEPENDS_ON."
        ),
    }
    return {
        "type": "object",
        "properties": {
            "nodes": nodes_array,
        },
        "required": ["nodes"],
    }


_DIAGRAM_SCHEMA = _build_layer_graph_schema()


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

VALIDATE_DESIGN_SCHEMA = {
    "name": "validate_design",
    "description": (
        "Validate a draft OO design before committing it. Accepts a list of "
        "CodeGraphNode dicts in the LayerGraph serialization format (each with "
        "a 'type' field and LLM-relevant properties). Checks for unknown "
        "edge targets, missing intercomponent references, and duplicate "
        "qualified names. Returns a list of errors and warnings. Use this "
        "to check your work before calling produce_oo_design."
    ),
    "input_schema": _DIAGRAM_SCHEMA,
}


CHECK_CLASS_NAME_SCHEMA = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design context "
        "(prior designs, dependency APIs, or intercomponent boundaries). "
        "Use this to verify that edge targets and type references are "
        "valid before including them in your design. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. "
                    "Can be a bare name (e.g., 'Thermostat') or a qualified name "
                    "(e.g., 'climate_control::Thermostat'). Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}


PRODUCE_OO_DESIGN_SCHEMA = {
    "name": "produce_oo_design",
    "description": (
        "Submit the final object-oriented class design as a list of "
        "CodeGraphNode dicts in the LayerGraph serialization format. "
        "The design is stored so that verification tools can validate "
        "references against it. Call this AFTER you are confident the "
        "design is correct — use validate_design first to check for "
        "issues. After this, proceed to resolve verification stubs "
        "using draft_verifications."
    ),
    "input_schema": _DIAGRAM_SCHEMA,
}


# ══════════════════════════════════════════════════════════════════════════
# Design validation helpers
# ══════════════════════════════════════════════════════════════════════════

def _node_qname(node: dict) -> str:
    """Extract the effective qualified name from a node dict."""
    qn = node.get("qualified_name", "")
    if qn:
        return qn
    name = node.get("name", "")
    return name


def _collect_qnames(nodes: list[dict]) -> dict[str, str]:
    """Build a mapping of bare_name → qualified_name from a list of nodes."""
    lookup: dict[str, str] = {}
    for node in nodes:
        qn = _node_qname(node)
        bare = node.get("name", qn.rsplit("::", 1)[-1] if "::" in qn else qn)
        if bare:
            lookup[bare] = qn
        if qn:
            lookup[qn] = qn
    return lookup


def _collect_edges(nodes: list[dict]) -> list[dict]:
    """Collect all edges from a flat list of nodes (including composed children)."""
    all_edges: list[dict] = []

    def walk(n: dict) -> None:
        for edge in n.get("edges", []):
            all_edges.append(edge)
        for child in n.get("composes", []):
            walk(child)

    for node in nodes:
        walk(node)
    return all_edges


def _qname_in_codegraph(qname: str) -> bool:
    """Check if a qualified or bare name exists anywhere in the codegraph.

    One Cypher probe — index-backed, no tag filtering.  Any node in the
    codegraph (any kind, any tag) is a valid reference target.

    Opens its own transient session (only called when all other lookups
    have missed, so the overhead is negligible).
    """
    import re
    if not qname:
        return False
    safe = re.escape(qname)
    bare = safe.rsplit("::", 1)[-1] if "::" in safe else safe
    try:
        from codegraph.persistence.connection import get_session
        with get_session() as s:
            result = s.run(
                "MATCH (n) WHERE n.qualified_name = $qn "
                "OR n.qualified_name ENDS WITH $suffix "
                "OR n.name = $bare "
                "RETURN n.qualified_name AS qn, n.name AS name, "
                "labels(n) AS labels, n.tags AS tags "
                "LIMIT 1",
                {"qn": qname, "suffix": "::" + bare, "bare": bare},
            )
            record = result.single()
            found = bool(record and record["qn"])
            if found:
                log.debug(
                    "_qname_in_codegraph(%s): matched %s (labels=%s, tags=%s)",
                    qname, record["qn"], record["labels"], record["tags"],
                )
            else:
                log.debug(
                    "_qname_in_codegraph(%s): no match in codegraph",
                    qname,
                )
            return found
    except Exception:
        return False


def _validate_oo_design(
    design: list[dict],
    *,
    has_qname,
) -> list[str]:
    """Validate a LayerGraph-format design (list of CodeGraphNode dicts).

    Checks:
    1. Unknown edge targets (not in design, context, or codegraph)
    2. Duplicate qualified names
    """
    errors: list[str] = []

    design_qnames = _collect_qnames(design)

    # 1. Check edge targets — delegate to unified resolution
    for edge in _collect_edges(design):
        target = edge.get("target_uid", "")
        if not target:
            continue
        target_bare = target.rsplit("::", 1)[-1] if "::" in target else target
        if (
            target in design_qnames
            or target_bare in design_qnames
            or has_qname(target)
            or has_qname(target_bare)
        ):
            continue
        errors.append(
            f"Edge target '{target}' not found — "
            f"use import_compound to load it from the codegraph first"
        )

    # 2. Check for duplicate qualified names
    seen: dict[str, int] = {}

    def _count_qnames(n: dict) -> None:
        qn = _node_qname(n)
        seen[qn] = seen.get(qn, 0) + 1
        for child in n.get("composes", []):
            _count_qnames(child)

    for node in design:
        _count_qnames(node)

    for qn, count in seen.items():
        if count > 1:
            errors.append(f"Duplicate qualified name: '{qn}' appears {count} times")

    return errors


# ══════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════

def handle_validate_design(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Validate a draft OO design — edge targets, duplicates, AND structural smells."""
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes and ctx.design_draft:
        nodes = ctx.design_draft
    if not nodes:
        return json.dumps({"valid": False, "errors": ["No nodes provided"], "warnings": []})

    # ── Edge-target and duplicate checks ────────────────────────────
    errors = _validate_oo_design(
        nodes,
        has_qname=ctx.has_qname,
    )

    critical = [e for e in errors if not e.startswith("Warning:")]
    warnings = [e.replace("Warning: ", "") for e in errors if e.startswith("Warning:")]

    # ── Structural smell checks (forced — runs automatically) ────────
    from codegraph_design.tools.design_smells import run_all_smells
    smell_report = run_all_smells(nodes)
    for s in smell_report.smells:
        msg = f"[{s.severity}] {s.id}: {s.detail}"
        if s.severity == "blocking":
            critical.append(msg)
        else:
            warnings.append(msg)

    return json.dumps({
        "valid": len(critical) == 0,
        "errors": critical,
        "warnings": warnings,
        "smell_summary": smell_report.summary,
    })


def handle_produce_oo_design(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Store the final design on the dispatcher for verification tools."""
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes:
        return json.dumps({
            "stored": False,
            "errors": ["No nodes provided"],
        })

    # ── Edge-target and duplicate checks ────────────────────────────
    errors = _validate_oo_design(
        nodes,
        has_qname=ctx.has_qname,
    )
    critical = [e for e in errors if not e.startswith("Warning:")]
    warnings = [e.replace("Warning: ", "") for e in errors if e.startswith("Warning:")]

    # ── Structural smell checks (forced — runs automatically) ────────
    from codegraph_design.tools.design_smells import run_all_smells
    smell_report = run_all_smells(nodes)
    for s in smell_report.smells:
        msg = f"[{s.severity}] {s.id}: {s.detail}"
        if s.severity == "blocking":
            critical.append(msg)
        else:
            warnings.append(msg)

    if critical:
        return json.dumps({
            "stored": False,
            "errors": critical,
            "warnings": warnings,
            "smell_summary": smell_report.summary,
            "hint": "Fix errors and call produce_oo_design again.",
        })

    ctx.design_draft_graph = LayerGraph.deserialize(nodes)
    design_size = sum(1 for _ in ctx.design_draft_graph._all_entries())
    log.info(
        "produce_oo_design: stored %d nodes in design_draft_graph",
        design_size,
    )

    return json.dumps({
        "stored": True,
        "warnings": warnings,
        "smell_summary": smell_report.summary,
        "hint": (
            "Design stored. Now resolve verification stubs using "
            "draft_verifications, then call "
            "commit_design_and_verifications to finish."
        ),
    })


IMPORT_COMPOUND_SCHEMA = {
    "name": "import_compound",
    "description": (
        "Load a class, interface, enum, or namespace from the codegraph "
        "into the working context graph.  Use this to make as-built or "
        "prior-design nodes available as valid reference targets for "
        "DEPENDS_ON edges, type signatures, and verifications.  Call "
        "search_symbols first to discover qualified names, then "
        "import_compound to load them.  The loaded node and its members "
        "become resolvable by validate_design and draft_verifications."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": (
                    "Fully-qualified name of the compound or namespace "
                    "to import (e.g. 'codegraph.graph.LayerGraph')."
                ),
            },
        },
        "required": ["qualified_name"],
    },
}


def handle_import_compound(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Load a compound from Neo4j into the context LayerGraph."""
    qname = tool_input.get("qualified_name", "")
    if not qname:
        return json.dumps({"imported": False, "error": "qualified_name is required"})

    try:
        sub = LayerGraph.import_compound(qname)
    except ValueError as exc:
        log.debug("import_compound(%s): not found — %s", qname, exc)
        return json.dumps({"imported": False, "error": str(exc)})
    except Exception as exc:
        log.debug("import_compound(%s): error — %s", qname, exc)
        return json.dumps(
            {"imported": False, "error": f"Import failed: {exc}"}
        )

    if not sub.entries:
        return json.dumps({
            "imported": False, "error": f"No entries found for '{qname}'",
        })

    ctx.context_graph.merge(sub)
    ctx_size = sum(1 for _ in ctx.context_graph._all_entries())
    sub_size = sum(1 for _ in sub._all_entries())
    log.info(
        "import_compound(%s): loaded %d nodes into context_graph (total now %d)",
        qname, sub_size, ctx_size,
    )
    imported = []
    for entry in sub._all_entries():
        node = entry.node
        imported.append({
            "qualified_name": getattr(node, "qualified_name", ""),
            "name": getattr(node, "name", ""),
            "kind": getattr(node, "kind", type(node).__name__),
            "type": type(node).__name__,
        })

    total_ctx = len(ctx.context_graph.entries)
    return json.dumps({
        "imported": True,
        "qualified_name": qname,
        "nodes_imported": len(imported),
        "imported_nodes": imported,
        "context_graph_size": total_ctx,
        "hint": (
            f"'{qname}' and its members are now valid reference targets. "
            f"Context graph has {total_ctx} root entries."
        ),
    })


def handle_check_class_name(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Check if a class name exists in context graph, design draft,
    or the codegraph."""
    name = tool_input.get("name", "")
    if not name:
        return json.dumps({"found": False, "matches": []})

    matches: list[dict] = []
    name_lower = name.lower()
    seen: set[str] = set()

    # Search context_graph
    for entry in ctx.context_graph._all_entries():
        node = entry.node
        qn = getattr(node, "qualified_name", "") or ""
        node_name = getattr(node, "name", "") or ""
        if name_lower in qn.lower() or name_lower in node_name.lower():
            kind = getattr(node, "kind", type(node).__name__)
            if qn and qn not in seen:
                seen.add(qn)
                matches.append({
                    "qualified_name": qn,
                    "name": node_name,
                    "kind": kind,
                    "source": "context",
                })

    # Search design_draft_graph
    for entry in ctx.design_draft_graph._all_entries():
        node = entry.node
        qn = getattr(node, "qualified_name", "") or ""
        node_name = getattr(node, "name", "") or ""
        if (name_lower in qn.lower() or name_lower in node_name.lower()):
            if qn and qn not in seen:
                seen.add(qn)
                matches.append({
                    "qualified_name": qn,
                    "name": node_name,
                    "kind": getattr(node, "kind", type(node).__name__),
                    "source": "design_draft",
                })

    # Search as-built codebase (limited, CONTAINS query)
    if len(matches) < 20:
        try:
            with ctx.session() as s:
                result = s.run(
                    "MATCH (n) WHERE "
                    "toLower(n.qualified_name) CONTAINS toLower($name) "
                    "OR toLower(n.name) CONTAINS toLower($name) "
                    "RETURN n.qualified_name AS qn, n.name AS name, "
                    "labels(n) AS labels "
                    "LIMIT $limit",
                    {"name": name, "limit": 20 - len(matches)},
                )
                for record in result:
                    qn = record.get("qn", "") or ""
                    if qn in seen:
                        continue
                    seen.add(qn)
                    labels = record.get("labels", [])
                    kind = labels[0] if labels else ""
                    matches.append({
                        "qualified_name": qn,
                        "name": record.get("name", "") or "",
                        "kind": kind,
                        "source": "codegraph",
                    })
        except Exception as exc:
            log.warning("check_class_name: Neo4j search for '%s' failed: %s", name, exc)

    log.info(
        "check_class_name('%s'): %d matches (context=%d, draft=%d, codegraph=%d)",
        name, len(matches),
        sum(1 for m in matches if m.get("source") == "context"),
        sum(1 for m in matches if m.get("source") == "design_draft"),
        sum(1 for m in matches if m.get("source") == "codegraph"),
    )
    return json.dumps({
        "found": len(matches) > 0,
        "matches": matches,
        "hint": (
            "Use import_compound with a qualified_name to load "
            "the match into the context graph so it becomes a "
            "valid reference target."
        ) if matches else None,
    })


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════

def register_all(dispatcher: DesignToolDispatcher) -> None:
    """Register all design tools on a :class:`DesignToolDispatcher`."""
    disp = dispatcher
    disp.register(
        "validate_design", VALIDATE_DESIGN_SCHEMA,
        lambda inp: handle_validate_design(disp, inp),
    )
    disp.register(
        "import_compound", IMPORT_COMPOUND_SCHEMA,
        lambda inp: handle_import_compound(disp, inp),
    )
    disp.register(
        "check_class_name", CHECK_CLASS_NAME_SCHEMA,
        lambda inp: handle_check_class_name(disp, inp),
    )
    disp.register(
        "produce_oo_design", PRODUCE_OO_DESIGN_SCHEMA,
        lambda inp: handle_produce_oo_design(disp, inp),
    )
