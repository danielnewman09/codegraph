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

    from codegraph.persistence.connection import init_neo4j
    from codegraph_requirements.persistence import persist_decomposition

    init_neo4j()
    result = persist_decomposition(
        hlr_refid="2c3463b2…",
        decomposition=decomposed,
    )
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from neomodel import db

from codegraph_requirements.models.requirement import HLR, LLR
from codegraph_requirements.schemas import DecomposedRequirementSchema

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
    """Persist a node via ``create_or_update``, returning the saved instance."""
    node_type = type(node)
    uid_prop = node_type._uid_prop()
    if uid_prop is None:
        node.save()
        return node

    props = {}
    for prop_name in node_type.defined_properties():
        val = getattr(node, prop_name, None)
        if val is not None:
            props[prop_name] = val

    persisted = node_type.create_or_update(
        props,
        merge_by={"keys": [uid_prop]},
    )
    return persisted[0]


def _create_edge(source, target, edge_type: str) -> bool:
    """Create any edge between two saved nodes using raw Cypher MERGE."""
    try:
        query = (
            f"MATCH (s), (t) "
            f"WHERE elementId(s) = $source_id AND elementId(t) = $target_id "
            f"MERGE (s)-[:{edge_type}]->(t)"
        )
        db.cypher_query(
            query,
            {
                "source_id": db.parse_element_id(source.element_id),
                "target_id": db.parse_element_id(target.element_id),
            },
        )
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
    hlr_refid: str,
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
        hlr_refid: The HLR's ``refid`` (hex UUID string).
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

    # --- Load the HLR (try uid first, then refid) ---
    hlr = HLR.nodes.get_or_none(uid=hlr_refid)
    if hlr is None:
        hlr = HLR.nodes.get_or_none(refid=hlr_refid)
    if hlr is None:
        raise ValueError(f"HLR '{hlr_refid}' not found")

    # --- Delete existing LLRs (and their verification subtrees) ---
    for old_llr in hlr.llrs.all():
        _delete_llr_subtree(old_llr)

    # --- Deserialize into a LayerGraph with auto-scaffold creation ---
    graph = LayerGraph.deserialize(
        list(decomposition.nodes),
        create_missing=True,
    )

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
        for relation_type, target_key, target_type in entry.references:
            total_refs += 1
            target_entry = flat.get(target_key)
            if target_entry is None:
                missing_targets += 1
                log.debug(
                    "persist_decomposition: missing flat target for "
                    "ref %s -> %s (key=%s)",
                    relation_type, target_type, target_key[:20] if target_key else "?",
                )
                continue
            if _create_edge(source_node, target_entry.node, relation_type):
                result.operand_edges += 1
    log.info(
        "persist_decomposition: %d reference edges (%d missing targets)",
        total_refs, missing_targets,
    )

    # --- Connect LLRs to the HLR ---
    for entry in graph.entries.values():
        if isinstance(entry.node, LLR):
            _create_edge(hlr, entry.node, "COMPOSES")
            result.llrs_created += 1
            for test_node in entry.node.verification_methods.all():
                result.tests_created += 1
                result.assertions_created += len(test_node.assertions.all())
                result.steps_created += len(test_node.steps.all())
                result.fixtures_created += len(test_node.fixtures.all())

    log.info(
        "persist_decomposition: HLR %s — %d LLRs, %d tests, %d assertions, "
        "%d steps, %d fixtures, %d scaffold classes, %d scaffold attributes",
        hlr_refid[:8], result.llrs_created, result.tests_created,
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
    # Step 1: Find scaffold nodes that ARE directly referenced by
    #         AssertionNode/TestStepNode edges.
    query_direct = """
    MATCH (ca)-[r]->(s)
    WHERE (ca:Assertion OR ca:TestStep)
      AND (r:LEFT_OPERAND OR r:RIGHT_OPERAND OR r:CALLEE)
      AND 'scaffold' IN s.tags
    RETURN DISTINCT elementId(s) AS eid
    """
    try:
        results, _ = db.cypher_query(query_direct)
    except Exception as exc:
        log.warning("_cleanup_orphaned_scaffolds: direct query failed: %s", exc)
        return 0

    directly_referenced_eids = {row[0] for row in results}

    # Step 2: Find scaffold ClassNodes that have at least one COMPOSES child
    #         that is directly referenced.
    query_parent = """
    MATCH (parent:Class)-[:COMPOSES]->(child)
    WHERE 'scaffold' IN parent.tags
      AND elementId(child) IN $referenced_eids
    RETURN DISTINCT elementId(parent) AS eid
    """
    try:
        results, _ = db.cypher_query(
            query_parent,
            {"referenced_eids": list(directly_referenced_eids)},
        )
    except Exception as exc:
        log.warning("_cleanup_orphaned_scaffolds: parent query failed: %s", exc)
        return 0

    referenced_parent_eids = {row[0] for row in results}
    all_reachable = directly_referenced_eids | referenced_parent_eids

    # Step 3: Find ALL scaffold nodes and delete those not in the reachable set.
    query_all = """
    MATCH (s)
    WHERE 'scaffold' IN s.tags
    RETURN elementId(s) AS eid, s.qualified_name AS qn, labels(s) AS lbls
    """
    try:
        results, _ = db.cypher_query(query_all)
    except Exception as exc:
        log.warning("_cleanup_orphaned_scaffolds: list query failed: %s", exc)
        return 0

    orphan_eids = []
    for row in results:
        eid, qn, lbls = row[0], row[1], row[2]
        if eid not in all_reachable:
            orphan_eids.append(eid)
            log.info(
                "_cleanup_orphaned_scaffolds: orphaned scaffold %s (%s)",
                qn or "?", lbls,
            )

    if not orphan_eids:
        return 0

    # Step 4: Delete orphaned scaffold nodes (and their edges).
    for eid in orphan_eids:
        try:
            db.cypher_query(
                "MATCH (s) WHERE elementId(s) = $eid "
                "DETACH DELETE s",
                {"eid": eid},
            )
        except Exception as exc:
            log.warning(
                "_cleanup_orphaned_scaffolds: failed to delete %s: %s",
                eid, exc,
            )

    return len(orphan_eids)


def _delete_llr_subtree(llr: LLR) -> None:
    """Delete an LLR and its entire verification subtree.

    Deletes all TestNode, AssertionNode, TestStepNode, and TestFixtureNode
    children, then the LLR itself.
    """
    for test_node in llr.verification_methods.all():
        for assertion in test_node.assertions.all():
            assertion.delete()
        for step in test_node.steps.all():
            step.delete()
        for fixture in test_node.fixtures.all():
            fixture.delete()
        test_node.delete()
    llr.delete()
