"""Shared class-scoped verification scope: which requirements and tests
pertain to a given class.

Single source of truth for the requirement → test mapping so the
explorer and any future exporter always agree:

- :mod:`codegraph.explorer.api` — the web explorer's requirements &
  tests panel and its tree badges.

A test *pertains* to the scoped class when any of its edges — or the
edges of its composed steps/assertions — targets the class or one of
its members.  Three link shapes are recognised (see module docstring
of :mod:`codegraph.models.test`):

- ``VERIFIES`` — TestNode → ClassNode | MethodNode | LLR;
- ``CALLEE`` — TestStepNode → MethodNode | ClassNode;
- ``LEFT_OPERAND`` / ``RIGHT_OPERAND`` — AssertionNode →
  AttributeNode | LiteralNode (the only link present in some fixtures).

The assertion-rendering helpers (:func:`truncate`,
:func:`render_condition`) live here because they narrate the same
scope: an assertion's condition string is how the panel shows *what* a
pertaining test checks.

Provenance: this module was re-authored on 2026-09-25.  The previous
``codegraph.export.verification``/``codegraph.export.coverage`` pair
was never committed to git; ``codegraph.explorer.api`` had imported it
since the explorer's first commit, leaving the package unimportable.
The scope logic and condition rendering were rebuilt from the
explorer's JSON contract (``tests/integration/explorer``); the Mermaid
coverage-Markdown exporter that also lived there was deliberately not
restored — nothing imported it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.graph import CompositeEntry, LayerGraph

__all__ = [
    "VerificationScope",
    "compute_verification_scope",
    "render_condition",
    "truncate",
]

#: Edges that express structure, not verification.  A test's COMPOSES
#: children and its DEFINED_IN file are never evidence that it targets
#: the scoped class.
_STRUCTURAL_RELATIONS = ("COMPOSES", "DEFINED_IN")


@dataclass
class VerificationScope:
    """The requirements and tests that pertain to a scoped class.

    Attributes:
        reqs: Qualified names of requirement nodes (LLR and HLR) that
            own at least one pertaining test.
        tests: Qualified names of the pertaining TestNodes.
        links: ``(test_qname, class_qname)`` pairs — every test → class
            verification link, for arrow emission.
        parents: child qname → parent qname map of the whole graph
            (COMPOSES ancestry), used to walk test → LLR → HLR.
    """

    reqs: set[str] = field(default_factory=set)
    tests: set[str] = field(default_factory=set)
    links: list[tuple[str, str]] = field(default_factory=list)
    parents: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Text helpers (tree badges / Markdown table cells)
# ----------------------------------------------------------------------


def truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* characters with an ellipsis.

    Newlines collapse to spaces first so the result is safe inside a
    single Markdown table cell or tree badge.
    """
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _operand_display(graph: LayerGraph, target_key: str) -> str:
    """Short display for an assertion operand: attribute/method short
    name, or literal value.
    """
    flat = graph._flat_index()
    entry = flat.get(target_key)
    if entry is not None:
        node = entry.node
        qn = getattr(node, "qualified_name", "") or ""
        name = getattr(node, "name", "") or ""
        if type(node).__name__ == "LiteralNode":
            return name or qn
        if "::" in qn:
            return qn.rsplit("::", 1)[-1]
        return qn or name
    display = graph.resolve_target_name(target_key, flat=flat)
    return display.rsplit("::", 1)[-1]


def render_condition(graph: LayerGraph, assertion_entry: CompositeEntry) -> str:
    """Render an assertion as a condition string.

    Design-pipeline assertions carry LEFT/RIGHT_OPERAND edges — render
    ``registered_versions == 3`` from operands + operator.  As-built
    assertions carry neither: their ``description`` holds the condition
    source (e.g. ``ASSERT_NO_THROW(createDB(true););``) — use it.
    """
    operands: dict[str, str] = {}
    for rel_type, target_key, _target_type in assertion_entry.references:
        if rel_type == "LEFT_OPERAND":
            operands["left"] = _operand_display(graph, target_key)
        elif rel_type == "RIGHT_OPERAND":
            operands["right"] = _operand_display(graph, target_key)

    op = getattr(assertion_entry.node, "operator", "") or "=="
    left = operands.get("left", "")
    right = operands.get("right", "")

    if not left and not right:
        # No operands to compose from — the description *is* the source
        # condition; fall back to the bare operator when it is empty too.
        desc = getattr(assertion_entry.node, "description", "") or ""
        return desc or op

    if op == "is_true":
        return f"{left} is true"
    if op == "is_false":
        return f"{left} is false"
    if op in ("equals", "eq"):
        return f"{left} == {right}"
    return f"{left} {op} {right}"


# ----------------------------------------------------------------------
# Verification scope
# ----------------------------------------------------------------------


def _owning_class_qname(target_qname: str) -> str:
    """Return the qualified name of the class owning a member target
    (the target's immediate parent in the qname).
    """
    if "::" not in target_qname:
        return ""
    return target_qname.rsplit("::", 1)[0]


def _build_parent_map(graph: LayerGraph) -> dict[str, str]:
    """Return child qname → parent qname for the whole graph."""
    parents: dict[str, str] = {}

    def walk(entry: CompositeEntry) -> None:
        parent_qname = (
            getattr(entry.node, "qualified_name", None) or entry.node.name
        )
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                walk(child_entry)
                cq = (
                    getattr(child_entry.node, "qualified_name", None)
                    or child_entry.node.name
                )
                if not cq:
                    continue
                parents[cq] = parent_qname

    for entry in graph.entries.values():
        walk(entry)
    return parents


def _targets_scope_class(
    target_qname: str, scope_class: str, allowed_classes: set[str]
) -> bool:
    """True when *target_qname* refers to the scoped class itself or to
    one of its members.

    Two matching rules, because design graphs may store member targets
    under either the fully-qualified class name
    (``cpp_sqlite::MigrationManager::is_initialized``) or a
    namespace-less orphan stub (``MigrationManager::error_state``):

    1. the target IS an allowed class, or its owner qname is;
    2. the owner's last segment equals the scoped class's short name
       (catches orphaned verification stubs whose qname lost the
       namespace prefix).
    """
    if target_qname in allowed_classes:
        return True
    owner = _owning_class_qname(target_qname)
    if owner in allowed_classes:
        return True
    scope_short = scope_class.rsplit("::", 1)[-1]
    return bool(owner and owner.rsplit("::", 1)[-1] == scope_short)


def _test_pertains_to_scope(
    graph: LayerGraph,
    test_entry: CompositeEntry,
    scope_class: str,
    allowed_classes: set[str],
) -> bool:
    """True when *test_entry* exercises the scoped class: any of its own
    edges or the edges of its composed steps/assertions (VERIFIES,
    CALLEE, LEFT_OPERAND, RIGHT_OPERAND) target the class or a member.
    """
    flat = graph._flat_index()

    # The test itself plus every composed step/assertion — pertains is
    # an OR over all of their outgoing references.
    candidates = [test_entry]
    for type_children in test_entry.children.values():
        candidates.extend(type_children.values())

    for entry in candidates:
        for rel_type, target_key, _target_type in entry.references:
            if rel_type in _STRUCTURAL_RELATIONS:
                continue
            display = graph.resolve_target_name(target_key, flat=flat)
            if not display:
                continue
            if _targets_scope_class(display, scope_class, allowed_classes):
                return True
    return False


def compute_verification_scope(
    graph: LayerGraph, scope_class: str, allowed_classes: set[str]
) -> VerificationScope:
    """Collect the requirements (LLR/HLR) and tests pertaining to a
    scoped class.

    A test pertains to the scope when it (or its composed steps /
    assertions) references the class or any of its members.  The test's
    COMPOSES ancestry (test → LLR → HLR) is walked to collect the
    requirement nodes.  Every test → class link is recorded in
    :attr:`VerificationScope.links`.
    """
    scope = VerificationScope(parents=_build_parent_map(graph))

    tests = [
        entry
        for entry in graph._all_entries()
        if type(entry.node).__name__ == "TestNode"
    ]

    for test_entry in tests:
        if not _test_pertains_to_scope(
            graph, test_entry, scope_class, allowed_classes
        ):
            continue
        test_qname = (
            getattr(test_entry.node, "qualified_name", None)
            or test_entry.node.name
        )
        scope.tests.add(test_qname)
        scope.links.append((test_qname, scope_class))
        # Walk test → LLR → HLR so both requirement tiers surface.
        req_qname = scope.parents.get(test_qname)
        while req_qname:
            scope.reqs.add(req_qname)
            req_qname = scope.parents.get(req_qname)

    return scope
