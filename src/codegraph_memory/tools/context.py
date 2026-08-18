"""memory_context — fetch all design memory relevant to a code node.

The primary read-side tool for agents before modifying code.  Walks the
COMPOSES hierarchy upward to find inherited context (method → class →
namespace), plus direct memories on the target node itself.

Returns memories organized by proximity, with a summary that flags
low-confidence assumptions and superseded decisions.
"""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend


def memory_context(
    qualified_name: str,
    *,
    traverse_parents: bool = True,
    max_depth: int = 5,
    include_superseded: bool = False,
) -> dict[str, Any]:
    """Return all design memory relevant to a code node.

    Walks the COMPOSES hierarchy upward to find inherited context:
    a method inherits its class's decisions, a class inherits its
    namespace's constraints, etc.

    Args:
        qualified_name: The qualified_name of the target code node.
        traverse_parents: If True (default), walk COMPOSES upward to
              include memories from parent nodes.
        max_depth: Maximum COMPOSES traversal depth (default 5).
        include_superseded: If True, include decisions that have been
              superseded.  Default False — only current decisions.

    Returns:
        A dict with keys:
          - target: {qualified_name, kind} of the target node
          - direct: list of memory dicts directly linked to the target
          - inherited: list of {source, source_kind, depth, memories}
            for each ancestor in the COMPOSES chain
          - summary: {total_memories, by_type, low_confidence, superseded}
    """
    backend = get_backend()

    # ── Resolve target node ──────────────────────────────────────
    target_node = backend.graph.find_by_qualified_name(qualified_name)
    if target_node is None:
        return {
            "target": {"qualified_name": qualified_name, "kind": None},
            "direct": [],
            "inherited": [],
            "summary": {
                "total_memories": 0,
                "by_type": {},
                "low_confidence": [],
                "superseded": [],
            },
            "error": f"No code node found with qualified_name {qualified_name!r}",
        }

    target_uid = target_node.canonical_key
    labels = backend.graph.get_labels(target_uid) if target_uid else set()
    kind = _kind_from_labels(labels)

    target_info = {"qualified_name": qualified_name, "kind": kind}

    # ── Direct memories ───────────────────────────────────────────
    direct = _memories_for_node(qualified_name)

    # ── Inherited memories (upward COMPOSES) ──────────────────────
    inherited: list[dict[str, Any]] = []
    if traverse_parents and target_uid:
        inherited = _inherited_memories(target_uid, qualified_name, max_depth)

    # ── Build summary ─────────────────────────────────────────────
    all_memories = list(direct)
    for entry in inherited:
        all_memories.extend(entry["memories"])

    summary = _build_summary(all_memories, include_superseded)

    return {
        "target": target_info,
        "direct": direct,
        "inherited": inherited,
        "summary": summary,
        "error": None,
    }


# ── Internal helpers ────────────────────────────────────────────────

_KIND_PRIORITY_TARGET = [
    "MethodNode", "AttributeNode", "EnumValueNode",
    "FunctionNode", "DefineNode",
    "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
    "NamespaceNode", "FileNode",
]

_KIND_PRIORITY_ANCESTOR = [
    "NamespaceNode", "FileNode",
    "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
]


def _kind_from_labels(labels: set[str], priority: list[str] | None = None) -> str:
    if priority is None:
        priority = _KIND_PRIORITY_TARGET
    for k in priority:
        if k in labels:
            return k
    return "CodeGraphNode"


def _memories_for_node(qualified_name: str) -> list[dict[str, Any]]:
    """Return all memory nodes directly linked to a code node."""
    backend = get_backend()
    results = backend.memory.find_for_code_node_by_qname(qualified_name)
    memories: list[dict[str, Any]] = []
    for r in results:
        node = r["node"]
        entry = node.serialize()
        entry["relation"] = r["rel_type"]
        memories.append(entry)
    return memories


def _inherited_memories(
    target_uid: str,
    target_qname: str,
    max_depth: int,
) -> list[dict[str, Any]]:
    """Walk COMPOSES upward and collect memories from ancestor nodes.

    Returns a list of {source, source_kind, depth, memories} dicts,
    ordered from nearest ancestor (depth 1) to farthest.
    """
    backend = get_backend()
    results = backend.memory.find_linked_to_ancestors(target_uid, max_depth=max_depth)

    # Group by ancestor
    by_ancestor: dict[str, dict[str, Any]] = {}
    for r in results:
        source_uid = r["source_uid"]
        memory_node = r["memory"]
        rel_type = r["rel_type"]

        if memory_node is None:
            continue

        # Resolve source qualified_name from uid
        source_qname = backend.graph.resolve_qualified_name(source_uid)
        if source_qname is None:
            source_qname = source_uid

        if source_qname not in by_ancestor:
            labels = backend.graph.get_labels(source_uid)
            kind = _kind_from_labels(labels, _KIND_PRIORITY_ANCESTOR)
            by_ancestor[source_qname] = {
                "source": source_qname,
                "source_kind": kind,
                "memories": [],
            }

        entry = memory_node.serialize()
        entry["relation"] = rel_type
        by_ancestor[source_qname]["memories"].append(entry)

    # Compute depth for each ancestor (approximate by qname nesting)
    target_parts = target_qname.split("::")
    result: list[dict[str, Any]] = []
    for qname, data in by_ancestor.items():
        ancestor_parts = qname.split("::")
        depth = len(target_parts) - len(ancestor_parts)
        data["depth"] = max(1, depth)
        result.append(data)

    # Sort by depth (nearest first)
    result.sort(key=lambda x: x["depth"])
    return result


def _build_summary(
    memories: list[dict[str, Any]],
    include_superseded: bool,
) -> dict[str, Any]:
    """Build a summary of the memory context."""
    by_type: dict[str, int] = {}
    low_confidence: list[str] = []
    superseded: list[str] = []

    for m in memories:
        mtype = m.get("type", "Unknown")
        by_type[mtype] = by_type.get(mtype, 0) + 1

        confidence = m.get("confidence", 1.0)
        if confidence is not None and confidence < 0.5:
            low_confidence.append(m.get("qualified_name", ""))

        # Check if this decision is superseded
        if mtype == "DecisionNode" and not include_superseded:
            qname = m.get("qualified_name", "")
            if qname:
                backend = get_backend()
                from codegraph_memory.models.decision import DecisionNode

                older = backend.get(DecisionNode, qualified_name=qname)
                if older is not None:
                    superseded_by = [
                        e for e in backend.get_all_edges(older)
                        if e.relation_type == "SUPERSEDES" and not e.is_outgoing
                    ]
                    if superseded_by:
                        superseded.append(qname)

    return {
        "total_memories": len(memories),
        "by_type": by_type,
        "low_confidence": low_confidence,
        "superseded": superseded,
    }
