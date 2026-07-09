"""Relationship helpers for memory-to-code edges.

Memory nodes link to arbitrary CodeGraphNode subclasses via neomodel
RelationshipTo("CodeGraphNode", ...).  This works for .connect() but
not for .all(), because CodeGraphNode is not a StructuredNode and has
no ``__label__`` attribute.

This module provides helper functions that use raw Cypher to query
memory-to-code relationships and inflate the results to the correct
CodeGraphNode subclass based on Neo4j labels.
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph.models.tags import CodeGraphNode


def _inflate_code_node(raw_node: Any) -> CodeGraphNode | None:
    """Inflate a raw Neo4j node to the appropriate CodeGraphNode subclass.

    Determines the correct Python class by matching the node's Neo4j
    labels against ``__label__`` attributes in ``CodeGraphNode._registry``.

    Args:
        raw_node: A raw neo4j graph node object (from a Cypher query result).

    Returns:
        An inflated CodeGraphNode subclass instance, or None if no
        matching class is found in the registry.
    """
    if raw_node is None:
        return None

    labels = set(raw_node.labels) if hasattr(raw_node, "labels") else set()

    # Find the most specific class (most labels matched) in the registry.
    # Prefer concrete (non-abstract) classes over abstract ones, since
    # concrete subclasses inherit the abstract base's label.
    best_cls = None
    best_score = 0
    for cls in CodeGraphNode._registry.values():
        cls_label = getattr(cls, "__label__", None)
        if not cls_label or cls_label not in labels:
            continue
        is_abstract = getattr(cls, "__abstract__", False)
        # Score: concrete classes get a bonus, plus property overlap
        score = (0 if is_abstract else 1000) + len(
            cls.defined_properties().keys() & set(raw_node.keys())
        )
        if score > best_score:
            best_cls = cls
            best_score = score

    if best_cls is None:
        return None

    return best_cls.inflate(raw_node)


def get_linked_code_nodes(memory_node: CodeGraphNode, relation_type: str) -> list[CodeGraphNode]:
    """Return all code nodes linked to *memory_node* via *relation_type*.

    Uses raw Cypher to traverse the relationship and inflates results
    to the correct CodeGraphNode subclass.

    Args:
        memory_node: A memory node instance (DecisionNode, ConstraintNode, etc.)
        relation_type: The Neo4j relationship type (e.g. "MOTIVATES", "CONSTRAINS")

    Returns:
        A list of inflated CodeGraphNode instances linked via the relationship.
    """
    if not hasattr(memory_node, "element_id_property"):
        return []

    label = type(memory_node).__label__
    results, _ = db.cypher_query(
        f"MATCH (m:`{label}`)-[:{relation_type}]->(c) "
        f"WHERE elementId(m) = $mid RETURN c",
        {"mid": db.parse_element_id(memory_node.element_id)},
    )
    nodes = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is not None:
            nodes.append(node)
    return nodes


def get_linked_memory_nodes(code_node: CodeGraphNode, relation_type: str) -> list[CodeGraphNode]:
    """Return all memory nodes linking to *code_node* via *relation_type*.

    Uses raw Cypher to traverse the reverse relationship and inflates
    results to the correct memory node subclass.

    Args:
        code_node: A code node instance (ClassNode, MethodNode, etc.)
        relation_type: The Neo4j relationship type (e.g. "MOTIVATES", "CONSTRAINS")

    Returns:
        A list of inflated memory node instances linked via the relationship.
    """
    if not hasattr(code_node, "element_id_property"):
        return []

    results, _ = db.cypher_query(
        f"MATCH (m)-[:{relation_type}]->(c) "
        f"WHERE elementId(c) = $cid RETURN m",
        {"cid": db.parse_element_id(code_node.element_id)},
    )
    nodes = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is not None:
            nodes.append(node)
    return nodes


def get_all_memory_for_code_node(code_node: CodeGraphNode) -> list[CodeGraphNode]:
    """Return all memory nodes linked to *code_node* via any relationship type.

    Traverses all outgoing memory→code relationship types and returns
    a flat list of linked memory nodes.

    Args:
        code_node: A code node instance.

    Returns:
        A list of inflated memory node instances.
    """
    if not hasattr(code_node, "element_id_property"):
        return []

    # All memory→code relationship types
    rel_types = [
        "MOTIVATES", "CONSTRAINS", "EXPLAINS",
        "ASSUMES", "TRADES_OFF", "INSIGHT_INTO",
    ]
    rel_pattern = "|".join(rel_types)

    results, _ = db.cypher_query(
        f"MATCH (m)-[:{rel_pattern}]->(c) "
        f"WHERE elementId(c) = $cid RETURN m",
        {"cid": db.parse_element_id(code_node.element_id)},
    )
    nodes = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is not None:
            nodes.append(node)
    return nodes