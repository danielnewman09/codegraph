"""Memory search tool — full-text and vector search across memory content.

Implements: search_memory.
"""

from __future__ import annotations

from typing import Any

from codegraph.persistence.memory_repository import MemoryRepository


def search_memory(
    query: str,
    limit: int = 20,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Full-text search across all memory node content.

    Delegates to MemoryRepository.search_content, which uses Neo4j's
    full-text index (memory_search) with a CONTAINS fallback.

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
    return MemoryRepository.search_content(query, limit=limit, tag=tag)


def search_memory_semantic(
    embedding: list[float],
    limit: int = 10,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Vector similarity search across memory node embeddings.

    Delegates to MemoryRepository.search_semantic, which uses Neo4j's
    vector index (memory_embedding).

    Args:
        embedding: A 1536-dimensional embedding vector.
        limit: Maximum number of results to return (default 10).
        tag: Optional tag filter.

    Returns:
        A list of serialized memory node dicts with similarity scores.
    """
    if not embedding:
        return []
    return MemoryRepository.search_semantic(embedding, limit=limit, tag=tag)