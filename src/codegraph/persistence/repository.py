"""GraphRepository — abstract interface for code graph operations.

Defines the contract that every backend must implement.  Neo4j, SQLite,
Postgres, etc. each provide a concrete implementation.

All methods use ``uid`` as the canonical cross-backend key.

Usage::

    from codegraph.backends import get_backend

    node = get_backend().graph.find_by_uid("abc123")
    labels = get_backend().graph.get_labels("abc123")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.constants import Tag
    from codegraph.graph import LayerGraph
    from codegraph.models.tags import CodeGraphNode


class GraphRepository(ABC):
    """Abstract interface for code graph data access.

    Concrete implementations (Neo4jGraphRepository, SQLiteGraphRepository,
    etc.) provide the storage-specific logic.
    """

    # ── uid / qualified_name resolution ───────────────────────────

    @abstractmethod
    def resolve_uid(self, qualified_name: str) -> str | None:
        """Look up the ``uid`` for a node by ``qualified_name``."""
        ...

    @abstractmethod
    def resolve_uid_by_name(self, name: str, *, label: str | None = None) -> str | None:
        """Look up the ``uid`` for a node by ``name`` (optionally label-qualified)."""
        ...

    @abstractmethod
    def resolve_qualified_name(self, uid: str) -> str | None:
        """Look up the ``qualified_name`` for a node by ``uid``."""
        ...

    # ── Node lookup ───────────────────────────────────────────────

    @abstractmethod
    def find_by_uid(self, uid: str) -> "CodeGraphNode | None":
        """Find any node by its deterministic uid."""
        ...

    @abstractmethod
    def find_by_qualified_name(
        self, qualified_name: str
    ) -> "CodeGraphNode | None":
        """Convenience: resolve qname → uid, then find_by_uid."""
        ...

    @abstractmethod
    def find_all_by_qualified_name(
        self, qualified_name: str
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *qualified_name*.

        Unlike :meth:`find_by_qualified_name`, this returns every node
        with the given qualified_name — useful for detecting duplicates.
        """
        ...

    # ── Node label operations ─────────────────────────────────────

    @abstractmethod
    def get_labels(self, uid: str) -> set[str]:
        """Return labels (type tags) for a node by uid."""
        ...

    @abstractmethod
    def set_labels(self, uid: str, labels: list[str]) -> None:
        """Replace all labels on a node."""
        ...

    @abstractmethod
    def remove_labels(self, uid: str, labels: list[str]) -> None:
        """Remove specific labels from a node."""
        ...

    # ── Bulk queries ─────────────────────────────────────────────

    @abstractmethod
    def get_all_node_labels(self) -> list["dict[str, Any]"]:
        """Return qualified_name and labels for every node in the graph.

        Returns ``[{"qualified_name": str, "labels": list[str], "uid": str}]``.
        """
        ...

    @abstractmethod
    def find_nodes_with_labels(
        self, labels: list[str]
    ) -> list["dict[str, Any]"]:
        """Find nodes that carry ALL of the specified labels.

        Returns ``[{"qualified_name": str, "labels": list[str], "uid": str}]``.
        """
        ...

    @abstractmethod
    def count_all_nodes(self) -> int:
        """Return the total number of nodes in the graph."""
        ...

    # ── Node mutation ─────────────────────────────────────────────

    @abstractmethod
    def update_properties(
        self, uid: str, props: dict, *, add_labels: list[str] | None = None
    ) -> bool:
        """SET properties (and optionally add labels) on a node by uid."""
        ...

    @abstractmethod
    def delete_by_uid(self, uid: str) -> bool:
        """Delete a node (DETACH) by uid."""
        ...

    # ── Relationships ─────────────────────────────────────────────

    @abstractmethod
    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """MERGE a relationship between two nodes by uid.  Returns 0 or 1.

        Optionally sets *edge_properties* on the relationship.
        """
        ...

    @abstractmethod
    def merge_labeled_relationship(
        self,
        source_uid: str,
        source_label: str,
        rel_type: str,
        target_uid: str,
        target_label: str,
    ) -> None:
        """MERGE a relationship between two labeled nodes by uid.

        Used for memory-to-memory edges (SUPERSEDES, REFINES,
        CONTRADICTS) where uid alone isn't enough to disambiguate.
        """
        ...

    # ── Traversal ─────────────────────────────────────────────────

    @abstractmethod
    def get_ancestors(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES upward from uid.

        Returns ``[{"uid": str, "labels": list[str]}]``.
        """
        ...

    @abstractmethod
    def get_descendants(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES downward from uid."""
        ...

    # ── Tag queries ───────────────────────────────────────────────

    @abstractmethod
    def find_uids_by_tag(self, tag: str) -> list[str]:
        """Return all uids for nodes whose ``tags`` contain *tag*."""
        ...

    @abstractmethod
    def find_uids_by_tag_and_condition(
        self,
        tag: str,
        *,
        condition_clause: str = "",
        params: dict | None = None,
    ) -> list[str]:
        """Return uids for nodes with *tag* + optional condition."""
        ...

    # ── Related-node queries ──────────────────────────────────────

    @abstractmethod
    def find_related_nodes(
        self,
        target_uid: str,
        rel_pattern: str,
        *,
        source_labels: str | None = None,
    ) -> list[dict]:
        """Find source nodes that have relationship matching
        *rel_pattern* to the target node by *target_uid*.

        Returns ``[{"node": CodeGraphNode, "rel_type": str}]``.
        """
        ...

    # ── Full-text search ──────────────────────────────────────────

    @abstractmethod
    def search_fulltext(
        self,
        query: str,
        *,
        index_name: str,
        labels: str = "",
        tag: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search with optional label/tag filters.

        Falls back to CONTAINS if the index doesn't exist.
        """
        ...

    # ── Vector search ─────────────────────────────────────────────

    @abstractmethod
    def search_vector(
        self,
        embedding: list[float],
        *,
        index_name: str,
        labels: str = "",
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Vector similarity search.  Returns empty if unavailable."""
        ...

    # ── Scope-based reads ─────────────────────────────────────────

    @abstractmethod
    def get_by_tag(self, tag: "Tag") -> "LayerGraph":
        """Fetch all nodes with tag plus 1-hop neighbours."""
        ...

    @abstractmethod
    def get_by_source(self, source: str) -> "LayerGraph":
        """Fetch all nodes from a source project plus neighbours."""
        ...

    @abstractmethod
    def get_by_namespace(self, qualified_name: str) -> "LayerGraph":
        """Fetch a namespace and its composed entities."""
        ...

    @abstractmethod
    def get_by_compound(self, qualified_name: str) -> "LayerGraph":
        """Fetch a compound node and its 1-hop neighbours."""
        ...

    @abstractmethod
    def get_by_neighbourhood(self, qualified_name: str) -> "LayerGraph":
        """Fetch any node and its 1-hop neighbourhood."""
        ...

    @abstractmethod
    def get_by_kind(
        self, kind: str, tag: "Tag | None" = None
    ) -> "LayerGraph":
        """Fetch all nodes of a given kind."""
        ...

    @abstractmethod
    def get_hlr_subtree(self, uid: str, tag: str = "") -> "LayerGraph":
        """Fetch the full requirements subtree for an HLR."""
        ...

    # ── Flat queries ──────────────────────────────────────────────

    @abstractmethod
    def find_by_tag(
        self, node_type: type["CodeGraphNode"], tag: str
    ) -> list["CodeGraphNode"]:
        """Return nodes of *node_type* whose tags contain *tag*."""
        ...

    @abstractmethod
    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Return all nodes across all types whose tags contain *tag*."""
        ...

    @abstractmethod
    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Return all nodes matching *source*."""
        ...

    @abstractmethod
    def find_all_by_kind(
        self, kind: str, tag: str | None = None
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *kind* (and optionally *tag*)."""
        ...

    # ── Relationship traversal ────────────────────────────────────

    @abstractmethod
    def composed_children(
        self,
        node: "CodeGraphNode",
        child_type: type["CodeGraphNode"],
    ) -> list["CodeGraphNode"]:
        """Return children reachable via outgoing COMPOSES."""
        ...

    @abstractmethod
    def incoming_composers(
        self,
        node: "CodeGraphNode",
        composer_type: type["CodeGraphNode"] | None = None,
    ) -> list["CodeGraphNode"]:
        """Return nodes that COMPOSE *node* (incoming COMPOSES)."""
        ...

    @abstractmethod
    def outgoing_by_relation(
        self,
        node: "CodeGraphNode",
        relation_type: str,
        target_type: type["CodeGraphNode"] | None = None,
    ) -> list["CodeGraphNode"]:
        """Return nodes reachable via outgoing *relation_type* edges."""
        ...

    # ── Write ─────────────────────────────────────────────────────

    @abstractmethod
    def save_layer_graph(self, graph: "LayerGraph") -> None:
        """Persist a LayerGraph."""
        ...

    # ── Aggregation ──────────────────────────────────────────────

    @abstractmethod
    def count_all_nodes(self, tag: str | None = None) -> int:
        """Count all nodes in the graph, optionally filtered by *tag*."""
        ...

    @abstractmethod
    def find_nodes_with_labels(
        self, labels: list[str]
    ) -> list[dict]:
        """Find all nodes that carry ALL of the given Neo4j labels.

        Returns a list of dicts with keys ``uid``, ``qualified_name``,
        and ``labels`` (sorted).
        """
        ...

    @abstractmethod
    def count_relationships(
        self,
        rel_types: list[str],
        *,
        source_labels: list[str] | None = None,
        target_labels: list[str] | None = None,
        target_tag: str | None = None,
    ) -> int:
        """Count relationships whose type is in *rel_types*.

        Optional filters narrow the match to specific source node
        labels, target node labels, or a target node tag value.
        """
        ...
