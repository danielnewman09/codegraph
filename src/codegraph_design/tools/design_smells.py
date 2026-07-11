"""Design-smell detection tools — structural validation for OO design graphs.

Each smell has a severity level:
- ``blocking`` — invalid design that must be fixed before persistence
- ``warning``  — potential issue that should be reviewed
- ``info``     — informational metric or observation

The ``check_design_smells`` tool is registered on
:class:`~codegraph_design.tools.dispatcher.DesignToolDispatcher` and is
available during the design agent loop (before ``produce_oo_design``).
It can also be called standalone through the bridge.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import DesignToolDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Smell severity levels
# ══════════════════════════════════════════════════════════════════════════

class Severity:
    """Canonical severity levels for design smells."""
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"

    _ORDER = {BLOCKING: 0, WARNING: 1, INFO: 2}

    @classmethod
    def sort_key(cls, severity: str) -> int:
        return cls._ORDER.get(severity, 99)


# ══════════════════════════════════════════════════════════════════════════
# Smell result dataclass
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class DesignSmell:
    """A single detected design smell."""

    smell_id: str
    """Unique identifier for this smell type, e.g. ``orphaned_enum``."""

    severity: str
    """One of ``blocking``, ``warning``, ``info``."""

    element: str
    """Qualified name of the offending element."""

    kind: str
    """Node kind (e.g. ``EnumNode``, ``EnumValueNode``, ``ClassNode``)."""

    detail: str
    """Human-readable description of the smell."""

    recommendation: str = ""
    """Suggested fix."""


@dataclass
class DesignSmellReport:
    """Full report from ``check_design_smells``."""

    valid: bool
    """True if there are no blocking smells."""

    summary: dict = field(default_factory=dict)
    """Counts per severity level."""

    smells: list[DesignSmell] = field(default_factory=list)
    """All detected smells, ordered by severity (blocking first)."""


# ══════════════════════════════════════════════════════════════════════════
# Individual smell checkers
# ══════════════════════════════════════════════════════════════════════════


def _check_orphaned_enums(nodes: list[dict]) -> list[DesignSmell]:
    """Check for EnumNodes that have no EnumValueNode children via COMPOSES.

    An enum without any values is a structural defect — it cannot
    represent any meaningful type and will cause null-pointer issues
    in generated code or invalid assertions in tests.
    """
    smells: list[DesignSmell] = []

    # Build lookup: EnumNode qualified_name → set of child EnumValueNode qnames
    enum_values: dict[str, set[str]] = {}
    enum_nodes: dict[str, dict] = {}

    for node in nodes:
        ntype = node.get("type", "")
        qn = node.get("qualified_name", "")

        if ntype == "EnumNode" and qn:
            enum_nodes[qn] = node
            enum_values.setdefault(qn, set())

        elif ntype == "EnumValueNode" and qn:
            # Find parent via edges (COMPOSES from EnumNode to EnumValueNode)
            pass

    # Walk COMPOSES edges: EnumNode → EnumValueNode
    for node in nodes:
        ntype = node.get("type", "")
        if ntype != "EnumNode":
            continue
        parent_qn = node.get("qualified_name", "")
        for edge in node.get("edges", []):
            if edge.get("relation_type") != "COMPOSES":
                continue
            target_type = edge.get("target_type", "")
            target_uid = edge.get("target_uid", "")
            if target_type == "EnumValueNode" and target_uid:
                enum_values.setdefault(parent_qn, set()).add(target_uid)

    # Also walk composes (nested children)
    def _walk_composes(n: dict, parent_qn: str) -> None:
        for child in n.get("composes", []):
            child_type = child.get("type", "")
            child_qn = child.get("qualified_name", "")
            if child_type == "EnumValueNode" and child_qn:
                enum_values.setdefault(parent_qn, set()).add(child_qn)
            _walk_composes(child, parent_qn)

    for node in nodes:
        if node.get("type") == "EnumNode":
            _walk_composes(node, node.get("qualified_name", ""))

    for qn, node in enum_nodes.items():
        if not enum_values.get(qn):
            smells.append(DesignSmell(
                smell_id="orphaned_enum",
                severity=Severity.BLOCKING,
                element=qn,
                kind="EnumNode",
                detail=f"Enum '{qn}' has no EnumValueNode children — it defines no values",
                recommendation=(
                    "Add at least one EnumValueNode child via a COMPOSES edge "
                    "or a composes nested child.  An enum with zero values is "
                    "structurally invalid."
                ),
            ))

    return smells


def _check_orphaned_enumvalues(nodes: list[dict]) -> list[DesignSmell]:
    """Check for EnumValueNodes that are not children of any EnumNode.

    An EnumValue without a parent Enum is dangling — it cannot be
    referenced by any type and is unreachable from the design surface.
    """
    smells: list[DesignSmell] = []

    # Collect all EnumValueNode qnames and all EnumValueNode qnames
    # reachable from an EnumNode via COMPOSES or composes.
    all_enumvalues: set[str] = set()
    owned_enumvalues: set[str] = set()

    for node in nodes:
        ntype = node.get("type", "")
        qn = node.get("qualified_name", "")
        if ntype == "EnumValueNode" and qn:
            all_enumvalues.add(qn)

        if ntype == "EnumNode":
            for edge in node.get("edges", []):
                if (edge.get("relation_type") == "COMPOSES"
                        and edge.get("target_type") == "EnumValueNode"):
                    target_uid = edge.get("target_uid", "")
                    if target_uid:
                        owned_enumvalues.add(target_uid)

            def _walk_nested(n: dict) -> None:
                for child in n.get("composes", []):
                    child_type = child.get("type", "")
                    child_qn = child.get("qualified_name", "")
                    if child_type == "EnumValueNode" and child_qn:
                        owned_enumvalues.add(child_qn)
                    _walk_nested(child)

            _walk_nested(node)

    orphaned = all_enumvalues - owned_enumvalues
    for qn in sorted(orphaned):
        smells.append(DesignSmell(
            smell_id="orphaned_enumvalue",
            severity=Severity.BLOCKING,
            element=qn,
            kind="EnumValueNode",
            detail=f"EnumValue '{qn}' is not a child of any EnumNode",
            recommendation=(
                "Add a COMPOSES edge from the parent EnumNode to this "
                "EnumValueNode, or nest it under the EnumNode's composes list."
            ),
        ))

    return smells


# ══════════════════════════════════════════════════════════════════════════
# Checker registry
# ══════════════════════════════════════════════════════════════════════════

_CHECKERS: list = [
    _check_orphaned_enums,
    _check_orphaned_enumvalues,
]


# ══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════


def check_design_smells(nodes: list[dict]) -> DesignSmellReport:
    """Run all design-smell checkers against a draft OO design.

    Args:
        nodes: A list of CodeGraphNode dicts in LayerGraph format
            (the same format produced by the design agent).

    Returns:
        A :class:`DesignSmellReport` with validity, summary counts, and
        a sorted list of smells (blocking first).
    """
    all_smells: list[DesignSmell] = []

    for checker in _CHECKERS:
        try:
            smells = checker(nodes)
            all_smells.extend(smells)
        except Exception as exc:
            log.warning("Smell checker %s failed: %s", checker.__name__, exc)

    # Sort by severity (blocking first)
    all_smells.sort(key=lambda s: Severity.sort_key(s.severity))

    summary = {
        "blocking": sum(1 for s in all_smells if s.severity == Severity.BLOCKING),
        "warning": sum(1 for s in all_smells if s.severity == Severity.WARNING),
        "info": sum(1 for s in all_smells if s.severity == Severity.INFO),
        "total": len(all_smells),
    }

    return DesignSmellReport(
        valid=(summary["blocking"] == 0),
        summary=summary,
        smells=all_smells,
    )


# ══════════════════════════════════════════════════════════════════════════
# Neo4j-based checker (standalone, queries the graph directly)
# ══════════════════════════════════════════════════════════════════════════


def check_design_smells_neo4j(tag: str = "design") -> DesignSmellReport:
    """Run design-smell checkers against Neo4j directly.

    Queries the graph for design-layer nodes (by tag) and checks for
    structural smells.  Used by the bridge's standalone smell-checking
    endpoint and by the design-pipeline post-design validation.

    Args:
        tag: Provenance tag to filter by (default ``"design"``).

    Returns:
        A :class:`DesignSmellReport`.
    """
    from neomodel import db

    all_smells: list[DesignSmell] = []

    # ── Orphaned enums: EnumNodes with no EnumValueNode children ───────
    try:
        results, _ = db.cypher_query(
            """
            MATCH (e:Enum)
            WHERE $tag IN e.tags
            OPTIONAL MATCH (e)-[:COMPOSES]->(v:EnumValue)
            WHERE $tag IN v.tags
            WITH e, collect(v) AS values
            WHERE size(values) = 0
            RETURN e.qualified_name AS qn, e.name AS name
            ORDER BY qn
            """,
            {"tag": tag},
        )
        for row in results:
            qn, name = row[0], row[1]
            all_smells.append(DesignSmell(
                smell_id="orphaned_enum",
                severity=Severity.BLOCKING,
                element=qn or name or "?",
                kind="EnumNode",
                detail=f"Enum '{qn or name}' has no EnumValueNode children",
                recommendation="Add at least one EnumValueNode via COMPOSES edge",
            ))
    except Exception as exc:
        log.warning("Neo4j orphaned-enum check failed: %s", exc)

    # ── Orphaned enumvalues: EnumValueNodes with no EnumNode parent ────
    try:
        results, _ = db.cypher_query(
            """
            MATCH (v:EnumValue)
            WHERE $tag IN v.tags
            OPTIONAL MATCH (e:Enum)-[:COMPOSES]->(v)
            WHERE $tag IN e.tags
            WITH v, e
            WHERE e IS NULL
            RETURN v.qualified_name AS qn, v.name AS name
            ORDER BY qn
            """,
            {"tag": tag},
        )
        for row in results:
            qn, name = row[0], row[1]
            all_smells.append(DesignSmell(
                smell_id="orphaned_enumvalue",
                severity=Severity.BLOCKING,
                element=qn or name or "?",
                kind="EnumValueNode",
                detail=f"EnumValue '{qn or name}' has no parent EnumNode",
                recommendation="Add a COMPOSES edge from the parent EnumNode to this EnumValueNode",
            ))
    except Exception as exc:
        log.warning("Neo4j orphaned-enumvalue check failed: %s", exc)

    all_smells.sort(key=lambda s: Severity.sort_key(s.severity))

    summary = {
        "blocking": sum(1 for s in all_smells if s.severity == Severity.BLOCKING),
        "warning": sum(1 for s in all_smells if s.severity == Severity.WARNING),
        "info": sum(1 for s in all_smells if s.severity == Severity.INFO),
        "total": len(all_smells),
    }

    return DesignSmellReport(
        valid=(summary["blocking"] == 0),
        summary=summary,
        smells=all_smells,
    )


# ══════════════════════════════════════════════════════════════════════════
# Tool schema
# ══════════════════════════════════════════════════════════════════════════

CHECK_DESIGN_SMELLS_SCHEMA = {
    "name": "check_design_smells",
    "description": (
        "Validate a draft OO design for structural smells and defects. "
        "Checks include: enum nodes without enumvalues (blocking), "
        "enumvalues without a parent enum (blocking). "
        "Returns a report with validity, severity-level summary, and "
        "a sorted list of smells (blocking → warning → info). "
        "Use this to check your work before calling produce_oo_design."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "minItems": 1,
                "description": (
                    "A list of CodeGraphNode dicts in the LayerGraph serialization format. "
                    "Each node has a 'type' discriminator and optional 'edges' and 'composes' arrays."
                ),
            },
        },
        "required": ["nodes"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Handler
# ══════════════════════════════════════════════════════════════════════════


def handle_check_design_smells(
    ctx: DesignToolDispatcher,
    tool_input: dict,
) -> str:
    """Handle the ``check_design_smells`` tool call.

    Validates the draft design on the dispatcher's ``design_draft``
    (preferred, if available) or the provided ``nodes`` list.
    """
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes and ctx.design_draft:
        nodes = ctx.design_draft

    if not nodes:
        return json.dumps({
            "valid": False,
            "summary": {"blocking": 1, "warning": 0, "info": 0, "total": 1},
            "smells": [{
                "smell_id": "no_input",
                "severity": "blocking",
                "element": "",
                "kind": "",
                "detail": "No design nodes provided and no draft available",
                "recommendation": "Provide a nodes array or call produce_oo_design first",
            }],
        })

    report = check_design_smells(nodes)

    return json.dumps({
        "valid": report.valid,
        "summary": report.summary,
        "smells": [
            {
                "smell_id": s.smell_id,
                "severity": s.severity,
                "element": s.element,
                "kind": s.kind,
                "detail": s.detail,
                "recommendation": s.recommendation,
            }
            for s in report.smells
        ],
    })


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════


def register_all(dispatcher: DesignToolDispatcher) -> None:
    """Register the design-smells tool on a :class:`DesignToolDispatcher`."""
    dispatcher.register(
        "check_design_smells",
        CHECK_DESIGN_SMELLS_SCHEMA,
        lambda inp: handle_check_design_smells(dispatcher, inp),
    )
