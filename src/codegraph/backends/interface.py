"""Abstract storage backend interface for the codegraph knowledge graph.

Defines the contract that every backend (Neo4j, SQLite, Postgres, ...)
must implement.  The backend provides lifecycle management and exposes
injected repository instances for graph and memory operations.

All Cypher/SQL is sealed inside the repository implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode
    from codegraph.graph import LayerGraph
    from codegraph.persistence.repository import GraphRepository
    from codegraph.persistence.memory_repository import MemoryRepository
    from codegraph.persistence.requirements_repository import RequirementsRepository


log = __import__("logging").getLogger(__name__)


@dataclass
class EdgeDescriptor:
    """Portable description of a relationship.

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

    Provides lifecycle management and exposes injected repository
    instances.  All Cypher/SQL lives in the repository implementations,
    not on the backend itself.
    """

    # ═══════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def initialize(self, config: BackendConfig) -> None:
        """Set up the backend. Called once at application startup."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the storage layer is reachable and operational."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Tear down the connection (close driver, release resources).

        The backend instance remains usable — call :meth:`reconnect` to
        re-establish the connection.  The default implementation is a
        no-op; backends with persistent connections (e.g. Neo4j)
        override this.
        """
        pass

    @abstractmethod
    def reconnect(self) -> None:
        """Re-establish the connection, re-reading configuration from
        the environment.

        Useful in tests when environment variables change between
        ``disconnect()`` and ``reconnect()``.  The default
        implementation is a no-op.
        """
        pass
    # ═══════════════════════════════════════════════════════════════════
    # Repositories
    # ═══════════════════════════════════════════════════════════════════

    @property
    @abstractmethod
    def graph(self) -> "GraphRepository":
        """The code graph repository."""
        ...

    @property
    @abstractmethod
    def memory(self) -> "MemoryRepository":
        """The design memory repository."""
        ...

    @property
    @abstractmethod
    def requirements(self) -> "RequirementsRepository":
        """The requirements (HLR/LLR/test) repository."""
        ...

    @abstractmethod
    def wipe(self) -> None:
        """Delete ALL nodes and relationships from the backend.

        Destroys every CodeGraphNode, every relationship, every index,
        and every constraint managed by codegraph.  The backend itself
        remains operational — only the data is cleared.

        This is the nuclear option.  There is no undo.
        """
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Node CRUD (delegated to model layer)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def save(self, node: "CodeGraphNode") -> "CodeGraphNode":
        """Idempotent create-or-update by uid."""
        ...

    @abstractmethod
    def delete(self, node: "CodeGraphNode") -> None:
        """Delete the node after cascading to COMPOSES children."""
        ...

    @abstractmethod
    def get(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> "CodeGraphNode | None":
        """Get a single node by field filters."""
        ...

    @abstractmethod
    def find_all(
        self,
        node_type: type["CodeGraphNode"],
        **filters: Any,
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* matching field filters (or all)."""
        ...

    @abstractmethod
    def inflate(
        self,
        raw: Any,
        node_type: type["CodeGraphNode"],
    ) -> "CodeGraphNode":
        """Create a CodeGraphNode from a raw backend result row."""
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Relationship operations (delegated to model layer)
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
    # Bulk operations
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Save all nodes and relationships in a LayerGraph."""
        ...

    @abstractmethod
    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with tag plus 1-hop neighbors."""
        ...

    # ═══════════════════════════════════════════════════════════════════
    # Raw query (escape hatch)
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
        fit the repository model.

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
