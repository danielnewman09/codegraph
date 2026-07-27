"""Relationship helpers for querying memory→code edges."""

from __future__ import annotations

from typing import Any

from codegraph.models.tags import CodeGraphNode
from codegraph.backends import get_backend


def _inflate_code_node(raw_node: Any) -> CodeGraphNode | None:
    """Inflate a raw Neo4j node to the appropriate CodeGraphNode subclass.

    Determines the correct Python class by matching the node's Neo4j
    labels against ``__label__`` attributes in ``CodeGraphNode._registry``.
    """
    if raw_node is None:
        return None

    labels = set(raw_node.labels) if hasattr(raw_node, "labels") else set()

    best_cls = None
    best_score = 0
    for cls in CodeGraphNode._registry.values():
        cls_label = getattr(cls, "__label__", None)
        if not cls_label or cls_label not in labels:
            continue
        is_abstract = getattr(cls, "__abstract__", False)
        score = (0 if is_abstract else 1000) + len(
            cls.defined_properties().keys() & set(raw_node.keys())
        )
        if score > best_score:
            best_cls = cls
            best_score = score

    if best_cls is None:
        return None

    return best_cls.inflate(raw_node)


def get_linked_code_nodes(
    memory_node: CodeGraphNode, relation_type: str
) -> list[CodeGraphNode]:
    """Return all code nodes linked to *memory_node* via *relation_type*."""
    return get_backend().graph.outgoing_by_relation(
        memory_node, relation_type,
    )


def get_linked_memory_nodes(
    code_node: CodeGraphNode, relation_type: str
) -> list[CodeGraphNode]:
    """Return all memory nodes linking to *code_node* via *relation_type*."""
    uid = code_node._uid_value()
    if not uid:
        return []
    results = get_backend().memory.find_for_code_node(uid)
    return [
        r["node"] for r in results
        if r["rel_type"] == relation_type
    ]


def get_all_memory_for_code_node(
    code_node: CodeGraphNode
) -> list[CodeGraphNode]:
    """Return all memory nodes linked to *code_node* via any relationship type."""
    uid = code_node._uid_value()
    if not uid:
        return []
    return [
        r["node"] for r in get_backend().memory.find_for_code_node(uid)
    ]
