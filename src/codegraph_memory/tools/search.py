"""Memory search tool — full-text and vector search across memory content.

Implements: search_memory.
"""

from __future__ import annotations

from typing import Any

from neomodel import db

from codegraph_memory.models.relationships import _inflate_code_node


def search_memory(
    query: str,
    limit: int = 20,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Full-text search across all memory node content.

    Uses Neo4j's full-text index (memory_search) to find memory nodes
    whose content or qualified_name matches the query string.

    Args:
        query: The search string.
        limit: Maximum number of results to return (default 20).
        tag: Optional tag filter (e.g. "design", "as-built"). When
            provided, only memories with this tag are returned.

    Returns:
        A list of serialized memory node dicts, ordered by relevance.
    """
    if not query.strip():
        return []

    # Build the Cypher query using the full-text index
    cypher = (
        "CALL db.index.fulltext.queryNodes('memory_search', $query) "
        "YIELD node, score "
    )
    if tag:
        cypher += f"WHERE ${tag!r} IN node.tags "
    cypher += "RETURN node, score ORDER BY score DESC LIMIT $limit"

    try:
        results, _ = db.cypher_query(
            cypher,
            {"query": query, "limit": limit},
        )
    except Exception:
        # Fallback: simple CONTAINS search if full-text index doesn't exist
        label_filter = (
            "AND $tag IN m.tags" if tag else ""
        )
        results, _ = db.cypher_query(
            "MATCH (m) "
            "WHERE (m:DecisionNode OR m:ConstraintNode OR m:RationaleNode "
            "OR m:AssumptionNode OR m:TradeoffNode OR m:InsightNode) "
            "AND (toLower(m.content) CONTAINS toLower($query) "
            "OR toLower(m.qualified_name) CONTAINS toLower($query)) "
            f"{label_filter} "
            "RETURN m, 1.0 AS score "
            "LIMIT $limit",
            {"query": query, "tag": tag, "limit": limit},
        )

    output: list[dict[str, Any]] = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is not None:
            data = node.serialize()
            data["search_score"] = row[1] if len(row) > 1 else 0.0
            output.append(data)
    return output


def search_memory_semantic(
    embedding: list[float],
    limit: int = 10,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Vector similarity search across memory node embeddings.

    Uses Neo4j's vector index (memory_embedding) to find memory nodes
    whose doc_embedding is most similar to the given embedding.

    Args:
        embedding: A 1536-dimensional embedding vector.
        limit: Maximum number of results to return (default 10).
        tag: Optional tag filter.

    Returns:
        A list of serialized memory node dicts with similarity scores.
    """
    if not embedding:
        return []

    cypher = (
        "CALL db.index.vector.queryNodes('memory_embedding', $limit, $embedding) "
        "YIELD node, score "
    )
    if tag:
        cypher += f"WHERE ${tag!r} IN node.tags "
    cypher += "RETURN node, score ORDER BY score DESC"

    try:
        results, _ = db.cypher_query(
            cypher,
            {"embedding": embedding, "limit": limit, "tag": tag},
        )
    except Exception:
        return []  # vector index may not exist yet

    output: list[dict[str, Any]] = []
    for row in results:
        node = _inflate_code_node(row[0])
        if node is not None:
            data = node.serialize()
            data["similarity_score"] = row[1] if len(row) > 1 else 0.0
            output.append(data)
    return output