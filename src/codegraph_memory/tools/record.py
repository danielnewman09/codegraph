"""record_memory — create, update, and link memory nodes in one call.

The primary write-side tool for agents.  Handles:
  - Creating new memory nodes
  - Updating existing ones (editable, not append-only)
  - Linking memory to code nodes
  - Memory-to-memory edges (supersedes, refines, contradicts)
  - Disambiguation when multiple nodes share a qualified_name
"""

from __future__ import annotations

from typing import Any, Literal

from codegraph.backends import get_backend
from codegraph.models.tags import CodeGraphNode
from codegraph_memory.models.base import MemoryNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.rationale import RationaleNode
from codegraph_memory.models.assumption import AssumptionNode
from codegraph_memory.models.tradeoff import TradeoffNode
from codegraph_memory.models.insight import InsightNode


# ── Type mapping ────────────────────────────────────────────────────

MemoryType = Literal[
    "decision", "constraint", "rationale", "assumption", "tradeoff", "insight",
]

_TYPE_TO_CLASS: dict[str, type[MemoryNode]] = {
    "decision": DecisionNode,
    "constraint": ConstraintNode,
    "rationale": RationaleNode,
    "assumption": AssumptionNode,
    "tradeoff": TradeoffNode,
    "insight": InsightNode,
}

# Memory → Code relationship type per memory class
_CODE_REL_MAP: dict[str, str] = {
    "DecisionNode": "MOTIVATES",
    "ConstraintNode": "CONSTRAINS",
    "RationaleNode": "EXPLAINS",
    "AssumptionNode": "ASSUMES",
    "TradeoffNode": "TRADES_OFF",
    "InsightNode": "INSIGHT_INTO",
}


# ── Public API ──────────────────────────────────────────────────────

def record_memory(
    type: MemoryType,
    qualified_name: str,
    content: str,
    *,
    tags: list[str] | None = None,
    confidence: float | None = None,
    source: str | None = None,
    links_to: str | list[str] | None = None,
    supersedes: str | None = None,
    refines: str | None = None,
    contradicts: str | None = None,
    mode: Literal["create", "update", "upsert"] = "upsert",
    uid: str | None = None,
) -> dict[str, Any]:
    """Create or update a memory node and link it to code.

    This is the primary write-side tool for agents.  It handles the full
    lifecycle: create, update, link to code, and memory-to-memory edges.

    Args:
        type: Memory node type — "decision", "constraint", "rationale",
              "assumption", "tradeoff", or "insight".
        qualified_name: Human-readable fully-qualified name
              (e.g. "memory::db-choice").  Must be unique per type.
        content: Free-text body of the memory.
        tags: Provenance tags (e.g. ["design", "as-built"]).
              Replaces existing tags on update.
        confidence: 0.0–1.0 certainty.  Replaces existing on update.
        source: Source project name (e.g. "myapp").
        links_to: qualified_name(s) of code nodes to link this memory to.
              Additive — adds new links, doesn't remove existing ones.
        supersedes: qualified_name of an older DecisionNode to supersede.
              Implies mode="create" (a new decision replaces the old one).
        refines: qualified_name of a DecisionNode this Rationale elaborates.
              Only valid when type="rationale".
        contradicts: qualified_name of an AssumptionNode this contradicts.
              Only valid when type="assumption".
        mode: "upsert" (default) — find by qualified_name, update if exists,
              create if not.  "create" — always create new (error if exists).
              "update" — error if not found.
        uid: Precise targeting by UID.  Overrides qualified_name lookup.

    Returns:
        A dict with keys:
          - action: "created", "updated", or "ambiguous"
          - type: the node class name (e.g. "DecisionNode")
          - qualified_name: the node's qualified_name
          - uid: the node's current UID
          - content: the node's content
          - tags: the node's tags
          - confidence: the node's confidence
          - linked_code: list of linked code node qualified_names
          - error: error message (None on success)
          - matches: list of disambiguation candidates (only when ambiguous)
    """
    # ── Validate type ────────────────────────────────────────────
    node_cls = _TYPE_TO_CLASS.get(type)
    if node_cls is None:
        return {
            "action": "error",
            "type": None,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": f"Unknown memory type: {type!r}. "
                     f"Must be one of: {list(_TYPE_TO_CLASS.keys())}",
            "matches": None,
        }

    # ── Validate memory-to-memory constraints ────────────────────
    if supersedes and type != "decision":
        return {
            "action": "error",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": "supersedes is only valid for type='decision'",
            "matches": None,
        }
    if refines and type != "rationale":
        return {
            "action": "error",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": "refines is only valid for type='rationale'",
            "matches": None,
        }
    if contradicts and type != "assumption":
        return {
            "action": "error",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": "contradicts is only valid for type='assumption'",
            "matches": None,
        }

    # supersedes implies create — always create a new node, never update
    if supersedes:
        mode = "create"
        existing = None  # force create, don't look up by qualified_name
    else:
        # ── Lookup existing node ──────────────────────────────────
        existing = _find_existing(node_cls, qualified_name, uid)

    if mode == "create" and existing is not None and not supersedes:
        return {
            "action": "error",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": existing.uid,
            "content": existing.content,
            "tags": list(existing.tags) if existing.tags else [],
            "confidence": existing.confidence,
            "linked_code": [],
            "error": f"A {node_cls.__name__} with qualified_name "
                     f"{qualified_name!r} already exists. Use mode='upsert' "
                     f"to update it, or choose a different qualified_name.",
            "matches": None,
        }

    if mode == "update" and existing is None:
        return {
            "action": "error",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": f"No {node_cls.__name__} found with qualified_name "
                     f"{qualified_name!r}. Use mode='create' or 'upsert'.",
            "matches": None,
        }

    # ── Handle disambiguation ─────────────────────────────────────
    if isinstance(existing, list):
        return {
            "action": "ambiguous",
            "type": node_cls.__name__,
            "qualified_name": qualified_name,
            "uid": None,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
            "linked_code": [],
            "error": f"Multiple {node_cls.__name__} nodes found with "
                     f"qualified_name {qualified_name!r}. Provide a uid "
                     f"to target a specific one.",
            "matches": [
                {
                    "uid": n.uid,
                    "content": n.content[:200] if n.content else "",
                    "confidence": n.confidence,
                    "tags": list(n.tags) if n.tags else [],
                }
                for n in existing
            ],
        }

    # ── Create or update ──────────────────────────────────────────
    if existing is not None:
        node = existing
        node.content = content
        if tags is not None:
            node.tags = tags
        if confidence is not None:
            node.confidence = confidence
        if source is not None:
            node.source = source
        node.save()
        action = "updated"
    else:
        node = node_cls(
            qualified_name=qualified_name,
            content=content,
            tags=tags or [],
            confidence=confidence if confidence is not None else 1.0,
            source=source or "",
        )
        node.save()
        action = "created"

    # ── Link to code nodes ────────────────────────────────────────
    linked_code: list[str] = []
    if links_to:
        code_qnames = [links_to] if isinstance(links_to, str) else links_to
        rel_type = _CODE_REL_MAP[node_cls.__name__]
        for qname in code_qnames:
            code_node = _find_code_node(qname)
            if code_node is not None:
                try:
                    get_backend().connect(node, rel_type, code_node)
                    linked_code.append(qname)
                except ValueError:
                    pass  # skip if no matching relationship declared

    # ── Memory-to-memory edges ────────────────────────────────────
    if supersedes:
        _link_supersedes(node, supersedes)
    if refines:
        _link_refines(node, refines)
    if contradicts:
        _link_contradicts(node, contradicts)

    return {
        "action": action,
        "type": node_cls.__name__,
        "qualified_name": node.qualified_name,
        "uid": node.uid,
        "content": node.content,
        "tags": list(node.tags) if node.tags else [],
        "confidence": node.confidence,
        "linked_code": linked_code,
        "error": None,
        "matches": None,
    }


# ── Internal helpers ────────────────────────────────────────────────

def _find_existing(
    node_cls: type[MemoryNode],
    qualified_name: str,
    uid: str | None,
) -> MemoryNode | list[MemoryNode] | None:
    """Find an existing memory node by uid or qualified_name.

    Returns:
        - A single MemoryNode if exactly one match
        - A list of MemoryNodes if multiple matches (disambiguation needed)
        - None if no match
    """
    if uid:
        return get_backend().graph.find_by_uid(uid)

    # Search by qualified_name — detect duplicate matches
    matches = get_backend().graph.find_all_by_qualified_name(
        qualified_name,
    )
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        return matches
    return matches[0]


def _find_code_node(qualified_name: str) -> CodeGraphNode | None:
    """Find a code node by qualified_name.

    Searches across all CodeGraphNode subclasses (ClassNode, MethodNode, etc.).
    """
    return get_backend().graph.find_by_qualified_name(qualified_name)


def _link_supersedes(new_decision: MemoryNode, old_qname: str) -> None:
    """Create a SUPERSEDES edge from new_decision to the old decision."""
    old = _find_existing(DecisionNode, old_qname, None)
    if old is None or isinstance(old, list):
        return  # silently skip if old decision not found
    get_backend().memory.merge_edge(
        new_decision.uid, "SUPERSEDES", old.uid,
        source_label="DecisionNode", target_label="DecisionNode",
    )


def _link_refines(rationale: MemoryNode, decision_qname: str) -> None:
    """Create a REFINES edge from rationale to the target decision."""
    target = _find_existing(DecisionNode, decision_qname, None)
    if target is None or isinstance(target, list):
        return
    get_backend().memory.merge_edge(
        rationale.uid, "REFINES", target.uid,
        source_label="RationaleNode", target_label="DecisionNode",
    )


def _link_contradicts(assumption: MemoryNode, other_qname: str) -> None:
    """Create a CONTRADICTS edge from assumption to the target assumption."""
    target = _find_existing(AssumptionNode, other_qname, None)
    if target is None or isinstance(target, list):
        return
    get_backend().memory.merge_edge(
        assumption.uid, "CONTRADICTS", target.uid,
        source_label="AssumptionNode", target_label="AssumptionNode",
    )
