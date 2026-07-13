"""Design-smell detection — declarative plugin-style registration.

Each smell checker is a function decorated with ``@register_smell``.
The orchestrator discovers all checkers automatically.  Adding a new
smell requires exactly one step: write the function and decorate it.

No raw Cypher — all checks operate on in-memory ``list[dict]``
(LayerGraph serialization format).  The Neo4j-based variant
(``check_design_smells_neo4j``) has been removed; bridge callers can
load design nodes from the graph then call ``run_all_smells``.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from codegraph_design.tools.dispatcher import DesignToolDispatcher

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Severity
# ══════════════════════════════════════════════════════════════════════════

class Severity:
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"

    _ORDER = {BLOCKING: 0, WARNING: 1, INFO: 2}

    @classmethod
    def sort_key(cls, severity: str) -> int:
        return cls._ORDER.get(severity, 99)


# ══════════════════════════════════════════════════════════════════════════
# Report types
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Smell:
    """A single detected design smell."""

    id: str            # e.g. "orphaned_enum"
    severity: str      # blocking | warning | info
    element: str       # qualified_name of the offending node
    kind: str          # node type discriminator
    detail: str        # human-readable description
    recommendation: str = ""


@dataclass
class SmellReport:
    valid: bool
    summary: dict = field(default_factory=dict)
    smells: list[Smell] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════════════

SmellChecker = Callable[[list[dict]], list[Smell]]

_registry: list[SmellChecker] = []
"""All registered smell checkers, in registration order."""


def register_smell(
    smell_id: str,
    severity: str,
    description: str,
) -> Callable[[SmellChecker], SmellChecker]:
    """Decorator: register a smell-checker function.

    The checker receives ``nodes: list[dict]`` (LayerGraph dicts) and
    returns a ``list[Smell]``.  Every ``Smell`` produced MUST use the
    declared ``smell_id`` and ``severity``.
    """

    def decorator(fn: SmellChecker) -> SmellChecker:
        fn._smell_id = smell_id          # type: ignore[attr-defined]
        fn._severity = severity          # type: ignore[attr-defined]
        fn._description = description    # type: ignore[attr-defined]
        _registry.append(fn)
        return fn

    return decorator


def _checker_summary() -> str:
    """Human-readable summary of registered checkers for tool descriptions."""
    parts = []
    for c in _registry:
        cid = getattr(c, "_smell_id", "?")
        csev = getattr(c, "_severity", "?")
        parts.append(f"{cid}({csev})")
    return ", ".join(parts) if parts else "(none)"


def _walk_tree(nodes: list[dict]) -> list[dict]:
    """Walk a node tree recursively, returning all nodes at all levels.

    Walks into ``composes`` of every node (NamespaceNode, ClassNode,
    EnumNode, etc.) so checkers can inspect deeply nested compounds.
    """
    out: list[dict] = []
    for node in nodes:
        out.append(node)
        out.extend(_walk_tree(node.get("composes", [])))
    return out


# ══════════════════════════════════════════════════════════════════════════
# Built-in checkers
# ══════════════════════════════════════════════════════════════════════════


@register_smell(
    "orphaned_enum", Severity.BLOCKING,
    "Enum has no EnumValue children — structurally invalid",
)
def _check_orphaned_enums(nodes: list[dict]) -> list[Smell]:
    """EnumNodes with zero EnumValueNode children."""
    owned: dict[str, set[str]] = {}

    def _collect(n: dict, enum_qn: str) -> None:
        for child in n.get("composes", []):
            if child.get("type") == "EnumValueNode":
                qn = child.get("qualified_name", "")
                if qn:
                    owned.setdefault(enum_qn, set()).add(qn)
            _collect(child, enum_qn)

    for node in _walk_tree(nodes):
        if node.get("type") == "EnumNode":
            qn = node.get("qualified_name", "")
            owned.setdefault(qn, set())
            _collect(node, qn)

    return [
        Smell(
            id="orphaned_enum",
            severity=Severity.BLOCKING,
            element=qn,
            kind="EnumNode",
            detail=f"Enum '{qn}' has no values",
            recommendation="Add at least one EnumValueNode child",
        )
        for qn, vals in owned.items()
        if not vals
    ]


@register_smell(
    "orphaned_enumvalue", Severity.BLOCKING,
    "EnumValue has no parent EnumNode",
)
def _check_orphaned_enumvalues(nodes: list[dict]) -> list[Smell]:
    """EnumValueNodes not nested under any EnumNode."""
    all_vals: set[str] = set()
    owned: set[str] = set()

    for node in _walk_tree(nodes):
        ntype = node.get("type", "")
        qn = node.get("qualified_name", "")
        if ntype == "EnumValueNode" and qn:
            all_vals.add(qn)

        if ntype == "EnumNode":

            def _walk(n: dict) -> None:
                for child in n.get("composes", []):
                    if child.get("type") == "EnumValueNode":
                        child_qn = child.get("qualified_name", "")
                        if child_qn:
                            owned.add(child_qn)
                    _walk(child)

            _walk(node)

    return [
        Smell(
            id="orphaned_enumvalue",
            severity=Severity.BLOCKING,
            element=qn,
            kind="EnumValueNode",
            detail=f"EnumValue '{qn}' has no parent EnumNode",
            recommendation="Nest under the parent EnumNode's composes list",
        )
        for qn in sorted(all_vals - owned)
    ]


@register_smell(
    "orphaned_node", Severity.BLOCKING,
    "Design node not nested under any NamespaceNode",
)
def _check_orphaned_nodes(nodes: list[dict]) -> list[Smell]:
    """Non-namespace nodes not nested under a NamespaceNode.

    Collects all NamespaceNode qualified_names, then flags any
    non-namespace node whose qualified_name doesn't start with
    a known namespace prefix + '::'.

    An empty design (no nodes at all) is trivially valid.
    """
    if not nodes:
        return []

    namespace_qns: set[str] = set()
    non_namespace_data: list[tuple[str, str]] = []

    for node in nodes:
        ntype = node.get("type", "")
        qn = node.get("qualified_name", "")
        if not qn:
            continue
        if ntype == "NamespaceNode":
            namespace_qns.add(qn)
        else:
            non_namespace_data.append((qn, ntype))

    if not namespace_qns:
        return [
            Smell(
                id="orphaned_node",
                severity=Severity.BLOCKING,
                element="(root)",
                kind="",
                detail="Design has no NamespaceNode — every node must be "
                       "composed into a namespace",
                recommendation="Add a namespace node and nest all design "
                               "nodes under it via qualified_name prefix",
            )
        ]

    smells: list[Smell] = []
    for qn, ntype in non_namespace_data:
        if "::" not in qn:
            smells.append(Smell(
                id="orphaned_node",
                severity=Severity.BLOCKING,
                element=qn,
                kind=ntype,
                detail=f"'{qn}' has no namespace prefix",
                recommendation="Use a qualified name like "
                               f"Namespace::{qn}",
            ))
            continue
        root_ns = qn.split("::", 1)[0]
        if root_ns not in namespace_qns:
            smells.append(Smell(
                id="orphaned_node",
                severity=Severity.BLOCKING,
                element=qn,
                kind=ntype,
                detail=f"Namespace '{root_ns}' not in design "
                       f"(known: {sorted(namespace_qns)})",
                recommendation=f"Add a NamespaceNode for '{root_ns}' or "
                               "correct the qualified_name prefix",
            ))
    return smells


@register_smell(
    "duplicate_qname", Severity.BLOCKING,
    "Two or more design nodes share the same qualified_name",
)
def _check_duplicate_names(nodes: list[dict]) -> list[Smell]:
    """Duplicate qualified_name across all design nodes at any level."""
    names = [
        n.get("qualified_name", "")
        for n in _walk_tree(nodes)
        if n.get("qualified_name")
    ]
    return [
        Smell(
            id="duplicate_qname",
            severity=Severity.BLOCKING,
            element=qn,
            kind="",
            detail=f"Duplicate qualified_name '{qn}' appears {cnt} times",
            recommendation="Every design node must have a unique qualified_name",
        )
        for qn, cnt in Counter(names).items()
        if cnt > 1
    ]


@register_smell(
    "missing_namespace", Severity.BLOCKING,
    "Root design compounds (class, enum, interface) have no parent NamespaceNode",
)
def _check_missing_namespace(nodes: list[dict]) -> list[Smell]:
    """Design has compound nodes but no NamespaceNode to group them under.

    Every design must include at least one NamespaceNode that wraps its
    top-level compounds.  Without it, the design graph is unrooted and
    namespace-filtered exports (Markdown / PlantUML) won't work.
    """
    has_namespace = False
    has_compound = False

    for node in _walk_tree(nodes):
        ntype = node.get("type", "")
        if ntype == "NamespaceNode":
            has_namespace = True
        if ntype in ("ClassNode", "InterfaceNode", "EnumNode", "StructNode"):
            has_compound = True

    if has_compound and not has_namespace:
        return [Smell(
            id="missing_namespace",
            severity=Severity.BLOCKING,
            element="",
            kind="NamespaceNode",
            detail=(
                "Design contains compound nodes (ClassNode / EnumNode / "
                "InterfaceNode) but no NamespaceNode.  Every design must "
                "have a NamespaceNode that composes its top-level compounds."
            ),
            recommendation=(
                "Add a NamespaceNode to the design whose qualified_name "
                "is the namespace prefix shared by all compounds "
                "(e.g., 'cpp_sqlite'), and nest all compounds under it "
                "via composes."
            ),
        )]
    return []


@register_smell(
    "unscoped_qname", Severity.BLOCKING,
    "Compound's qualified_name has no namespace prefix (no '::' separator)",
)
def _check_unscoped_qnames(nodes: list[dict]) -> list[Smell]:
    """Compounds whose qualified_name is just a bare name (no namespace).

    Every compound must live in a namespace.  A qualified_name like
    ``Migration`` is invalid; it should be ``cpp_sqlite::Migration``.
    """
    compound_types = {"ClassNode", "InterfaceNode", "EnumNode", "StructNode"}
    smells: list[Smell] = []

    for node in _walk_tree(nodes):
        ntype = node.get("type", "")
        if ntype not in compound_types:
            continue
        qn = node.get("qualified_name", "")
        if not qn:
            smells.append(Smell(
                id="unscoped_qname",
                severity=Severity.BLOCKING,
                element="(missing qualified_name)",
                kind=ntype,
                detail=f"{ntype} has no qualified_name at all",
                recommendation="Assign a scoped qualified_name like 'ns::ClassName'",
            ))
        elif "::" not in qn:
            smells.append(Smell(
                id="unscoped_qname",
                severity=Severity.BLOCKING,
                element=qn,
                kind=ntype,
                detail=f"{ntype} '{qn}' is not scoped to a namespace",
                recommendation=(
                    f"Add a namespace prefix, e.g. 'mycomponent::{qn}'"
                ),
            ))

    return smells


# ══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════

def run_all_smells(nodes: list[dict]) -> SmellReport:
    """Run every registered smell checker against a design draft.

    Each checker receives the original ``nodes`` list.  Checkers that
    need to inspect compounds at all nesting levels (including children
    of NamespaceNodes) should use :func:`_walk_tree`.

    Args:
        nodes: CodeGraphNode dicts in LayerGraph serialization format.

    Returns:
        A :class:`SmellReport` with validity, summary counts, and a
        sorted list of smells (blocking first).
    """
    all_smells: list[Smell] = []

    for checker in _registry:
        smell_id = getattr(checker, "_smell_id", "internal_error")
        try:
            all_smells.extend(checker(nodes))
        except Exception as exc:
            log.warning("Smell checker '%s' crashed: %s", smell_id, exc)
            all_smells.append(Smell(
                id=smell_id,
                severity=Severity.BLOCKING,
                element="",
                kind="",
                detail=f"Smell checker '{smell_id}' raised: {exc}",
                recommendation="Report this internal error",
            ))

    all_smells.sort(key=lambda s: Severity.sort_key(s.severity))

    summary = {
        sev: sum(1 for s in all_smells if s.severity == sev)
        for sev in ("blocking", "warning", "info")
    }
    summary["total"] = len(all_smells)

    return SmellReport(
        valid=(summary["blocking"] == 0),
        summary=summary,
        smells=all_smells,
    )


# ══════════════════════════════════════════════════════════════════════════
# Tool schema & handler
# ══════════════════════════════════════════════════════════════════════════

CHECK_DESIGN_SMELLS_SCHEMA = {
    "name": "check_design_smells",
    "description": (
        "Validate a draft OO design for structural defects. "
        f"Checks: {_checker_summary()}. "
        "Returns validity (no blocking smells = true), severity-level "
        "summary, and a sorted list of smells with recommendations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "minItems": 1,
                "description": (
                    "CodeGraphNode dicts in LayerGraph serialization format. "
                    "Each node has a 'type' discriminator and optional "
                    "'composes' and 'edges' arrays."
                ),
            },
        },
        "required": ["nodes"],
    },
}


def handle_check_design_smells(
    ctx: DesignToolDispatcher,
    tool_input: dict,
) -> str:
    """Handle ``check_design_smells`` — validate the draft design."""
    nodes: list[dict] = tool_input.get("nodes", [])
    if not nodes and ctx.design_draft:
        nodes = ctx.design_draft

    if not nodes:
        return json.dumps({
            "valid": False,
            "summary": {"blocking": 1, "warning": 0, "info": 0, "total": 1},
            "smells": [{
                "id": "no_input",
                "severity": "blocking",
                "element": "",
                "kind": "",
                "detail": "No design nodes provided",
                "recommendation": "Provide nodes or call produce_oo_design first",
            }],
        })

    report = run_all_smells(nodes)

    return json.dumps({
        "valid": report.valid,
        "summary": report.summary,
        "smells": [
            {
                "id": s.id,
                "severity": s.severity,
                "element": s.element,
                "kind": s.kind,
                "detail": s.detail,
                "recommendation": s.recommendation,
            }
            for s in report.smells
        ],
    })


def register_all(dispatcher: DesignToolDispatcher) -> None:
    """Register the design-smells tool on a :class:`DesignToolDispatcher`."""
    dispatcher.register(
        "check_design_smells",
        CHECK_DESIGN_SMELLS_SCHEMA,
        lambda inp: handle_check_design_smells(dispatcher, inp),
    )
