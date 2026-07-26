# Multi-Backend Architecture

> **Status**: Draft | **Date**: 2026-07-26  
> **Goal**: Decouple codegraph from Neo4j, support multiple storage backends (SQLite, Postgres, etc.)

---

## 1. Problem Statement

Codegraph is tightly coupled to Neo4j through **three layers**:

| Layer | Mechanism | Files |
|-------|-----------|-------|
| **Model definitions** | `neomodel.StructuredNode`, `RelationshipTo/From`, `StringProperty`, `ArrayProperty`, `UniqueIdProperty` | `models/compound.py`, `member.py`, `namespace.py`, `test.py`, `implementation.py`, `file.py`, `literal.py`, `parameter.py`, `tags.py` |
| **Runtime operations** | `db.cypher_query()`, `.nodes.get_or_none()`, `.all()`, `.connect()`, `.disconnect()`, MERGE Cypher, raw `session.run()` | `tags.py` (69 refs), `graph/__init__.py` (34 refs), `tools/discovery.py`, `tools/query.py` |
| **Raw Cypher queries** | Direct `MATCH`/`MERGE` strings | `codegraph_mine/` (~40 queries), `codegraph_memory/` (~20 queries), `scripts/`, `tools/` |

Changing the storage backend requires touching all three layers.  A SQLite-backed codegraph needs a different approach to properties, relationships, queries, and identity.

---

## 2. Proposed Architecture

### 2.1 Directory Structure

```
codegraph/
├── backends/
│   ├── __init__.py              # set_backend(), get_backend()
│   ├── interface.py             # Backend ABC + BackendConfig + EdgeDescriptor
│   │
│   ├── neo4j/                    # Existing logic, extracted & organised
│   │   ├── __init__.py           # Neo4jBackend — composes sub-ops
│   │   ├── connection.py         # Driver mgmt, session(), cypher_query()
│   │   ├── config.py             # Neo4jConfig (Bolt URI, credentials)
│   │   ├── node_ops.py           # save(), delete(), get(), find_by_*(), inflate()
│   │   ├── rel_ops.py            # connect(), disconnect(), get_related(), get_all_edges()
│   │   └── bulk_ops.py           # bulk_save(), bulk_load_by_tag()
│   │
│   ├── sqlite/                   # New backend
│   │   ├── __init__.py           # SQLiteBackend
│   │   ├── connection.py         # SQLAlchemy engine + session factory
│   │   ├── config.py             # SQLiteConfig (db path)
│   │   ├── node_ops.py           # save(), delete(), get(), find_by_*(), inflate()
│   │   ├── rel_ops.py            # connect(), disconnect(), get_related(), get_all_edges()
│   │   ├── bulk_ops.py           # bulk_save(), bulk_load_by_tag()
│   │   └── orm.py                # SQLAlchemy Table/Model definitions
│   │
│   └── postgres/                 # Future backend (same 6 files)
│
├── models/                       # UNCHANGED in Phase 1—2
│   └── tags.py                   # CodeGraphNode delegates to get_backend()
│
├── persistence/
│   ├── repository.py             # GraphRepository — takes Backend in __init__
│   └── docker.py                 # UNCHANGED (infrastructure)
│   # DELETED: connection.py, config.py → moved to backends/neo4j/
│
├── graph/
│   └── __init__.py               # LayerGraph.to_backend(), from_backend()
```

**Principle**: every backend has the same 5–6 sub-modules, each with a single responsibility and a direct counterpart in other backends.

### 2.2 Sub-module Responsibilities

| Sub-module | Responsibility | Neo4j implementation | SQLite implementation |
|---|---|---|---|
| `connection.py` | Driver/engine lifecycle, raw query execution, health check | Wraps `neomodel.db` + `neo4j.Driver` | Manages `sqlalchemy.Engine` + session factory |
| `config.py` | Backend-specific config (URL, credentials, paths) | `bolt://host:port`, user, password | `sqlite:///path/to/codegraph.db` |
| `node_ops.py` | Node CRUD: save, delete, get by field, find by tag/source/kind, inflate | MERGE Cypher, DETACH DELETE, neomodel queries | `INSERT OR REPLACE`, `DELETE`, SQLAlchemy queries, Row → CodeGraphNode |
| `rel_ops.py` | Relationship operations: connect, disconnect, walk edges | neomodel `.connect()`/`.disconnect()`/`.all()` | Join-table INSERT/DELETE, JOIN queries |
| `bulk_ops.py` | Bulk save/load LayerGraph | Batch MERGE + connect, multi-hop tag fetch | Batch INSERT in transaction, CTE-based tag loads |
| `orm.py` | SQLAlchemy declarative mappings | N/A (Neo4j uses neomodel on model classes) | SQLAlchemy `Table`/mapper for each CodeGraphNode subclass |

---

## 3. The `Backend` Interface

All 15 abstract methods.  Each backend implements this contract.

```python
# codegraph/backends/interface.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.models.tags import CodeGraphNode
    from codegraph.graph import LayerGraph


@dataclass
class EdgeDescriptor:
    """Portable description of a relationship (replaces neomodel edge dicts)."""
    relation_type: str       # e.g. "COMPOSES", "INHERITS_FROM"
    target_uid: str          # uid of the connected node
    target_type: str         # class name of the connected node
    is_outgoing: bool = True


@dataclass
class BackendConfig:
    """Base config. Subclassed per backend (Neo4jConfig, SQLiteConfig, ...)."""
    pass


class Backend(ABC):
    """Abstract storage backend for the codegraph knowledge graph.

    All operations work with in-memory ``CodeGraphNode`` instances.
    The backend translates between Python objects and the storage layer.
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
    # Node queries (→ node_ops.py)
    # ═══════════════════════════════════════════════════════════════════

    @abstractmethod
    def find_by_tag(
        self,
        node_type: type["CodeGraphNode"],
        tag: str,
    ) -> list["CodeGraphNode"]:
        """Return all nodes of *node_type* whose ``tags`` array contains *tag*."""
        ...

    @abstractmethod
    def find_all_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Return all nodes across all registered types whose ``tags`` contain *tag*."""
        ...

    @abstractmethod
    def find_all_by_source(self, source: str) -> list["CodeGraphNode"]:
        """Return all nodes across all types matching *source*."""
        ...

    @abstractmethod
    def find_all_by_kind(
        self,
        kind: str,
        tag: str | None = None,
    ) -> list["CodeGraphNode"]:
        """Return all nodes matching *kind* (and optionally *tag*)."""
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
        """Create a relationship between two saved nodes.

        The backend uses the source node's class attributes to find the
        correct relationship manager / join table for *rel_type* with
        the target's concrete type.
        """
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
        """Return all nodes reachable via outgoing COMPOSES edges.

        Used by CodeGraphNode.walk_composes() and delete cascade.
        """
        ...

    @abstractmethod
    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return ALL edges (incoming + outgoing) from *node*.

        Used by CodeGraphNode.walk_edges() for graph expansion.
        """
        ...

    @abstractmethod
    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges from *node*.

        Used by CodeGraphNode.serialize_edges() — excludes incoming
        edges to avoid duplicating relationships in exports.
        """
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
        """Load all nodes with *tag* plus 1-hop neighbors.

        Replaces the fetch portion of ``LayerGraph.from_neo4j()``.
        The returned list must include both tag-matched seed nodes and
        their immediate neighbors (nodes connected by any edge type).

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
    ) -> tuple[list[list], dict]:
        """Execute a backend-native query string.

        For Neo4j: Cypher.  For SQLite: SQL.  Use only for stats,
        aggregation, migrations, and complex traversals that don't
        fit the CRUD model.

        Returns ``(rows, metadata)`` — same shape as neomodel's
        ``db.cypher_query()`` for backward compatibility during migration.
        """
        ...
```

### 3.1 Backend Registry

```python
# codegraph/backends/__init__.py

_current_backend: Backend | None = None

def set_backend(backend: Backend) -> None:
    """Configure the active backend. Call once at startup."""
    global _current_backend
    _current_backend = backend

def get_backend() -> Backend:
    """Return the currently configured backend."""
    if _current_backend is None:
        raise RuntimeError(
            "No backend configured. Call codegraph.backends.set_backend() "
            "or set the CODEGRAPH_BACKEND environment variable."
        )
    return _current_backend
```

Models and tools import `get_backend()` — never a specific backend class.

---

## 4. How `CodeGraphNode` Delegates

Currently `CodeGraphNode` (in `models/tags.py`) has ~69 Neo4j-specific references.
After Phase 1, every database-touching method becomes a one-line delegation:

```python
# codegraph/models/tags.py — key method changes

class CodeGraphNode(metaclass=_CodeGraphNodeMeta):

    @classmethod
    def fetch_by_tag(cls, tag: str) -> list["CodeGraphNode"]:
        if "tags" not in cls.defined_properties():
            return []
        from codegraph.backends import get_backend
        return get_backend().find_by_tag(cls, tag)

    @classmethod
    def fetch_all_by_tag(cls, tag: str) -> list["CodeGraphNode"]:
        from codegraph.backends import get_backend
        return get_backend().find_all_by_tag(tag)

    @classmethod
    def fetch_all_by_source(cls, source: str) -> list["CodeGraphNode"]:
        from codegraph.backends import get_backend
        return get_backend().find_all_by_source(source)

    @classmethod
    def fetch_all_by_kind(
        cls, kind: str, tag: str | None = None
    ) -> list["CodeGraphNode"]:
        from codegraph.backends import get_backend
        return get_backend().find_all_by_kind(kind, tag)

    def _save(self) -> "CodeGraphNode":
        from codegraph.backends import get_backend
        props = type(self).defined_properties()
        if "qualified_name" in props and not getattr(self, "qualified_name", ""):
            self.qualified_name = self._compute_qualified_name()
        return get_backend().save(self)

    def _delete(self) -> "CodeGraphNode":
        from codegraph.backends import get_backend
        get_backend().delete(self)
        return self

    def walk_composes(self) -> list["CodeGraphNode"]:
        if not hasattr(self, "element_id_property"):
            return []
        from codegraph.backends import get_backend
        return get_backend().get_composed_children(self)

    def walk_edges(self) -> list[dict]:
        from codegraph.backends import get_backend
        edges = get_backend().get_all_edges(self)
        return [
            {
                "relation_type": e.relation_type,
                "target_uid": e.target_uid,
                "target_type": e.target_type,
                "is_outgoing": e.is_outgoing,
            }
            for e in edges
        ]

    def serialize_edges(self) -> list[dict]:
        from codegraph.backends import get_backend
        edges = get_backend().get_all_edges_outgoing(self)
        return [
            {
                "relation_type": e.relation_type,
                "target_uid": e.target_uid,
                "target_type": e.target_type,
            }
            for e in edges
        ]
```

`find_relationship_manager()` moves into `backends/neo4j/rel_ops.py` as a private
helper — callers now use `backend.connect()` / `backend.disconnect()` instead.

---

## 5. The `GraphRepository` Façade

`GraphRepository` stays but becomes backend-agnostic.  It takes a `Backend` in its
constructor and delegates all data access through it.  The `_build_layer_graph()`
tree-construction logic stays — it's pure Python.

```python
class GraphRepository:
    """Data access — scope-based queries, delegates to Backend."""

    def __init__(self, backend: Backend):
        self._backend = backend

    def get_by_tag(self, tag: str) -> LayerGraph:
        seeds = self._backend.find_all_by_tag(tag)
        return self._build_layer_graph(seeds)

    def get_by_namespace(self, qualified_name: str) -> LayerGraph:
        ns = self._backend.get(
            NamespaceNode, qualified_name=qualified_name
        )
        if ns is None:
            return LayerGraph(tags=frozenset({"design"}))
        seeds = [ns] + self._backend.get_composed_children(ns)
        return self._build_layer_graph(seeds)

    def get_by_compound(self, qualified_name: str) -> LayerGraph:
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = self._backend.get(node_cls, qualified_name=qualified_name)
            if node is not None:
                return self._build_layer_graph([node])
        return LayerGraph(tags=frozenset({"design"}))

    def get_by_neighbourhood(self, qualified_name: str) -> LayerGraph:
        # ... same pattern — find node via backend.get(), then build

    def get_by_kind(self, kind: str, tag: str | None = None) -> LayerGraph:
        seeds = self._backend.find_all_by_kind(kind, tag=tag)
        return self._build_layer_graph(seeds)

    def save_layer_graph(self, graph: LayerGraph) -> None:
        self._backend.bulk_save(graph)

    # _build_layer_graph() — UNCHANGED, pure Python
```

---

## 6. LayerGraph Changes

Two methods change — the rest stays pure Python.

```python
class LayerGraph:

    def to_backend(self, backend: Backend) -> None:
        """Persist to any backend (replaces to_neo4j)."""
        backend.bulk_save(self)

    @classmethod
    def from_backend(cls, backend: Backend, tag: str) -> "LayerGraph":
        """Load from any backend (replaces from_neo4j)."""
        matched_nodes = backend.find_all_by_tag(tag)

        # Expand 1-hop neighbors (same logic as current from_neo4j,
        # but using backend.get() + backend.get_all_edges() instead of
        # neomodel .nodes.get_or_none() + walk_edges()).

        # ... then build CompositeEntry tree (unchanged) ...

    # to_neo4j(), from_neo4j() → deprecated, delegate to to_backend/from_backend
```

---

## 7. Neo4j Backend Sub-modules (Detailed)

### 7.1 `backends/neo4j/connection.py`

**Migrated from**: `persistence/connection.py` (entire file, 155 lines)

```python
"""Neo4j driver lifecycle — wraps neomodel's db object."""

class Neo4jConnection:
    def __init__(self, config: Neo4jConfig): ...
    def ensure_driver(self) -> None: ...
    def get_session(self): ...
    def execute_raw(self, query, params): ...
    def health_check(self) -> bool: ...
```

All existing `get_session()`, `cypher_query()`, `verify_connectivity()`,
`require_connection()`, and `_ensure_driver()` move here verbatim.
The `Neo4jUnavailableError` moves too.

### 7.2 `backends/neo4j/config.py`

**Migrated from**: `persistence/config.py` (entire file, 17 lines)

```python
@dataclass
class Neo4jConfig(BackendConfig):
    uri: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "Neo4jConfig": ...
```

### 7.3 `backends/neo4j/node_ops.py`

**Migrated from**: `tags.py:_save`, `tags.py:_delete`, `tags.py:fetch_by_tag`,
`tags.py:fetch_all_by_*`, `memory/models/relationships.py:_inflate_code_node`

```python
class Neo4jNodeOps:
    def __init__(self, conn: Neo4jConnection): ...

    def save(self, node: CodeGraphNode) -> CodeGraphNode:
        """
        Extracted from CodeGraphNode._save() (~60 lines):
        - Compute uid from _identity_fields + source
        - Deflate properties (skip empty values)
        - MERGE (n:Label1:Label2 {uid: $uid}) SET n += $props RETURN n
        - Hydrate element_id_property for subsequent updates
        """

    def delete(self, node: CodeGraphNode) -> None:
        """
        Extracted from CodeGraphNode._delete():
        - Cascade: delete all COMPOSES children first
        - Disconnect remaining relationships (to clear caches)
        - DETACH DELETE via StructuredNode.delete()
        """

    def get(self, node_type, **filters) -> CodeGraphNode | None:
        """neomodel's .nodes.get_or_none(**filters) or .nodes.filter().first()"""

    def find_by_tag(self, node_type, tag) -> list[CodeGraphNode]:
        """MATCH (n:{label}) WHERE $tag IN n.tags RETURN n → .inflate()"""

    def find_all_by_tag(self, tag) -> list[CodeGraphNode]:
        """Loop find_by_tag across _registry"""

    def find_all_by_source(self, source) -> list[CodeGraphNode]:
        """Loop .nodes.filter(source=source) across _registry"""

    def find_all_by_kind(self, kind, tag) -> list[CodeGraphNode]:
        """Loop .nodes.filter(kind=kind) + optional tag filter"""

    def inflate(self, raw, node_type) -> CodeGraphNode:
        """Determine correct class from Neo4j labels, call .inflate()"""
```

Each method is extracted from exactly one existing code location.
The extraction is mechanical — copy the method body, replace `self` → `node`,
replace `cls` → `node_type`, replace `db.cypher_query` → `self._conn.execute_raw`.

### 7.4 `backends/neo4j/rel_ops.py`

**Migrated from**: `tags.py:walk_composes`, `tags.py:walk_edges`,
`tags.py:serialize_edges`, `tags.py:find_relationship_manager`, and
`graph/__init__.py` (connect/disconnect fallback logic)

```python
class Neo4jRelOps:
    def __init__(self, conn: Neo4jConnection): ...

    def connect(self, source, rel_type, target) -> None:
        """
        - Use _find_manager() to get the correct neomodel relationship manager
        - Call manager.connect(target)
        - Fallback: raw Cypher MERGE if no matching manager (poly edge case)
        """

    def disconnect(self, source, rel_type, target) -> None:
        """_find_manager() + .disconnect()"""

    def get_composed_children(self, node) -> list[CodeGraphNode]:
        """
        Iterate all RelationshipTo descriptors on the node's class
        where relation_type == "COMPOSES".  Call .all() on each.
        Deduplicate by attribute name.
        """

    def get_all_edges(self, node) -> list[EdgeDescriptor]:
        """
        Iterate all RelationshipTo AND RelationshipFrom descriptors.
        Call .all() on each.  Return list of EdgeDescriptor.
        """

    def get_all_edges_outgoing(self, node) -> list[EdgeDescriptor]:
        """
        Same as get_all_edges but only RelationshipTo — no incoming edges.
        """

    @staticmethod
    def _find_manager(source, rel_type, target):
        """
        Private helper: match rel_type + target class across MRO.
        Extracted from CodeGraphNode.find_relationship_manager().
        """
```

### 7.5 `backends/neo4j/bulk_ops.py`

**Migrated from**: `graph/__init__.py:to_neo4j` (~70 lines) and
`graph/__init__.py:from_neo4j` fetch section (~60 lines)

```python
class Neo4jBulkOps:
    def __init__(self, conn, node_ops, rel_ops): ...

    def bulk_save(self, layer_graph: LayerGraph) -> None:
        """
        Phase 1: Save all nodes (delegates to node_ops.save).
        Phase 2: Connect COMPOSES children (delegates to rel_ops.connect).
        Phase 3: Connect reference edges (cross-document fallback via raw Cypher).
        """

    def bulk_load_by_tag(self, tag: str) -> list[CodeGraphNode]:
        """
        1. find_all_by_tag(tag) — seed nodes.
        2. For each seed, walk_edges to find 1-hop neighbors.
        3. For non-project neighbors, pull in immediate namespace parents.
        4. Return flat list — tree construction is pure Python in LayerGraph.
        """
```

### 7.6 `backends/neo4j/__init__.py`

```python
class Neo4jBackend(Backend):
    def __init__(self, config: Neo4jConfig | None = None):
        if config is None:
            config = Neo4jConfig.from_env()
        self._conn = Neo4jConnection(config)
        self._node_ops = Neo4jNodeOps(self._conn)
        self._rel_ops = Neo4jRelOps(self._conn)
        self._bulk_ops = Neo4jBulkOps(self._conn, self._node_ops, self._rel_ops)

    def initialize(self, config):  self._conn.ensure_driver()
    def health_check(self) -> bool: return self._conn.health_check()
    def save(self, node):          return self._node_ops.save(node)
    def delete(self, node):        self._node_ops.delete(node)
    def get(self, *a, **kw):       return self._node_ops.get(*a, **kw)
    def inflate(self, *a, **kw):   return self._node_ops.inflate(*a, **kw)
    def find_by_tag(self, *a, **kw):    return self._node_ops.find_by_tag(*a, **kw)
    def find_all_by_tag(self, *a, **kw): return self._node_ops.find_all_by_tag(*a, **kw)
    def find_all_by_source(self, *a):    return self._node_ops.find_all_by_source(*a)
    def find_all_by_kind(self, *a, **kw): return self._node_ops.find_all_by_kind(*a, **kw)
    def connect(self, *a, **kw):    self._rel_ops.connect(*a, **kw)
    def disconnect(self, *a, **kw): self._rel_ops.disconnect(*a, **kw)
    def get_composed_children(self, *a):      return self._rel_ops.get_composed_children(*a)
    def get_all_edges(self, *a):              return self._rel_ops.get_all_edges(*a)
    def get_all_edges_outgoing(self, *a):     return self._rel_ops.get_all_edges_outgoing(*a)
    def bulk_save(self, *a):        self._bulk_ops.bulk_save(*a)
    def bulk_load_by_tag(self, *a): return self._bulk_ops.bulk_load_by_tag(*a)
    def execute_raw(self, *a, **kw): return self._conn.execute_raw(*a, **kw)
```

---

## 8. SQLite Backend Counterparts

### 8.1 `backends/sqlite/connection.py`

```python
class SQLiteConnection:
    def __init__(self, config: SQLiteConfig):
        self.engine = create_engine(config.url)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self): ...
    def execute_raw(self, sql, params) -> tuple[list, dict]: ...
    def health_check(self) -> bool: ...
```

### 8.2 `backends/sqlite/node_ops.py`

- `save()` → computes uid, uses `INSERT ... ON CONFLICT(uid) DO UPDATE SET ...`
- `delete()` → recursive CTE for COMPOSES cascade, then DELETE
- `get()` → `session.query(orm_class).filter_by(**filters).first()`
- `find_by_tag()` → `WHERE json_each(tags).value = :tag` (SQLite JSON functions)
- `inflate()` → converts SQLAlchemy Row to `CodeGraphNode(**row_dict)`

### 8.3 `backends/sqlite/rel_ops.py`

- `connect()` → INSERT into join table `{source_type}_{rel_type}_{target_type}`
- `get_composed_children()` → JOIN on parent_uid column
- `get_all_edges()` → UNION across all join tables for a node

### 8.4 `backends/sqlite/bulk_ops.py`

- `bulk_save()` → single transaction: bulk INSERT nodes, then bulk INSERT join rows
- `bulk_load_by_tag()` → seed nodes by tag, then JOIN for 1-hop expansion

### 8.5 `backends/sqlite/orm.py`

SQLAlchemy declarative models mirroring every CodeGraphNode subclass.  Each has a
`uid` primary key column, typed property columns, and relationship definitions.

---

## 9. Migration Plan

### Phase 1: Extract Neo4j Backend (the focus of this document)

1. Create `codegraph/backends/` package with `interface.py`
2. Create `backends/neo4j/` with all 6 sub-modules
3. Extract existing logic into each sub-module (mechanical copy-paste-adapt)
4. Add `set_backend()` / `get_backend()` registry
5. Rewire `CodeGraphNode` methods to delegate via `get_backend()`
6. Rewire `GraphRepository` to take `Backend` in constructor
7. Rewire `LayerGraph.to_neo4j()` → `to_backend()`, `from_neo4j()` → `from_backend()`
8. Wire `persistence/config.py` → `Neo4jConfig.from_env()`
9. Wire `persistence/connection.py` → `Neo4jConnection` → `Neo4jBackend`
10. **Verification**: full test suite passes against Neo4j with zero behavior changes

### Phase 2: SQLite Backend

1. Create `backends/sqlite/` with mirror structure
2. Implement `orm.py` — SQLAlchemy models for all 17+ node types
3. Implement `node_ops.py`, `rel_ops.py`, `bulk_ops.py`, `connection.py`, `config.py`
4. Map: `ArrayProperty` → JSON column (fast path) or normalized tags table (optimized)
5. Map: multi-hop traversals → recursive CTEs
6. Map: MERGE semantics → `INSERT ... ON CONFLICT(uid) DO UPDATE`
7. **Verification**: test suite passes against SQLite with zero model changes

### Phase 3: Abstract Field Descriptors

1. Create `codegraph/fields.py` with backend-aware property descriptors
2. Replace neomodel imports in models with abstract field imports
3. Models become fully backend-agnostic declarative classes
4. SQLite `orm.py` merges into the field descriptors
5. **Verification**: zero neomodel imports in model files; both backends work

### Phase 4: Replace Raw Queries

1. All raw `db.cypher_query("MATCH ...")` in tools/scripts move into backend operations
2. `session.run()` calls in `tools/discovery.py` become `backend.execute_raw()`
3. Tools accept an optional `backend` parameter (defaults to `get_backend()`)
4. **Verification**: all raw Cypher lives only in `backends/neo4j/`

---

## 10. Key Technical Challenges

### 10.1 ArrayProperty → SQL

Neo4j's `ArrayProperty(StringProperty())` stores lists natively.
`tags` is the primary use case — every node type uses it for provenance filtering.

**SQLite options**:

| Approach | Query pattern | Trade-off |
|----------|--------------|-----------|
| JSON column | `WHERE json_each(tags).value = :tag` | Simple migration, indexable with generated columns |
| Normalized `node_tags` table | `JOIN node_tags WHERE tag = :tag` | Faster for filtered queries, more complex writes |

**Recommendation**: start with JSON for simplicity.  Switch to normalized if tag-filtered
`find_all_by_tag()` becomes a bottleneck.

### 10.2 Graph Traversals → Recursive CTEs

Multi-hop `COMPOSES` and `DEPENDS_ON` traversals map to recursive CTEs:

```sql
WITH RECURSIVE composes_tree AS (
  SELECT uid, qualified_name, parent_uid, 0 as depth
  FROM nodes WHERE uid = :root_uid
  UNION ALL
  SELECT n.uid, n.qualified_name, n.parent_uid, ct.depth + 1
  FROM nodes n
  JOIN composes_tree ct ON n.parent_uid = ct.uid
  WHERE ct.depth < :max_depth
)
SELECT * FROM composes_tree;
```

Depth limits (10 hops max in memory tools) prevent runaway recursion.

### 10.3 MERGE Semantics

Neo4j `MERGE ... SET n += $props` provides idempotent create-or-update by uid.
SQLite equivalent (3.24+):

```sql
INSERT INTO nodes (uid, qualified_name, kind, tags, ...)
VALUES (:uid, :qname, :kind, :tags, ...)
ON CONFLICT(uid) DO UPDATE SET
  qualified_name = excluded.qualified_name,
  kind = excluded.kind,
  tags = excluded.tags,
  ...;
```

### 10.4 Relationship Polymorphism

Currently each relation type (COMPOSES, VERIFIES, etc.) has multiple
`RelationshipTo` descriptors targeting different concrete types (e.g.,
`COMPOSES` → MethodNode, `COMPOSES` → AttributeNode, ...).  This exists
because neomodel can't dispatch polymorphically.

**For SQLite**: each (source_type, rel_type, target_type) triplet gets a join table:

```sql
CREATE TABLE ClassNode_COMPOSES_MethodNode (
    source_uid TEXT REFERENCES nodes(uid),
    target_uid TEXT REFERENCES nodes(uid),
    PRIMARY KEY (source_uid, target_uid)
);
```

Or use a single polymorphic relationships table with a discriminator column.
The single-table approach is simpler but produces wider rows.

### 10.5 neo4j-admin Backup/Restore

The `persistence/docker.py` backup/restore commands use `neo4j-admin dump` and
`neo4j-admin load`.  For SQLite, backup is simply `cp codegraph.db codegraph-backup.db`
(or `.dump` for portability).  This stays backend-specific — each backend can
provide its own backup strategy.

---

## 11. What Does NOT Change

These subsystems are backend-agnostic and stay as-is:

| Subsystem | Reason |
|-----------|--------|
| `LayerGraph` tree construction (`_build_layer_graph`) | Pure Python composition from a flat node list |
| Serialization (`serialize()`, `deserialize()`) | Dict-based, no database interaction |
| UID computation (`_compute_uid()`, `compute_uid()`) | SHA-1 hashing, pure Python |
| Markdown export (`to_markdown()`, `MarkdownExporter`) | File I/O only |
| Component decomposition, PlantUML, visualization | Operate on in-memory `LayerGraph` objects |
| `persistence/docker.py` | Infrastructure management, not query logic |
| `_CodeGraphNodeMeta` registry logic | Class registration, `_llm_fields` — no DB |
| `GraphRepository._build_layer_graph()` | Pure Python tree construction |

---

## 12. Acceptance Criteria

### Phase 1 (Neo4j extraction)
- [ ] `backends/interface.py` defines all 15 abstract methods
- [ ] `backends/neo4j/` has 6 sub-modules, each ≤300 lines
- [ ] `CodeGraphNode` has zero direct neomodel calls (except property declarations)
- [ ] `GraphRepository.__init__` accepts a `Backend` parameter
- [ ] `LayerGraph.to_backend()` / `from_backend()` replace Neo4j-specific variants
- [ ] `persistence/connection.py` and `persistence/config.py` are deleted
- [ ] Full test suite passes against Neo4j backend

### Phase 2 (SQLite backend)
- [ ] `backends/sqlite/` has 6 sub-modules implementing all 15 interface methods
- [ ] All 17+ node types have SQLAlchemy mappings in `orm.py`
- [ ] MERGE semantics work via `ON CONFLICT(uid) DO UPDATE`
- [ ] Tag filtering works via JSON column or normalized table
- [ ] Multi-hop traversals work via recursive CTEs
- [ ] Full test suite passes against SQLite backend
- [ ] No Docker required for test suite

### Phase 3 (Abstract fields)
- [ ] `codegraph/fields.py` provides backend-aware descriptors
- [ ] Zero `from neomodel import` in model files
- [ ] Both Neo4j and SQLite backends pass full test suite
- [ ] Adding a new node type works for both backends without backend-specific code

### Phase 4 (Raw query migration)
- [ ] Zero raw Cypher outside `backends/neo4j/`
- [ ] Zero raw SQL outside `backends/sqlite/` (except `orm.py` definitions)
- [ ] All script/tool raw queries route through `backend.execute_raw()`

---

## Appendix A: Neo4j Reference Count by File

| File | Neo4j refs | Phase migrated |
|------|-----------|----------------|
| `models/tags.py` | 69 | Phase 1 (→ backend delegation) |
| `graph/__init__.py` | 34 | Phase 1 (→ backend.bulk_save/load) |
| `persistence/connection.py` | 15 (entire file) | Phase 1 (→ neo4j/connection.py) |
| `persistence/repository.py` | 20+ | Phase 1 (→ backend.get/find) |
| `persistence/config.py` | 3 (entire file) | Phase 1 (→ neo4j/config.py) |
| `codegraph_mine/persistence.py` | ~15 raw Cypher | Phase 4 |
| `codegraph_mine/llr_miner.py` | ~10 raw Cypher | Phase 4 |
| `codegraph_mine/component_miner.py` | ~10 raw Cypher | Phase 4 |
| `codegraph_mine/composite_miner.py` | ~8 raw Cypher | Phase 4 |
| `codegraph_mine/report.py` | ~8 raw Cypher | Phase 4 |
| `codegraph_memory/tools/*.py` | ~20 raw Cypher | Phase 4 |
| `codegraph_memory/models/relationships.py` | ~5 raw Cypher | Phase 1 (inflate → backend) |
| `tools/discovery.py` | ~10 session.run() | Phase 4 |
| `tools/lookup.py` | ~5 session.run() | Phase 4 |
| `scripts/*.py` | ~15 raw Cypher | Phase 4 |

## Appendix B: Node Type Inventory

All types that need SQLAlchemy mappings (Phase 2, `backends/sqlite/orm.py`):

| Model class | Neo4j label | Key fields |
|-------------|------------|------------|
| `ClassNode` | `:Class` | kind, module, base_classes, is_final, is_abstract |
| `InterfaceNode` | `:Interface` | kind, module, is_abstract |
| `EnumNode` | `:Enum` | kind, module |
| `UnionNode` | `:Union` | kind, module |
| `ConceptNode` | `:Concept` | kind, module, initializer |
| `ModuleNode` | `:Module` | kind |
| `MethodNode` | `:Method` | type_signature, argsstring, is_static, is_const, ... |
| `AttributeNode` | `:Attribute` | type_signature, is_static, is_const |
| `EnumValueNode` | `:EnumValue` | — |
| `FunctionNode` | `:Function` | type_signature, argsstring |
| `DefineNode` | `:Define` | — |
| `NamespaceNode` | `:Namespace` | description |
| `TestNode` | `:Test` | test_name, test_module, method, description |
| `AssertionNode` | `:Assertion` | phase, order, operator, description |
| `TestStepNode` | `:TestStep` | order, description, body_start, body_end |
| `TestFixtureNode` | `:TestFixture` | name, description, type_signature |
| `ImplementationNode` | `:Implementation` | implementation, impl_embedding |
| `FileNode` | `:File` | path, file_type |
| `LiteralNode` | `:Literal` | value, value_type |
| `HLR` | `:HLR` | description |
| `LLR` | `:LLR` | description |
| `DecisionNode` | `:Decision` | content, decided_at, updated_at, confidence |
| `ConstraintNode` | `:Constraint` | content, decided_at, updated_at, confidence |
| `RationaleNode` | `:Rationale` | content, decided_at, updated_at, confidence |
| `AssumptionNode` | `:Assumption` | content, decided_at, updated_at, confidence |
| `TradeoffNode` | `:Tradeoff` | content, decided_at, updated_at, confidence |
| `InsightNode` | `:Insight` | content, decided_at, updated_at, confidence |
| `Component` | `:Component` | (from `codegraph_project`) |

Plus shared fields on `CompoundNode` / `MemberNode` / `CodeGraphNode` bases:
`uid`, `qualified_name`, `name`, `kind`, `tags`, `source`, `visibility`,
`brief_description`, `detailed_description`, `file_path`, `line_number`,
`definition`, `doc_embedding`, `component_id`, `source_type`, `refid`.

---

## Appendix C: Test Suite Impact Assessment

### C.1 Current State

| Metric | Count |
|--------|-------|
| Total test files | 126 |
| Total test functions | ~550 |
| Pure Python tests (no Neo4j) | ~320 tests (58%) |
| Neo4j-dependent tests | ~180 tests (33%) |
| Integration tests (Neo4j + LLM) | ~50 tests (9%) |
| Duplicate test directories | 1 (`memory/` and `codegraph_memory/` are near-duplicates) |

Infrastructure:
- `tests/docker-compose.yml` — dedicated Neo4j container on port 7688 (password `codegraph-test`)
- `tests/conftest.py` — session-scoped container lifecycle + neomodel setup + per-test DB wipe
- `tests/.env` — kept for documentation, NOT loaded by fixtures (avoids VS Code `.env` pre-load conflicts)

### C.2 Classification Matrix

#### Pure Python Tests → `tests/unit/`

These test serialization, deserialization, UID computation, field defaults,
markdown/PUML/viz export, and agent graph construction.  **No backend needed**.

| Current path | Tests | Topic |
|---|---|---|
| `compound/test_class_serialization.py` | 1 | ClassNode deserialization |
| `compound/test_enum_serialization.py` | 1 | EnumNode deserialization |
| `compound/test_interface_serialization.py` | 1 | InterfaceNode deserialization |
| `compound/test_module_serialization.py` | 1 | ModuleNode deserialization |
| `compound/test_union_serialization.py` | 1 | UnionNode deserialization |
| `compound/test_compound_search_fields.py` | 8 | doc_embedding, implementation_ref field defaults |
| `member/test_attribute_serialization.py` | 1 | AttributeNode serialization |
| `member/test_attribute_deserialization.py` | 1 | AttributeNode deserialization |
| `member/test_define_serialization.py` | 1 | DefineNode serialization |
| `member/test_enum_value_serialization.py` | 1 | EnumValueNode serialization |
| `member/test_function_serialization.py` | 1 | FunctionNode serialization |
| `member/test_method_serialization.py` | 1 | MethodNode serialization |
| `member/test_method_deserialization.py` | 4 | MethodNode deserialization |
| `member/test_member_search_fields.py` | 24 | doc_embedding, implementation_ref field defaults |
| `file/test_file_serialization.py` | 4 | FileNode serialization |
| `file/test_file_deserialization.py` | 1 | FileNode deserialization |
| `namespace/test_namespace_serialization.py` | 1 | NamespaceNode serialization |
| `parameter/test_parameter_serialization.py` | 1 | ParameterNode serialization |
| `implementation/test_implementation_node.py` | 16 | ImplementationNode model |
| `implementation/test_implementation_search_fields.py` | 4 | ImplementationNode search fields |
| `test/test_test_node.py` | 24 | TestNode model, field defaults, serialization |
| `test/test_assertion_node.py` | 19 | AssertionNode model, field defaults |
| `test/test_test_step_node.py` | 24 | TestStepNode model, field defaults |
| `test_codegraph_node.py` (partial) | ~35 | deserialize error paths, serialize, identity |
| `test_layer_graph.py` (partial) | ~30 | `_node_key`, deserialize, serialize, composite tree |
| `test_markdown.py` | 51 | Markdown export/import, round-trip |
| `test_plantuml.py` (partial) | ~80 | PlantUML export/import |
| `test_viz.py` (partial) | ~30 | Cytoscape HTML generation |
| `test_component_decomposition.py` (partial) | ~18 | Component decomposition logic |
| `requirements/test_formatting.py` | 16 | HLR/LLR formatting |
| `enrich/test_enrich_unit.py` | 33 | Enrichment result types, parsing |
| `unit/test_design_smells.py` | 18 | Design smell detection |
| `agents/test_base_agent.py` | 29 | Agent graph construction, routing |
| `agents/test_callbacks.py` | 8 | JSONL/markdown/metrics output |
| `agents/test_config.py` | 4 | Context resolution |
| `agents/test_context.py` | 19 | Built-in resolvers (mocked Neo4j) |
| `agents/test_design_agent.py` | 32 | DesignAgent (mocked Neo4j) |
| `codegraph_design/test_design_smells.py` | 23 | Design smell checkers |
| `codegraph_decompose/test_decompose_agent.py` | 45 | Decompose validation + ingestion (unit) |
| `codegraph_feedback/tools/test_feedback_tools.py` | 23 | Feedback tool logic |

#### Neo4j-Dependent Tests → `tests/backends/neo4j/`

These test CRUD, relationship creation/querying, graph persistence, and
repository methods.  **Require a running Neo4j container** (via `docker compose`).

| Current path | Tests | Topic |
|---|---|---|
| **compound/** (12 files) | ~ | |
| `compound/test_class_composed_by_namespace.py` | 1 | ClassNode → NamespaceNode COMPOSES |
| `compound/test_class_composes_attribute.py` | 1 | ClassNode COMPOSES AttributeNode |
| `compound/test_class_composes_method.py` | 1 | ClassNode COMPOSES MethodNode |
| `compound/test_class_depends_on.py` | 3 | ClassNode DEPENDS_ON |
| `compound/test_class_inherits.py` | 1 | ClassNode INHERITS_FROM |
| `compound/test_class_realizes_interface.py` | 1 | ClassNode REALIZES InterfaceNode |
| `compound/test_enum_composed_by_namespace.py` | 1 | EnumNode ← NamespaceNode |
| `compound/test_enum_composes_value.py` | 1 | EnumNode COMPOSES EnumValueNode |
| `compound/test_interface_composed_by_namespace.py` | 1 | InterfaceNode ← NamespaceNode |
| `compound/test_interface_composes_method.py` | 1 | InterfaceNode COMPOSES MethodNode |
| `compound/test_module_composed_by_namespace.py` | 1 | ModuleNode ← NamespaceNode |
| `compound/test_union_composed_by_namespace.py` | 1 | UnionNode ← NamespaceNode |
| **member/** (7 files) | ~ | |
| `member/test_attribute_composed_by_class.py` | 1 | AttributeNode ← ClassNode |
| `member/test_attribute_defined_in_file.py` | 1 | AttributeNode DEFINED_IN FileNode |
| `member/test_enum_value_composed_by_enum.py` | 1 | EnumValueNode ← EnumNode |
| `member/test_function_composed_by_namespace.py` | 1 | FunctionNode ← NamespaceNode |
| `member/test_method_composed_by_parent.py` | 2 | MethodNode ← ClassNode / InterfaceNode |
| `member/test_method_defined_in_file.py` | 1 | MethodNode DEFINED_IN FileNode |
| `member/test_method_invokes_method.py` | 2 | MethodNode INVOKES MethodNode |
| **namespace/** (7 files) | ~ | |
| `namespace/test_namespace_composes_class.py` | 1 | NamespaceNode COMPOSES ClassNode |
| `namespace/test_namespace_composes_enum.py` | 1 | NamespaceNode COMPOSES EnumNode |
| `namespace/test_namespace_composes_function.py` | 1 | NamespaceNode COMPOSES FunctionNode |
| `namespace/test_namespace_composes_interface.py` | 1 | NamespaceNode COMPOSES InterfaceNode |
| `namespace/test_namespace_composes_module.py` | 1 | NamespaceNode COMPOSES ModuleNode |
| `namespace/test_namespace_composes_namespace.py` | 1 | NamespaceNode COMPOSES NamespaceNode |
| `namespace/test_namespace_composes_union.py` | 1 | NamespaceNode COMPOSES UnionNode |
| `namespace/test_namespace_composed_by_namespace_incoming.py` | 1 | NamespaceNode ← NamespaceNode |
| **test/** (2 files) | ~ | |
| `test/test_test_fixture_node.py` | 31 | TestFixtureNode CRUD + relationships |
| `test/test_graph_integration.py` | 17 | TestNode + AssertionNode + TestStepNode integration |
| **repository/** (2 files) | ~ | |
| `repository/test_graph_repository.py` | 27 | GraphRepository scope methods |
| `repository/test_hlr_subtree.py` | 10 | Multi-hop COMPOSES traversal |
| **top-level** | ~ | |
| `test_codegraph_node.py` (partial) | ~40 | find_relationship_manager, fetch_by_tag, save, delete |
| `test_layer_graph.py` (partial) | ~16 | to_neo4j, from_neo4j |
| `test_connection.py` | 5 | Neo4j session + Cypher |
| `test_graph_integration.py` | 7 | Full Calculator graph round-trip |
| `test_update.py` | 11 | CodeGraphNode.update() |
| `test_tools.py` (@integration) | ~4 | Tool tests needing Neo4j |
| `test_tools_integration.py` | 16 | Tool integration tests |
| **memory/** (ALL) | ~100 | Memory node CRUD, tools, graph, lifecycle |
| **codegraph_memory/** (ALL) | ~100 | Near-duplicate of `memory/` |

#### Integration Tests → `tests/integration/`

These need both a backend AND an LLM key, or test multi-tool pipelines.

| Current path | Tests | Notes |
|---|---|---|
| `test_markdown_integration.py` | 3 | Full graph → markdown → round-trip |
| `test_markdown_roundtrip.py` | 20 | Requirements graph round-trip |
| `test_markdown_requirements.py` | 31 | HLR/LLR/Component markdown |
| `test_plantuml_integration.py` | 2 | Full graph → PlantUML → PNG |
| `test_viz_integration.py` | 4 | LayerGraph JSON → HTML → PNG |
| `test_decompose_roundtrip.py` | 18 | Decomposition + persistence round-trip |
| `test_component_decomposition.py` (partial) | ~4 | Needs Neo4j for data |
| `test_viz.py` (@integration) | ~4 | Visualization integration markers |
| `pipelines/test_design_migration_manager.py` | 3 | End-to-end design agent pipeline |
| `pipelines/test_requirements_lint.py` | 5 | Lint agent across versions |
| `codegraph_design/test_design_reconciliation.py` | 2 | Design reconciliation in Neo4j |

### C.3 Duplicate Test Directories

`tests/memory/` and `tests/codegraph_memory/` are near-duplicates.  They have the
same file structure:

```
memory/                      codegraph_memory/
├── conftest.py               ├── __init__.py
├── export/                   ├── conftest.py
│   └── test_markdown.py      ├── export/
├── graph/                    │   └── test_markdown.py
│   └── test_memory_graph.py  ├── graph/
├── lifecycle/                │   └── test_memory_graph.py
│   ├── test_drift.py         ├── lifecycle/
│   └── test_validate.py      │   ├── test_drift.py
├── models/                   │   └── test_validate.py
│   ├── test_assumption_node  ├── models/
│   ├── test_constraint_node  │   ├── test_assumption_node
│   ├── test_decision_node    │   ├── test_constraint_node
│   ├── test_insight_node     │   ├── test_decision_node
│   ├── test_rationale_node   │   ├── test_insight_node
│   └── test_tradeoff_node    │   ├── test_rationale_node
└── tools/                    │   └── test_tradeoff_node
    ├── test_context.py       └── tools/
    ├── test_lookup.py            ├── test_context.py
    ├── test_record.py            ├── test_lookup.py
    ├── test_search.py            ├── test_record.py
                                  └── test_search.py
```

Files differ slightly (different import paths, minor content changes).
**Action**: consolidate into one directory during the migration.  The canonical
location should be `tests/backends/neo4j/memory/` since these tests require Neo4j.

### C.4 Target Test Structure

```
tests/
├── conftest.py                      # Top-level: backend fixture selection
├── docker-compose.yml               # Moved from root — only neo4j backend needs it
│
├── unit/                            # Pure Python — no backend, no Docker
│   ├── conftest.py                  # Empty or global test config only
│   ├── models/
│   │   ├── compound/               # test_*_serialization.py, test_*_search_fields.py
│   │   ├── member/                 # test_*_serialization.py, test_*_deserialization.py
│   │   ├── test_/                  # test_test_node.py, test_assertion_node.py, test_test_step_node.py
│   │   ├── namespace/              # test_namespace_serialization.py
│   │   ├── file/                   # test_file_serialization.py, test_file_deserialization.py
│   │   ├── parameter/              # test_parameter_serialization.py
│   │   └── implementation/         # test_implementation_node.py, test_implementation_search_fields.py
│   ├── graph/
│   │   ├── test_layer_graph.py     # _node_key, deserialize, composite tree (pure Python subset)
│   │   └── test_codegraph_node.py  # deserialize, serialize, identity (pure Python subset)
│   ├── export/
│   │   ├── test_markdown.py
│   │   ├── test_plantuml.py        # (pure Python subset)
│   │   └── test_viz.py             # (pure Python subset)
│   ├── agents/
│   │   ├── test_base_agent.py
│   │   ├── test_callbacks.py
│   │   ├── test_config.py
│   │   ├── test_context.py
│   │   └── test_design_agent.py
│   ├── enrichment/
│   │   └── test_enrich_unit.py
│   ├── requirements/
│   │   └── test_formatting.py
│   ├── design/
│   │   └── test_design_smells.py
│   ├── decompose/
│   │   └── test_decompose_agent.py
│   └── feedback/
│       └── test_feedback_tools.py
│
├── backends/
│   ├── neo4j/                       # Requires Docker + Neo4j container
│   │   ├── docker-compose.yml       # Per-backend container config
│   │   ├── conftest.py              # test_neo4j_container, setup_neomodel, clear_db
│   │   ├── test_connection.py
│   │   ├── models/
│   │   │   ├── compound/           # All test_class_composes_*, test_*_inherits, etc.
│   │   │   ├── member/             # All test_*_composed_by_*, test_*_defined_in, etc.
│   │   │   ├── test_/              # test_test_fixture_node.py, test_graph_integration.py
│   │   │   └── namespace/          # All test_namespace_composes_*
│   │   ├── graph/
│   │   │   ├── test_codegraph_node.py    # find_relationship_manager, fetch_by_tag, save, delete
│   │   │   ├── test_layer_graph.py       # to_neo4j, from_neo4j
│   │   │   ├── test_graph_repository.py
│   │   │   └── test_hlr_subtree.py
│   │   ├── memory/                  # Consolidated from tests/memory/ + tests/codegraph_memory/
│   │   │   ├── conftest.py
│   │   │   ├── models/
│   │   │   ├── tools/
│   │   │   ├── graph/
│   │   │   ├── lifecycle/
│   │   │   └── export/
│   │   └── tools/
│   │       ├── test_tools.py        # (@integration subset)
│   │       └── test_discovery.py    # New — backend-specific discovery tests
│   │
│   └── sqlite/                      # No Docker — uses :memory: or temp file
│       ├── conftest.py              # create_engine("sqlite://"), session fixture
│       ├── test_connection.py
│       ├── models/
│       │   ├── compound/           # Same test logic as neo4j, different backend
│       │   ├── member/
│       │   ├── test_/
│       │   └── namespace/
│       ├── graph/
│       │   ├── test_codegraph_node.py
│       │   ├── test_layer_graph.py
│       │   ├── test_graph_repository.py
│       │   └── test_hlr_subtree.py
│       └── memory/
│
└── integration/                     # Backend + LLM / multi-tool pipelines
    ├── conftest.py                  # Needs backend fixture + LLM key check
    ├── test_markdown_integration.py
    ├── test_markdown_roundtrip.py
    ├── test_markdown_requirements.py
    ├── test_plantuml_integration.py
    ├── test_viz_integration.py
    ├── test_decompose_roundtrip.py
    ├── test_graph_integration.py
    ├── test_tools_integration.py
    ├── pipelines/
    │   ├── conftest.py
    │   ├── test_design_migration_manager.py
    │   └── test_requirements_lint.py
    └── design/
        └── test_design_reconciliation.py
```

### C.5 Backend-Agnostic Test Pattern (Phase 2+)

Once the backend interface exists, many "Neo4j-dependent" tests become
generic backend tests.  The pattern:

```python
# tests/backends/neo4j/models/compound/test_class_composes_method.py
# AND
# tests/backends/sqlite/models/compound/test_class_composes_method.py
#
# Both import the SAME test class from a shared location:

from tests.backends.shared.test_compound_relationships import TestClassComposesMethod

# Each backend's conftest.py defines the 'backend' fixture:
#   neo4j/conftest.py  → Neo4jBackend(Neo4jConfig.from_env())
#   sqlite/conftest.py → SQLiteBackend(SQLiteConfig(db_path=":memory:"))
```

```python
# tests/backends/shared/test_compound_relationships.py

class TestClassComposesMethod:
    """Backend-agnostic: ClassNode COMPOSES MethodNode."""

    def test_create_and_connect(self, backend, clear_backend):
        cls = ClassNode(name="Calc", kind="class", source="test")
        cls = backend.save(cls)
        method = MethodNode(name="add", kind="method", source="test")
        method = backend.save(method)

        backend.connect(cls, "COMPOSES", method)

        children = backend.get_composed_children(cls)
        assert len(children) == 1
        assert children[0].name == "add"

    def test_roundtrip_serialize_edges(self, backend, clear_backend):
        # ... serialize + backend.save + verify edges ...
```

This gives **one implementation, two backends** — the backend fixture
is the only variable.

### C.6 Migration Steps

#### Step 1: Split `tests/conftest.py`

Extract the Neo4j-specific fixtures into `tests/backends/neo4j/conftest.py`.
The top-level `tests/conftest.py` becomes a thin layer that:
- Discovers which backend to use (env var `CODEGRAPH_TEST_BACKEND=neo4j|sqlite`)
- Imports the backend-specific conftest
- Keeps shared fixtures (`_check_dev_neo4j_for_integration_tests` → renamed)

#### Step 2: Create `tests/unit/`

Move all pure-Python tests.  No conftest changes needed — these tests
don't use Neo4j fixtures.

#### Step 3: Create `tests/backends/neo4j/`

Move all Neo4j-dependent tests.  The `docker-compose.yml` moves WITH them.
The conftest (`test_neo4j_container`, `setup_neomodel`, `clear_db`) moves
verbatim.

#### Step 4: Consolidate `memory/` duplicates

Pick `tests/backends/neo4j/memory/` as the canonical location.  Merge any
non-conflicting changes from the duplicate.  Delete `tests/memory/` and
`tests/codegraph_memory/`.

#### Step 5: Create `tests/integration/`

Move integration tests.  These need a backend fixture (from Step 1) PLUS
an LLM key check.  Their conftest validates both.

#### Step 6: Add `tests/backends/sqlite/`

Create the mirror structure with a SQLite-specific conftest.  Start with
a subset of tests (e.g., `test_class_composes_method.py`) imported from
`tests/backends/shared/`.  Grow coverage as the SQLite backend matures.

### C.7 Pytest Invocation After Migration

```bash
# Run pure Python unit tests (no Docker, no DB)
pytest tests/unit/ -v

# Run Neo4j-specific tests (requires Docker)
pytest tests/backends/neo4j/ -v

# Run SQLite-specific tests (no Docker, uses :memory:)
pytest tests/backends/sqlite/ -v

# Run all backend tests
pytest tests/backends/ -v

# Run integration tests (requires backend + LLM key)
pytest tests/integration/ -v --run-slow

# Run everything
pytest tests/ -v

# CI matrix (future)
# Job 1: pytest tests/unit/ tests/backends/sqlite/     (fast, no Docker)
# Job 2: pytest tests/backends/neo4j/                   (Docker!)
# Job 3: pytest tests/integration/ --run-slow           (needs LLM key)
```
