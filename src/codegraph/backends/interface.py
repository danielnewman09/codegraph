"""Abstract storage backend interface for the codegraph knowledge graph.

Defines the contract that every backend (Neo4j, SQLite, Postgres, ...)
must implement.  All operations work with in-memory ``CodeGraphNode``
instances — the backend translates between Python objects and the
storage layer.

Registry-level query methods (``find_by_tag``, ``find_all_by_tag``,
``find_all_by_source``, ``find_all_by_kind``) use the **Template
Method** pattern: the public concrete method validates that all
registered node types declare the expected properties, then delegates
to a private abstract ``_impl`` method.  Backends only implement the
``_impl`` variants — validation lives in one place and cannot be
forgotten.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode



log = logging.getLogger(__name__)


@dataclass
class EdgeDescriptor:
    """Portable description of a relationship (replaces neomodel edge dicts).

    Attributes:
        relation_type: Relationship label (e.g. "COMPOSES", "INHERITS_FROM").
        target_uid: uid of the connected node.
        target_type: Class name of the connected node.
        is_outgoing: True for outgoing edges, False for incoming.
    """

    relation_type: str
    target_uid: str
    target_type: str
    is_outgoing: bool = True


@dataclass
class BackendConfig:
    """Base config. Subclassed per backend (Neo4jConfig, SQLiteConfig, ...)."""
    pass


class Backend(ABC):
    """Abstract storage backend for the codegraph knowledge graph.

    All operations work with in-memory ``CodeGraphNode`` instances.
    The backend translates between Python objects and the storage layer.

    Submodules map:
    - Lifecycle → connection.py
    - Node CRUD + queries → node_ops.py
    - Relationship operations → rel_ops.py
    - Bulk operations → bulk_ops.py
    """

    # ═══════════════════════════════════════════════════════════════════
    # Lifecycle (→ connection.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def initialize(self, config: BackendConfig) -> None:
        """Set up the backend. Called once at application startup."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the storage layer is reachable and operational."""
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Node CRUD (→ node_ops.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def save(self, node: "CodeGraphNode") -> "CodeGraphNode":
        """Idempotent create-or-update by uid.

        If ``uid`` is not set, computes it from ``_identity_fields`` +
        ``source``.  Uses MERGE (Neo4j) or INSERT OR REPLACE (SQLite).
        Returns the saved node with auto-generated fields populated.
        """
        ...

    @abstractmethod
    def delete(self, node: "CodeGraphNode") -> None:
        """Delete the node after cascading to COMPOSES children.

        Implementation must:
        1. Recursively delete composed children (depth-first, leaves first).
        2. Disconnect all remaining relationships on this node.
        3. Delete the node itself.
        """
        ...

    @abstractmethod
    def get(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> "CodeGraphNode | None":
        """Get a single node by arbitrary field filters.

        Example:
            backend.get(ClassNode, qualified_name="ns::Widget")
            backend.get(NamespaceNode, uid="abc123")
        """
        ...

    @abstractmethod
    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        """Create a CodeGraphNode from a raw backend result row.

        For Neo4j: inflates a Bolt node record.
        For SQLite: inflates a SQLAlchemy Row.
        """
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Node queries — Template Method
    # ═══════════════════════════════════════════════════════════════════
    #
    # Public concrete methods validate that all registered node types
    # declare the expected properties, then delegate to private abstract
    # ``_impl`` methods.  Backends only implement the ``_impl`` variants.

    # ── find_by_tag ──────────────────────────────────────────────────

    def find_by_tag(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* whose ``tags`` array contains *tag*.

        Validates that ``node_type`` declares a ``tags`` property.
        Raises ``TypeError`` if it does not.
        """
        _require_property(node_type, "tags")
        return self._find_by_tag_impl(node_type, tag)

    @abstractmethod
    def _find_by_tag_impl(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        ...

    # ── find_all_by_tag ────────────────────────────────────────────

    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Return all nodes across all registered types whose ``tags`` contain *tag*.

        Validates that every registered node type declares a ``tags``
        property.  Raises ``TypeError`` if any type does not.
        """
        _require_registry_property("tags")
        return self._find_all_by_tag_impl(tag)

    @abstractmethod
    def _find_all_by_tag_impl(self, tag: str) -> list["CodeGraphNode"]:
        ...

    # ── find_all_by_source ──────────────────────────────────────────

    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Return all nodes across all registered types matching *source*.

        Validates that every registered node type declares a ``source``
        property.  Raises ``TypeError`` if any type does not.
        """
        _require_registry_property("source")
        return self._find_all_by_source_impl(source)

    @abstractmethod
    def _find_all_by_source_impl(self, source: str) -> list["CodeGraphNode"]:
        ...

    # ── find_all_by_kind ────────────────────────────────────────────

    def find_all_by_kind(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *kind* (and optionally *tag*).

        Validates that every registered node type declares a ``kind``
        property.  When *tag* is provided, also validates that every
        type declares a ``tags`` property.  Raises ``TypeError`` if
        any type does not.
        """
        _require_registry_property("kind")
        if tag is not None:
            _require_registry_property("tags")
        return self._find_all_by_kind_impl(kind, tag)

    @abstractmethod
    def _find_all_by_kind_impl(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Relationship operations (→ rel_ops.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def connect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Create a relationship between two saved nodes."""
        ...

    @abstractmethod
    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Remove a single relationship between two nodes."""
        ...

    @abstractmethod
    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return all nodes reachable via outgoing COMPOSES edges."""
        ...

    @abstractmethod
    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return ALL edges (incoming + outgoing) from node."""
        ...

    @abstractmethod
    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges from node."""
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Bulk operations (→ bulk_ops.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Save all nodes and relationships in a LayerGraph.

        Replaces ``LayerGraph.to_neo4j()``.  The backend must:
        1. Save every node (idempotent by uid).
        2. Connect COMPOSES edges (building the composition tree).
        3. Connect reference edges (non-COMPOSES relationships).
        """
        ...

    @abstractmethod
    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with tag plus 1-hop neighbors.

        Replaces the fetch portion of ``LayerGraph.from_neo4j()``.
        The returned list must include both tag-matched seed nodes and
        their immediate neighbors.

        ``LayerGraph`` tree construction is pure Python — the backend
        only provides the flat node list.
        """
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Raw query (escape hatch → connection.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Execute a backend-native query string.

        For Neo4j: Cypher.  For SQLite: SQL.  Use only for stats,
        aggregation, migrations, and complex traversals that don't
        fit the CRUD model.

        Returns ``(rows, columns)`` where *rows* is a list of dicts
        (each keyed by column name) and *columns* is the ordered list
        of column names.
        """
        ...

    def verify_connectivity(self) -> bool:
        """Check that the backend is reachable (safe to call before init).

        Wraps :meth:`health_check` in a try/except, returning ``False``
        instead of raising on connection failure.
        """
        try:
            return self.health_check()
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ══════════════════════════════════════════════════════════════════════════


def _require_property(node_type: type, prop: str) -> None:
    """Raise ``TypeError`` if *node_type* does not declare *prop*.

    Called by ``find_by_tag`` to validate a single type before querying.
    """
    props = node_type.defined_properties()
    if prop not in props:
        raise TypeError(
            f"{node_type.__name__} does not declare a '{prop}' property. "
            f"Declared properties: {sorted(props)}"
        )


def _require_registry_property(prop: str) -> None:
    """Raise ``TypeError`` if any registered node type lacks *prop*.

    Called by registry-level queries (``find_all_by_tag``,
    ``find_all_by_source``, ``find_all_by_kind``) before delegating
    to the backend ``_impl``.
    """

    missing: list[str] = []
    from codegraph.models.tags import CodeGraphNode  # lazy — avoids circular import with tags.py
    for node_cls in list(CodeGraphNode._registry.values()):
        if prop not in node_cls.defined_properties():
            missing.append(node_cls.__name__)
    if missing:
        raise TypeError(
            f"find_all_by_{prop}: these registered types lack a "
            f"'{prop}' property: {sorted(missing)}. "
            f"Add '{prop}' to the type's property declarations, or "
            f"remove the type from CodeGraphNode._registry if it should "
            f"not participate in {prop}-based queries."
        )
