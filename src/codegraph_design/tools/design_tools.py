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


def _validate_oo_design(
    design: list[dict],
    *,
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> list[str]:
    """Validate a LayerGraph-format design (list of CodeGraphNode dicts).

    Checks:
    1. Unknown edge targets (not in any known lookup or the design itself)
    2. Missing intercomponent references
    3. Duplicate qualified names
    """
    errors: list[str] = []

    # Build union of all known qualified names
    known_qnames: set[str] = set()
    known_qnames.update(prior_class_lookup.values())
    known_qnames.update(dependency_lookup.values())
    for ic in intercomponent_classes:
        qn = ic.get("qualified_name", "")
        if qn:
            known_qnames.add(qn)

    known_bare: set[str] = set()
    known_bare.update(prior_class_lookup.keys())
    known_bare.update(dependency_lookup.keys())
    for ic in intercomponent_classes:
        bare = ic.get("name", "") or ic.get("qualified_name", "").rsplit("::", 1)[-1]
        if bare:
            known_bare.add(bare)

    design_qnames = _collect_qnames(design)

    # 1. Check edge targets
    for edge in _collect_edges(design):
        target = edge.get("target_uid", "")
        if not target:
            continue
        target_bare = target.rsplit("::", 1)[-1] if "::" in target else target
        if (
            target in design_qnames
            or target in known_qnames
            or target_bare in known_bare
            or target_bare in design_qnames
        ):
            continue
        errors.append(
            f"Edge target '{target}' not found in design context "
            f"(prior designs, dependency APIs, or intercomponent classes)"
        )

    # 2. Check intercomponent references
    for ic in intercomponent_classes:
        ic_qname = ic.get("qualified_name", "")
        ic_bare = ic.get("name", "") or ic_qname.rsplit("::", 1)[-1]
        ic_kind = ic.get("kind", "class")
        if ic_kind not in ("class", "interface"):
            continue

        found = False
        for edge in _collect_edges(design):
            target = edge.get("target_uid", "")
            if target == ic_qname or target == ic_bare:
                found = True
                break

        if not found:
            def _check_type_sig(n: dict) -> bool:
                ts = n.get("type_signature", "")
                if ts and (ic_qname in ts or ic_bare in ts):
                    return True
                for child in n.get("composes", []):
                    if _check_type_sig(child):
                        return True
                return False

            for node in design:
                if _check_type_sig(node):
                    found = True
                    break

        if not found:
            errors.append(
                f"Warning: no reference to intercomponent class "
                f"'{ic_qname}' — your design may have a missing dependency"
            )

    # 3. Check for duplicate qualified names
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
    """Validate a draft OO design against the dispatcher's lookups."""
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes:
        return json.dumps({"valid": False, "errors": ["No nodes provided"], "warnings": []})
    errors = _validate_oo_design(
        nodes,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dependency_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )

    critical = [e for e in errors if not e.startswith("Warning:")]
    warnings = [e.replace("Warning: ", "") for e in errors if e.startswith("Warning:")]

    return json.dumps({
        "valid": len(critical) == 0,
        "errors": critical,
        "warnings": warnings,
    })


def handle_produce_oo_design(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Store the final design on the dispatcher for verification tools."""
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes:
        return json.dumps({
            "stored": False,
            "errors": ["No nodes provided"],
        })

    errors = _validate_oo_design(
        nodes,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dependency_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )
    critical = [e for e in errors if not e.startswith("Warning:")]
    warnings = [e.replace("Warning: ", "") for e in errors if e.startswith("Warning:")]

    if critical:
        return json.dumps({
            "stored": False,
            "errors": critical,
            "warnings": warnings,
            "hint": "Fix errors and call produce_oo_design again.",
        })

    ctx.design_draft = nodes

    for node in nodes:
        qn = node.get("qualified_name", "")
        name = node.get("name", "")
        if qn and name:
            ctx.prior_class_lookup[name] = qn

    return json.dumps({
        "stored": True,
        "warnings": warnings,
        "hint": (
            "Design stored. Now resolve verification stubs using "
            "draft_verifications, then call "
            "commit_design_and_verifications to finish."
        ),
    })


def handle_check_class_name(ctx: DesignToolDispatcher, tool_input: dict) -> str:
    """Check if a class name exists in any of the dispatcher's lookups."""
    name = tool_input.get("name", "")
    if not name:
        return json.dumps({"found": False, "matches": []})

    matches: list[dict] = []
    name_lower = name.lower()

    for bare, qname in ctx.prior_class_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "name": bare,
                "kind": "class",
                "source": "prior_design",
            })

    for bare, qname in ctx.dependency_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "name": bare,
                "kind": "dependency",
                "source": "dependency",
            })

    for cls in ctx.intercomponent_classes:
        qname = cls.get("qualified_name", "")
        bare = qname.rsplit("::", 1)[-1] if qname else ""
        cls_name = cls.get("name", bare)
        if name_lower in cls_name.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "name": cls_name,
                "kind": cls.get("kind", "class"),
                "source": "intercomponent",
            })

    return json.dumps({
        "found": len(matches) > 0,
        "matches": matches,
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
        "check_class_name", CHECK_CLASS_NAME_SCHEMA,
        lambda inp: handle_check_class_name(disp, inp),
    )
    disp.register(
        "produce_oo_design", PRODUCE_OO_DESIGN_SCHEMA,
        lambda inp: handle_produce_oo_design(disp, inp),
    )
