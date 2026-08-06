"""Persistence layer for HLR decomposition results.

The decompose agent produces a flat list of codegraph node dicts —
the same format that ``LayerGraph.deserialize()`` consumes.  Scaffold
nodes (placeholder ClassNode/AttributeNode/LiteralNode with
``tags=["scaffold"]``) for edge targets that don't exist in the LLM
output are auto-created by ``LayerGraph.deserialize(create_missing=True)``
— a general codegraph feature.

All nodes (test nodes AND scaffold nodes) are persisted via
``create_or_update`` with ``merge_by`` on the node's unique property
(``uid`` for TestNode/AssertionNode/TestStepNode).  Scaffold nodes
with the same ``uid`` (deterministic hash of ``qualified_name``)
are upserted (shared across HLRs).

Verification nodes use codegraph's native TestNode / AssertionNode /
TestStepNode / TestFixtureNode types.  COMPOSES edges from
LLR → TestNode and TestNode → AssertionNode / TestStepNode are created
via raw Cypher MERGE.

Usage::

    from codegraph.backends import get_backend
    from codegraph_requirements.persistence import persist_decomposition

    decomposition = persist_decomposition(
        hlr_uid="2c3463b2…",
        decomposition=decomposed,
    )
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from codegraph.backends import get_backend
from codegraph.models.descriptors import PropertyRegistry

from codegraph_requirements.models.requirement import HLR, LLR
from codegraph_requirements.schemas import DecomposedRequirementSchema
from codegraph.persistence.repository import GraphRepository
from codegraph.models.test import TestNode, AssertionNode, TestStepNode, TestFixtureNode

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Result dataclass
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class DecompositionResult:
    """Summary of what persist_decomposition created in Neo4j."""

    llrs_created: int = 0
    tests_created: int = 0
    assertions_created: int = 0
    steps_created: int = 0
    fixtures_created: int = 0
    scaffold_classes: int = 0
    scaffold_attributes: int = 0
    operand_edges: int = 0
    scaffold_map: dict[str, dict] = field(default_factory=dict)
    """Maps each auto-created scaffold node's qualified_name to a dict of
    its type, uid, kind, and parent (for member nodes).  Populated by
    ``persist_decomposition`` so the caller (and the design agent) can see
    what scaffolding was created from notional references in verification
    stubs."""


# ══════════════════════════════════════════════════════════════════════════
# Persistence helpers
# ══════════════════════════════════════════════════════════════════════════


def _persist_node(node) -> object:
    """Persist a node, returning the saved instance.

    Delegates to ``node.save()`` which goes through the active backend.
    The backend handles MERGE/upsert, property introspection, and all
    storage-specific logic.
    """
    return node.save()


def _create_edge(source, target, edge_type: str) -> bool:
    """Create any edge between two saved nodes via the active backend."""
    try:
        get_backend().connect(source, edge_type, target)
        return True
    except Exception as exc:
        log.warning("Failed to create %s edge: %s", edge_type, exc)
        return False


def _safe_all_entries(graph) -> list:
    """Iteratively collect all CompositeEntry nodes with cycle detection.

    Avoids ``graph._all_entries()`` which can recurse infinitely when the
    codegraph library produces entry trees with cycles (e.g. due to
    colliding empty-string keys from LLM-generated node dicts).
    """
    result: list = []
    seen: set[int] = set()
    queue = deque(graph.entries.values())
    while queue:
        entry = queue.popleft()
        eid = id(entry)
        if eid in seen:
            continue
        seen.add(eid)
        result.append(entry)
        for type_children in entry.children.values():
            for child in type_children.values():
                if id(child) not in seen:
                    queue.append(child)
    return result


def _safe_flat_index(graph, all_entries: list) -> dict:
    """Build a flat key→CompositeEntry lookup without recursive walk."""
    from codegraph.graph import LayerGraph
    return {LayerGraph._node_key(e.node): e for e in all_entries}


# ══════════════════════════════════════════════════════════════════════════
# Persistence
# ══════════════════════════════════════════════════════════════════════════


def persist_decomposition(
    hlr_uid: str,
    decomposition: DecomposedRequirementSchema,
) -> DecompositionResult:
    """Persist an HLR decomposition to Neo4j using the codegraph LayerGraph system.

    The decomposition's ``nodes`` list (codegraph-format node dicts) is
    passed directly to ``LayerGraph.deserialize(create_missing=True)``,
    which auto-creates scaffold nodes for edge targets that don't
    exist in the list.  All nodes are persisted via
    ``create_or_update`` (upsert by unique property).  All edges are
    created via raw Cypher MERGE.

    If LLRs already exist for this HLR (re-decomposition), they are
    deleted first — including their verification subtrees.  Scaffold
    nodes are *not* deleted (shared across HLRs, deduplicated by
    deterministic ``uid``).

    Args:
        hlr_uid: The HLR's ``uid`` (hex UUID string).
        decomposition: A validated ``DecomposedRequirementSchema`` from
            the decompose agent.

    Returns:
        A :class:`DecompositionResult` with counts of everything created.

    Raises:
        ValueError: If the HLR is not found.
    """
    from codegraph.graph import LayerGraph
    from codegraph.models.compound import ClassNode
    from codegraph.models.member import AttributeNode
    from codegraph.models.literal import LiteralNode

    result = DecompositionResult()

    # --- Load the HLR by uid ---
    hlr = HLR.nodes.get_or_none(uid=hlr_uid)
    if hlr is None:
        raise ValueError(f"HLR '{hlr_uid}' not found")

    # --- Delete existing LLRs (and their verification subtrees) ---
    for old_llr in get_backend().graph.composed_children(hlr, LLR):
        _delete_llr_subtree(old_llr)

    # --- Deserialize into a LayerGraph with auto-scaffold creation ---
    nodes = list(decomposition.nodes)
    # Normalize: add qualified_name to LLR nodes that lack it.
    # Legacy decompose outputs only include "name"; deserialize needs
    # qualified_name as the identity field to derive a stable key.
    for n in nodes:
        if n.get("type") == "LLR" and not n.get("qualified_name"):
            n["qualified_name"] = n.get("name", "")
    graph = LayerGraph.deserialize(nodes, create_missing=True)

    # --- Validate scaffold graph: no orphaned scaffold nodes ---
    scaffold_errors = _validate_scaffold_graph(graph)
    if scaffold_errors:
        msg = "Scaffold graph validation failed:\n" + "\n".join(
            f"  - {e}" for e in scaffold_errors
        )
        log.error("persist_decomposition: %s", msg)
        raise ValueError(msg)

    # --- Persist all nodes via create_or_update ---
    for entry in graph._all_entries():
        entry.node = _persist_node(entry.node)

    # --- Collect scaffold nodes for diagnostics and scaffold_map ---
    for entry in graph._all_entries():
        node = entry.node
        is_scaffold = False
        if isinstance(node, ClassNode):
            result.scaffold_classes += 1
            is_scaffold = True
        elif isinstance(node, (AttributeNode, LiteralNode)):
            result.scaffold_attributes += 1
            is_scaffold = True

        # Only record nodes that were auto-created as scaffolds
        # (have the "scaffold" tag), not pre-existing real nodes.
        if is_scaffold and hasattr(node, "has_tag") and node.has_tag("scaffold"):
            qn = getattr(node, "qualified_name", None) or ""
            result.scaffold_map[qn] = {
                "type": type(node).__name__,
                "uid": getattr(node, "_uid_value", lambda: None)() or "",
                "kind": getattr(node, "kind", None) or "",
            }
            # For member nodes with a parent qualifier, record the parent
            if "::" in qn and isinstance(node, (AttributeNode, LiteralNode)):
                result.scaffold_map[qn]["parent"] = qn.rsplit("::", 1)[0]

    log.info(
        "persist_decomposition: %d scaffold class(es), %d scaffold attribute(s) "
        "auto-created from notional references",
        result.scaffold_classes, result.scaffold_attributes,
    )

    # --- Create all edges via raw Cypher ---
    flat = graph._flat_index()
    total_refs = 0
    missing_targets = 0
    for entry in graph._all_entries():
        source_node = entry.node

        # COMPOSES children
        for target_type, type_children in entry.children.items():
            for child_key, child_entry in type_children.items():
                _create_edge(source_node, child_entry.node, "COMPOSES")

        # Reference edges (LEFT_OPERAND, RIGHT_OPERAND, CALLEE, etc.)
        edge_counts: dict[str, int] = {}
        for relation_type, target_key, target_type in entry.references:
            total_refs += 1
            target_entry = flat.get(target_key)
            if target_entry is None:
                missing_targets += 1
                log.warning(
                    "persist_decomposition: missing flat target for "
                    "ref %s -> %s (key=%s) — scaffold may be orphaned",
                    relation_type, target_type, target_key[:20] if target_key else "?",
                )
                continue
            if _create_edge(source_node, target_entry.node, relation_type):
                result.operand_edges += 1
                edge_counts[relation_type] = edge_counts.get(relation_type, 0) + 1
    log.info(
        "persist_decomposition: %d reference edges (%d missing targets) — "
        "by type: %s",
        total_refs, missing_targets,
        ", ".join(f"{k}={v}" for k, v in sorted(edge_counts.items())),
    )

    # --- Connect LLRs to the HLR ---
    for entry in graph.entries.values():
        if type(entry.node) is LLR:
            _create_edge(hlr, entry.node, "COMPOSES")
            result.llrs_created += 1
            for test_node in get_backend().graph.composed_children(
                entry.node, TestNode
            ):
                result.tests_created += 1
                result.assertions_created += len(
                    get_backend().graph.composed_children(test_node, AssertionNode)
                )
                result.steps_created += len(
                    get_backend().graph.composed_children(test_node, TestStepNode)
                )
                result.fixtures_created += len(
                    get_backend().graph.composed_children(test_node, TestFixtureNode)
                )

    log.info(
        "persist_decomposition: HLR %s — %d LLRs, %d tests, %d assertions, "
        "%d steps, %d fixtures, %d scaffold classes, %d scaffold attributes",
        hlr_uid[:8], result.llrs_created, result.tests_created,
        result.assertions_created, result.steps_created,
        result.fixtures_created, result.scaffold_classes, result.scaffold_attributes,
    )

    # --- Clean up orphaned scaffold nodes from previous runs ---
    deleted = _cleanup_orphaned_scaffolds()
    if deleted:
        log.info(
            "persist_decomposition: cleaned up %d orphaned scaffold nodes",
            deleted,
        )

    return result


# ══════════════════════════════════════════════════════════════════════════
# Scaffold validation and cleanup
# ══════════════════════════════════════════════════════════════════════════


def _validate_scaffold_graph(graph) -> list[str]:
    """Validate that every scaffold node in the LayerGraph is reachable from verification.

    After ``LayerGraph.deserialize(create_missing=True)`` auto-creates scaffold
    nodes, this function checks that no scaffold is orphaned — i.e., every
    scaffold node must be either:

    - **Directly referenced** by an AssertionNode or TestStepNode edge
      (LEFT_OPERAND, RIGHT_OPERAND, CALLEE), or
    - A **parent ClassNode** that has at least one child referenced by an
      AssertionNode/TestStepNode edge.

    Returns
    -------
    list[str]
        Empty list if valid.  Otherwise, error messages for each orphaned scaffold.
    """
    from codegraph.models.compound import ClassNode

    errors: list[str] = []

    # --- Safe iterative walk of all entries with cycle detection ---
    all_entries = _safe_all_entries(graph)

    # Collect all scaffold node UIDs that are directly referenced by
    # Condition/Action edges (LEFT_OPERAND, RIGHT_OPERAND, CALLEE, etc.)
    directly_referenced: set[str] = set()

    # Map: parent ClassNode UID -> set of child UIDs (via COMPOSES)
    parent_to_children: dict[str, set[str]] = {}

    for entry in all_entries:
        node = entry.node
        is_scaffold = hasattr(node, "has_tag") and node.has_tag("scaffold")
        if not is_scaffold:
            continue

        node_uid = node._uid_value() or ""

        # Track COMPOSES children for parent ClassNodes
        if isinstance(node, ClassNode):
            for child_type, type_children in entry.children.items():
                for child_key, child_entry in type_children.items():
                    child_uid = child_entry.node._uid_value() or ""
                    parent_to_children.setdefault(node_uid, set()).add(child_uid)

    # Now check which scaffold UIDs are directly referenced by
    # AssertionNode/TestStepNode
    flat_index = _safe_flat_index(graph, all_entries)
    for entry in all_entries:
        for relation_type, target_key, target_type in entry.references:
            node = entry.node
            node_type_name = type(node).__name__
            if node_type_name in ("AssertionNode", "TestStepNode"):
                target_entry = flat_index.get(target_key)
                if target_entry:
                    target_uid = target_entry.node._uid_value() or ""
                    if target_uid:
                        directly_referenced.add(target_uid)

    # Check every scaffold node
    for entry in all_entries:
        node = entry.node
        is_scaffold = hasattr(node, "has_tag") and node.has_tag("scaffold")
        if not is_scaffold:
            continue

        node_uid = node._uid_value() or ""
        node_qn = getattr(node, "qualified_name", "") or ""
        node_type_name = type(node).__name__

        if node_uid in directly_referenced:
            continue  # Directly referenced — valid

        # For ClassNodes: check if any child is directly referenced
        if isinstance(node, ClassNode):
            children = parent_to_children.get(node_uid, set())
            referenced_children = children & directly_referenced
            if referenced_children:
                continue  # At least one child is referenced — valid
            child_names = []
            for child_type, type_children in entry.children.items():
                for child_key, child_entry in type_children.items():
                    child_qn = getattr(child_entry.node, "qualified_name", "") or ""
                    child_names.append(child_qn)
            errors.append(
                f"Scaffold ClassNode '{node_qn}' has no directly referenced children "
                f"(children: {child_names or ['none']})"
            )
        else:
            errors.append(
                f"Scaffold {node_type_name} '{node_qn}' is not referenced by any "
                "AssertionNode/TestStepNode edge"
            )

    return errors


def _cleanup_orphaned_scaffolds() -> int:
    """Delete scaffold nodes that have no path to any verification method.

    A scaffold node is "orphaned" if it cannot be reached from any
    AssertionNode or TestStepNode via LEFT_OPERAND / RIGHT_OPERAND / CALLEE
    edges, and (for ClassNodes) none of its COMPOSES children are reachable
    either.

    This runs after the new decomposition is persisted, cleaning up
    leftover scaffolds from previous runs that are no longer referenced.

    Returns the number of nodes deleted.
    """
    backend = get_backend()
    req = backend.requirements

    # Step 1: Scaffold nodes directly referenced by AssertionNode /
    #         TestStepNode edges (LEFT_OPERAND / RIGHT_OPERAND / CALLEE).
    directly_referenced_uids = set(req.find_scaffold_uids(directly_referenced=True))

    # Step 2: Scaffold ClassNodes that compose at least one referenced node.
    referenced_parent_uids = set(
        req.find_scaffold_parents_of_referenced(list(directly_referenced_uids))
    )

    all_reachable = directly_referenced_uids | referenced_parent_uids

    # Step 3: All scaffold uids; orphans = not reachable.
    all_scaffold_uids = set(req.find_scaffold_uids())
    orphan_uids = all_scaffold_uids - all_reachable

    if not orphan_uids:
        log.info(
            "_cleanup_orphaned_scaffolds: all %d scaffold(s) are reachable — "
            "%d directly, %d via parent ClassNode",
            len(all_scaffold_uids),
            len(directly_referenced_uids),
            len(referenced_parent_uids),
        )
        return 0

    log.warning(
        "_cleanup_orphaned_scaffolds: %d of %d scaffold(s) are orphaned "
        "(%d directly referenced, %d via parent ClassNode)",
        len(orphan_uids), len(all_scaffold_uids),
        len(directly_referenced_uids), len(referenced_parent_uids),
    )
    for i, uid in enumerate(sorted(orphan_uids)):
        if i < 10:
            qn = backend.graph.resolve_qualified_name(uid)
            log.info(
                "_cleanup_orphaned_scaffolds: orphaned scaffold %s",
                qn or uid,
            )
        else:
            log.info(
                "_cleanup_orphaned_scaffolds: ... and %d more orphaned scaffolds",
                len(orphan_uids) - 10,
            )
            break

    # Step 4: Delete orphaned scaffold nodes (and their edges).
    for uid in orphan_uids:
        try:
            req.delete_scaffold(uid)
        except Exception as exc:
            log.warning(
                "_cleanup_orphaned_scaffolds: failed to delete %s: %s",
                uid, exc,
            )

    return len(orphan_uids)


def _delete_llr_subtree(llr: LLR) -> None:
    """Delete an LLR and its entire verification subtree.

    Deletes all TestNode, AssertionNode, TestStepNode, and TestFixtureNode
    children, then the LLR itself.
    """
    for test_node in get_backend().graph.composed_children(llr, TestNode):
        for assertion in get_backend().graph.composed_children(
            test_node, AssertionNode
        ):
            assertion.delete()
        for step in get_backend().graph.composed_children(
            test_node, TestStepNode
        ):
            step.delete()
        for fixture in get_backend().graph.composed_children(
            test_node, TestFixtureNode
        ):
            fixture.delete()
        test_node.delete()
    llr.delete()
