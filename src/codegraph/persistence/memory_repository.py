"""MemoryRepository — abstract interface for design memory operations.

Memory nodes (DecisionNode, ConstraintNode, RationaleNode, etc.) have
their own labels, relationship types, full-text indexes, and query
patterns.  This interface defines the contract that every backend must
implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode


class MemoryRepository(ABC):
    """Abstract interface for design memory data access."""

    # ── Memory → code node queries ──────────────────────────────────

    @abstractmethod
    def find_for_code_node(self, uid: str) -> list[dict]:
        """Return all memory nodes linked to a code node by uid.

        Returns ``[{"memory": CodeGraphNode, "rel_type": str}]``.
        """
        ...

    @abstractmethod
    def find_for_code_node_by_qname(
        self, qualified_name: str
    ) -> list[dict]:
        """Convenience: resolve qname → uid, then find memories."""
        ...

    # ── Memory nodes by tag ────────────────────────────────────────

    @abstractmethod
    def find_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Return all memory nodes with *tag*."""
        ...

    # ── Memory-to-memory edges ─────────────────────────────────────

    @abstractmethod
    def merge_edge(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        source_label: str,
        target_label: str,
    ) -> None:
        """Create a memory-to-memory edge (SUPERSEDES, REFINES,
        CONTRADICTS)."""
        ...

    # ── Composite traversal + memory queries ───────────────────────

    @abstractmethod
    def find_linked_to_ancestors(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list[dict]:
        """Walk COMPOSES upward and return memories linked to any
        ancestor.  Returns ``[{memory, source_uid, rel_type}]``."""
        ...

    @abstractmethod
    def find_linked_to_descendants(
        self,
        uid: str,
        *,
        max_depth: int = 10,
    ) -> list["CodeGraphNode"]:
        """Walk COMPOSES downward and return distinct memories linked
        to any descendant."""
        ...

    # ── Full-text search ───────────────────────────────────────────

    @abstractmethod
    def search_content(
        self,
        query: str,
        limit: int = 20,
        tag: str | None = None,
    ) -> list[dict]:
        """Full-text search across memory node content.

        Returns ``[{...serialized node..., search_score: float}]``.
        """
        ...

    # ── Vector search ──────────────────────────────────────────────

    @abstractmethod
    def search_semantic(
        self,
        embedding: list[float],
        limit: int = 10,
        tag: str | None = None,
    ) -> list[dict]:
        """Vector similarity search across memory node embeddings.

        Returns ``[{...serialized node..., similarity_score: float}]``.
        """
        ...
