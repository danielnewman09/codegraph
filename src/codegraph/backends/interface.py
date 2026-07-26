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
