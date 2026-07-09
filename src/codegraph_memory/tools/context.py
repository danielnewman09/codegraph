"""memory_context — fetch all design memory relevant to a code node.

The primary read-side tool for agents before modifying code.  Walks the
COMPOSES hierarchy upward to find inherited context (method → class →
namespace), plus direct memories on the target node itself.

Returns memories organized by proximity, with a summary that flags
low-confidence assumptions and superseded decisions.
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph_memory.models.relationships import _inflate_code_node


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
    # ── Resolve target node ──────────────────────────────────────
    target_info = _resolve_target(qualified_name)
    if target_info is None:
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

    # ── Direct memories ───────────────────────────────────────────
    direct = _memories_for_node(qualified_name)

    # ── Inherited memories (upward COMPOSES) ──────────────────────
    inherited: list[dict[str, Any]] = []
    if traverse_parents:
        inherited = _inherited_memories(qualified_name, max_depth)

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

def _resolve_target(qualified_name: str) -> dict[str, Any] | None:
    """Resolve a qualified_name to a target info dict.

    Returns:
        {"qualified_name": str, "kind": str} or None if not found.
    """
    results, _ = db.cypher_query(
        "MATCH (n) WHERE n.qualified_name = $qname "
        "RETURN n.qualified_name AS qname, labels(n) AS labels LIMIT 1",
        {"qname": qualified_name},
    )
    if not results:
        return None

    row = results[0]
    labels = set(row[1]) if row[1] else set()
    # Determine the most specific kind from labels
    kind = "CodeGraphNode"
    kind_priority = [
        "MethodNode", "AttributeNode", "EnumValueNode",
        "FunctionNode", "DefineNode",
        "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
        "NamespaceNode", "FileNode",
    ]
    for k in kind_priority:
        if k in labels:
            kind = k
            break

    return {
        "qualified_name": row[0],
        "kind": kind,
    }


def _memories_for_node(qualified_name: str) -> list[dict[str, Any]]:
    """Return all memory nodes directly linked to a code node."""
    results, _ = db.cypher_query(
        "MATCH (m)-[r:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(target) "
        "WHERE target.qualified_name = $qname "
        "RETURN m, type(r) AS rel_type",
        {"qname": qualified_name},
    )
    memories: list[dict[str, Any]] = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is None:
            continue
        entry = node.serialize()
        entry["relation"] = row[1]
        memories.append(entry)
    return memories


def _inherited_memories(
    qualified_name: str,
    max_depth: int,
) -> list[dict[str, Any]]:
    """Walk COMPOSES upward and collect memories from ancestor nodes.

    Returns a list of {source, source_kind, depth, memories} dicts,
    ordered from nearest ancestor (depth 1) to farthest.
    """
    # Neo4j doesn't allow parameters in variable-length patterns,
    # so we interpolate max_depth directly (it's an int, safe from injection).
    results, _ = db.cypher_query(
        f"MATCH (target)<-[:COMPOSES*1..{max_depth}]-(ancestor) "
        "WHERE target.qualified_name = $qname "
        "MATCH (m)-[r:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(ancestor) "
        "RETURN ancestor.qualified_name AS source_qname, "
        "labels(ancestor) AS source_labels, "
        "m, type(r) AS rel_type "
        "ORDER BY source_qname",
        {"qname": qualified_name},
    )

    # Group by ancestor
    by_ancestor: dict[str, dict[str, Any]] = {}
    for row in results:
        source_qname = row[0]
        source_labels = set(row[1]) if row[1] else set()
        memory_node = _inflate_code_node(row[2])
        rel_type = row[3]

        if memory_node is None:
            continue

        if source_qname not in by_ancestor:
            # Determine kind
            kind = "CodeGraphNode"
            kind_priority = [
                "NamespaceNode", "FileNode",
                "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
            ]
            for k in kind_priority:
                if k in source_labels:
                    kind = k
                    break

            by_ancestor[source_qname] = {
                "source": source_qname,
                "source_kind": kind,
                "memories": [],
            }

        entry = memory_node.serialize()
        entry["relation"] = rel_type
        by_ancestor[source_qname]["memories"].append(entry)

    # Compute depth for each ancestor (approximate by qname nesting)
    target_parts = qualified_name.split("::")
    result: list[dict[str, Any]] = []
    for qname, data in by_ancestor.items():
        ancestor_parts = qname.split("::")
        # Depth = how many levels up from target
        # If target is a::b::c::method and ancestor is a::b, depth = 1
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
    """Build a summary of the memory context.

    Args:
        memories: Flat list of serialized memory dicts.
        include_superseded: Whether to include superseded decisions.

    Returns:
        A dict with total_memories, by_type, low_confidence, superseded.
    """
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
                # Check if any other decision supersedes this one
                results, _ = db.cypher_query(
                    "MATCH (newer:DecisionNode)-[:SUPERSEDES]->(older:DecisionNode) "
                    "WHERE older.qualified_name = $qname "
                    "RETURN newer.qualified_name",
                    {"qname": qname},
                )
                if results:
                    superseded.append(qname)

    return {
        "total_memories": len(memories),
        "by_type": by_type,
        "low_confidence": low_confidence,
        "superseded": superseded,
    }
