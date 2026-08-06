"""SQLite backend — composes connection, config, and repository implementations.

Mirrors ``codegraph.backends.neo4j.Neo4jBackend``.  Selecting it via
``CODEGRAPH_BACKEND=sqlite`` must give the same application behavior as
the Neo4j backend: node CRUD, relationships, LayerGraph round-trips,
memory + requirements repositories, full-text and vector search — all
backed by a single SQLite file.

Usage::

    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
    from codegraph.backends import set_backend

    backend = SqliteBackend(SqliteConfig(path="codegraph.sqlite3"))
    set_backend(backend)
    backend.initialize(SqliteConfig(path="codegraph.sqlite3"))
"""

from __future__ import annotations

from typing import Any, override

import sqlalchemy as sa

from codegraph.backends.interface import Backend, BackendConfig, EdgeDescriptor
from codegraph.backends.sqlite.bulk_ops import SqliteBulkOps
from codegraph.backends.sqlite.config import SqliteConfig
from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.backends.sqlite.graph_repository import SqliteGraphRepository
from codegraph.backends.sqlite.memory_repository import SqliteMemoryRepository
from codegraph.backends.sqlite.node_ops import SqliteNodeOps
from codegraph.backends.sqlite.rel_ops import SqliteRelOps
from codegraph.backends.sqlite.requirements_repository import (
    SqliteRequirementsRepository,
)
from codegraph.backends.sqlite.schema import ensure_schema
from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.memory_repository import MemoryRepository
from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.requirements_repository import RequirementsRepository


class SqliteBackend(Backend):
    """SQLite storage backend for the codegraph knowledge graph.

    Composes:
    - ``_conn`` — SQLAlchemy engine lifecycle + raw SQL
    - ``_graph`` — SqliteGraphRepository (code graph operations)
    - ``_memory`` — SqliteMemoryRepository (design memory operations)
    - ``_requirements`` — SqliteRequirementsRepository (HLR/LLR/test ops)
    """

    def __init__(self, config: SqliteConfig | None = None):
        if config is None:
            config = SqliteConfig.from_env()
        self._config = config
        self._conn = SqliteConnection(config)
        self._graph = SqliteGraphRepository(self._conn)
        self._memory = SqliteMemoryRepository(self._conn, self._graph)
        self._requirements = SqliteRequirementsRepository(self._conn, self._graph)
        self._node_ops = SqliteNodeOps(self._conn)
        self._rel_ops = SqliteRelOps(self._conn)
        self._bulk_ops = SqliteBulkOps(self._conn, self._node_ops, self._rel_ops)
        self._initialized = False

    def _ensure(self) -> None:
        """Lazily create the schema on first use.

        Keeps the backend usable without an explicit ``initialize()``
        (matching the Neo4j backend's lazy driver), while
        ``initialize()`` remains the explicit startup path.
        """
        if self._initialized:
            return
        ensure_schema(self._conn.engine)
        self._initialized = True

    # ── Lifecycle ────────────────────────────────────────────────────

    @override
    def initialize(self, config: BackendConfig) -> None:
        """Create (or migrate) the schema.  Called once at startup."""
        ensure_schema(self._conn.engine)
        self._initialized = True

    @override
    def apply_schema(self) -> None:
        """SQLite tables are created by :meth:`initialize` / lazily on write."""
        return None

    @override
    def health_check(self) -> bool:
        self._ensure()
        return self._conn.health_check()

    @override
    def close(self) -> None:
        """Dispose the engine and close all pooled connections."""
        self._conn.close()
        self._initialized = False

    @override
    def reconnect(self) -> None:
        """Re-establish the connection with fresh environment config."""
        self._conn.reconnect()
        self._graph = SqliteGraphRepository(self._conn)
        self._memory = SqliteMemoryRepository(self._conn, self._graph)
        self._requirements = SqliteRequirementsRepository(self._conn, self._graph)
        self._node_ops = SqliteNodeOps(self._conn)
        self._rel_ops = SqliteRelOps(self._conn)
        self._bulk_ops = SqliteBulkOps(self._conn, self._node_ops, self._rel_ops)
        self._initialized = False
        self._ensure()

    # ── Repositories ────────────────────────────────────────────────

    @property
    @override
    def graph(self) -> GraphRepository:
        self._ensure()
        return self._graph

    @property
    @override
    def memory(self) -> MemoryRepository:
        self._ensure()
        return self._memory

    @property
    @override
    def requirements(self) -> RequirementsRepository:
        self._ensure()
        return self._requirements

    # ── Node CRUD (model-layer delegation) ─────────────────────────

    @override
    def save(self, node: CodeGraphNode) -> CodeGraphNode:
        self._ensure()
        return self._node_ops.save(node)

    @override
    def delete(self, node: CodeGraphNode) -> None:
        self._ensure()
        self._node_ops.delete(node)

    @override
    def get(
        self, node_type: type[CodeGraphNode], **filters: Any
    ) -> CodeGraphNode | None:
        self._ensure()
        return self._node_ops.get(node_type, **filters)

    @override
    def find_all(
        self, node_type: type[CodeGraphNode], **filters: Any
    ) -> list[CodeGraphNode]:
        self._ensure()
        return self._node_ops.find_all(node_type, **filters)

    @override
    def inflate(self, raw: Any, node_type: type[CodeGraphNode]) -> CodeGraphNode:
        self._ensure()
        return self._node_ops.inflate(raw, node_type)

    # ── Relationship operations (model-layer delegation) ──────────

    @override
    def connect(
        self, source: CodeGraphNode, rel_type: str, target: CodeGraphNode
    ) -> None:
        self._ensure()
        self._rel_ops.connect(source, rel_type, target)

    @override
    def disconnect(
        self, source: CodeGraphNode, rel_type: str, target: CodeGraphNode
    ) -> None:
        self._ensure()
        self._rel_ops.disconnect(source, rel_type, target)

    @override
    def get_composed_children(self, node: CodeGraphNode) -> list[CodeGraphNode]:
        self._ensure()
        return self._rel_ops.get_composed_children(node)

    @override
    def get_all_edges(self, node: CodeGraphNode) -> list[EdgeDescriptor]:
        self._ensure()
        return self._rel_ops.get_all_edges(node)

    @override
    def get_all_edges_outgoing(self, node: CodeGraphNode) -> list[EdgeDescriptor]:
        self._ensure()
        return self._rel_ops.get_all_edges_outgoing(node)

    # ── Bulk operations ──────────────────────────────────────────

    @override
    def bulk_save(self, layer_graph: LayerGraph) -> None:
        self._ensure()
        self._bulk_ops.bulk_save(layer_graph)

    @override
    def bulk_load_by_tag(self, tag: str) -> list[CodeGraphNode]:
        self._ensure()
        return self._bulk_ops.bulk_load_by_tag(tag)

    # ── Raw query ───────────────────────────────────────────────────

    @override
    def wipe(self) -> None:
        """Drop every table and recreate the schema."""
        self._ensure()
        with self._conn.engine.begin() as conn:
            for table in ("node_embeddings", "fts_nodes", "edges", "node_tags", "node_labels", "nodes"):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        ensure_schema(self._conn.engine)
        from codegraph.backends.sqlite.search import invalidate_vector_index

        invalidate_vector_index(self._conn)

    @override
    def execute_raw(
        self,
        query: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        self._ensure()
        return self._conn.execute_raw(query, params)
