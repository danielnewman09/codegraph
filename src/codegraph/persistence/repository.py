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

    @abstractmethod
    def delete_by_source(self, source: str) -> int:
        """Delete ALL nodes carrying *source* in one aggregate operation.

        Edges cascade (DETACH semantics).  Never per-node round trips —
        backends implement this as a single native statement (Cypher
        ``DETACH DELETE`` / SQL ``DELETE`` with FK cascade).

        Returns:
            The number of nodes deleted.
        """
        ...

    @abstractmethod
    def delete_by_uids(self, uids: list[str]) -> int:
        """Delete all nodes with the given uids in one aggregate operation.

        Edges cascade.  Idempotent — uids that don't exist are ignored.

        Returns:
            The number of nodes deleted.
        """
        ...

    # ── Canonical-key operations (key-neutral; WP3.1) ──────────────
    #
    # New production code must prefer these over the UID-named methods;
    # the UID-named methods remain as compatibility wrappers for the
    # legacy path.  ``resolve_uid(qualified_name)`` — which selects an
    # arbitrary first match — must NOT be used for canonical migration.

    @abstractmethod
    def find_by_key(self, key: str) -> "CodeGraphNode | None":
        """Find any node by its canonical key (``cg:v1:...``)."""
        ...

    def resolve_key(self, identity) -> str:
        """Resolve an identity (``CanonicalIdentity``) to its canonical key.

        Canonical keys are deterministic functions of the identity, so
        the base implementation computes it directly — no backend query.
        Backends may override to additionally verify the node exists.
        """
        return identity.key()

    @abstractmethod
    def merge_relationship_by_key(
        self,
        source_key: str,
        rel_type: str,
        target_key: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """MERGE a relationship between two nodes by canonical key.

        Both endpoints must already exist as keyed nodes.  Returns 1 if
        both resolve, 0 otherwise.
        """
        ...

    @abstractmethod
    def delete_by_key(self, key: str) -> bool:
        """Delete a node (DETACH semantics) by canonical key."""
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
    def list_sources(self) -> list[dict]:
        """Return distinct ``source`` values with node counts.

        Returns a list of ``{"source": str, "count": int}`` sorted by
        count descending.  Used to enumerate indexed source projects
        (e.g. ``cppreference``, ``boost``, a project's own code).
        """
        ...

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

    # ── Discovery queries (backend-agnostic read API) ──────────────
    #
    # The discovery tools (search / compound / member / namespace /
    # inheritance / callers-callees) used to issue raw Cypher through
    # ``Backend.execute_raw`` — which only works on the Neo4j backend.
    # These methods are the backend-agnostic equivalents: each backend
    # implements them natively (Cypher for Neo4j, SQL for SQLite) and
    # the tool layer never sees a query string.

    @abstractmethod
    def search_compounds(
        self,
        query: str,
        *,
        source: str | None = None,
        kind: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        """Search compounds by case-insensitive qualified_name substring.

        Returns slim dicts with keys ``qualified_name``, ``name``,
        ``kind``, ``source``, and ``brief_description``, ordered by
        ``qualified_name`` ascending.
        """
        ...

    @abstractmethod
    def get_compound(self, qualified_name: str) -> dict | None:
        """Fetch a compound by qualified_name plus its member children.

        Returns ``None`` when the compound is not found.  Otherwise a
        slim compound dict (``qualified_name``, ``name``, ``kind``,
        ``source``, ``brief_description``) extended with ``members``
        (a list of slim member dicts) and ``member_count``.
        """
        ...

    @abstractmethod
    def get_member(self, qualified_name: str) -> dict | None:
        """Fetch a single member by qualified_name.

        Returns ``None`` when not found.  Otherwise a slim member dict
        with keys ``qualified_name``, ``name``, ``kind``, ``visibility``,
        ``type_signature``, ``argsstring``, and ``brief_description``.
        """
        ...

    @abstractmethod
    def browse_namespace(
        self, namespace: str, limit: int = 50
    ) -> list[dict]:
        """List compounds whose qualified_name starts with *namespace*.

        Returns slim compound dicts ordered by qualified_name ascending.
        """
        ...

    @abstractmethod
    def list_namespaces(self) -> list[dict]:
        """List namespace nodes with entity + sub-namespace counts.

        Returns dicts with keys ``qualified_name``, ``name``,
        ``entity_count``, and ``sub_namespace_count``, ordered by
        ``entity_count`` descending.
        """
        ...

    @abstractmethod
    def find_inheritance(self, qualified_name: str) -> dict:
        """Return the inheritance hierarchy for a compound.

        Returns ``{"parents": [...], "children": [...]}`` where each
        entry is ``{"qualified_name": str, "kind": str}``.  Parents are
        reached via outgoing ``INHERITS_FROM`` / ``REALIZES`` edges;
        children via the inverse.
        """
        ...

    @abstractmethod
    def find_callers_callees(self, qualified_name: str) -> dict:
        """Return callers and callees for a member.

        Returns ``{"callers": [...], "callees": [...]}`` where each
        entry is ``{"qualified_name": str, "kind": str}``.  Callees are
        reached via outgoing ``INVOKES`` edges; callers via the inverse.
        """
        ...

    @abstractmethod
    def find_compounds_by_qualified_names(
        self, names: list[str]
    ) -> list[dict]:
        """Return slim compound dicts whose qualified_name is in *names*.

        Preserves no particular order (backends may return in natural
        qualified_name order).  Used for container/type seeding.
        """
        ...

    @abstractmethod
    def find_members(
        self,
        *,
        source: str | None = None,
        kind: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return slim member dicts filtered by ``source`` and/or ``kind``.

        Either filter may be omitted (``None``) to match all members.
        """
        ...

    @abstractmethod
    def list_dependency_compounds(
        self,
        *,
        source: str = "all",
        kind: str | None = None,
        query: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """List dependency-API compounds (``cppreference`` / ``boost``).

        ``source`` may be ``"all"`` (both cppreference and boost), a
        single source name, or any other value.  ``query`` is an
        optional case-insensitive qualified_name substring; ``kind``
        optionally narrows the node kind.  Returns slim compound dicts
        ordered by qualified_name ascending.
        """
        ...


# ══════════════════════════════════════════════════════════════════════════
# Discovery row shapers — shared slim-dict shapes for the backend-agnostic
# discovery read methods.  The ``name`` fallback to the last qualified-name
# segment is applied in the tool layer, not here.
# ══════════════════════════════════════════════════════════════════════════


def slim_compound_row(record: dict) -> dict:
    """Shape a backend row into the slim compound dict."""
    return {
        "qualified_name": record["qualified_name"],
        "name": record.get("name"),
        "kind": record["kind"],
        "source": record.get("source"),
        "brief_description": record.get("brief_description"),
    }


def slim_member_row(record: dict) -> dict:
    """Shape a backend row into the slim member dict."""
    return {
        "qualified_name": record["qualified_name"],
        "name": record.get("name"),
        "kind": record["kind"],
        "visibility": record.get("visibility"),
        "type_signature": record.get("type_signature"),
        "argsstring": record.get("argsstring"),
        "brief_description": record.get("brief_description"),
    }


def namespace_row(record: dict) -> dict:
    """Shape a backend row into the namespace summary dict."""
    return {
        "qualified_name": record["qualified_name"],
        "name": record.get("name"),
        "entity_count": record["entity_count"],
        "sub_namespace_count": record["sub_namespace_count"],
    }


def related_row(record: dict) -> dict:
    """Shape a backend row into a related-node entry (parents/children)."""
    return {
        "qualified_name": record["qualified_name"],
        "kind": record["kind"],
    }
