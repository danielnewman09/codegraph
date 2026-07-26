"""Memory search — full-text and vector search across memory content."""

from __future__ import annotations

from typing import Any

from codegraph.backends import get_backend


def search_memory(
    query: str,
    limit: int = 20,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Full-text search across all memory node content.

    Args:
        query: The search string.
        limit: Maximum number of results to return (default 20).
        tag: Optional tag filter (e.g. "design", "as-built").

    Returns:
        A list of serialized memory node dicts with ``search_score``,
        ordered by relevance.
    """
    if not query.strip():
        return []
    return get_backend().memory.search_content(query, limit=limit, tag=tag)


def search_memory_semantic(
    embedding: list[float],
    limit: int = 10,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Vector similarity search across memory node embeddings.

    Args:
        embedding: A 1536-dimensional embedding vector.
        limit: Maximum number of results to return (default 10).
        tag: Optional tag filter.

    Returns:
        A list of serialized memory node dicts with ``similarity_score``.
    """
    if not embedding:
        return []
    return get_backend().memory.search_semantic(embedding, limit=limit, tag=tag)
