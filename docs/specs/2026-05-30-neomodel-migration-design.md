# Neomodel Migration Design

**Date:** 2026-05-30  
**Status:** Approved  
**Scope:** Replace custom Neo4j driver management and node CRUD with neomodel OGM

## Overview

Replace the custom Neo4j driver management (`neo4j/connection.py`) and
Pydantic node models (`nodes/`) with [neomodel](https://github.com/neo4j-contrib/neomodel),
a Neo4j Object Graph Mapper. Node persistence and traversal become neomodel-native.
The Pydantic design layer (`designs/`) remains unchanged — repositories bridge
the two.

**Architecture after migration:**

```
                    ┌──────────────────────────┐
                    │   design models (Pydantic) │
                    │   ClassDiagram, ClassNode, │
                    │   InterfaceNode, EnumNode, │
                    │   Association, FieldTags   │
                    └─────────────┬────────────┘
                                  │ calls
                    ┌─────────────▼────────────┐
                    │   Repository layer (new)  │
                    │   CompoundRepository,     │
                    │   MemberRepository, ...   │
                    └─────────────┬────────────┘
                                  │ delegates to
                    ┌─────────────▼────────────┐
                    │   node models (neomodel)  │
                    │   CompoundNode, MemberNode│
                    │   NamespaceNode, FileNode │
                    │   ParameterNode           │
                    └─────────────┬────────────┘
                                  │ lives in
                    ┌─────────────▼────────────┐
                    │         Neo4j             │
                    └──────────────────────────┘
```

## Approach

**Option 3: neomodel for persistence, Pydantic for contracts**

Node models become neomodel `StructuredNode` subclasses that handle persistence
(`.save()`, `.delete()`, relationship traversal). Design models stay Pydantic
with FieldTags for LLM serialization. Repositories bridge the two: the design
layer's `ClassDiagram.to_neo4j()` calls repositories internally rather than
returning raw lists for the caller to insert.

See [rejected options](#rejected-options) below.

## What Changes

### 1. Node Models (Pydantic → neomodel)

All node models move from `src/codegraph/nodes/` to `src/codegraph/models/`
and become neomodel `StructuredNode` subclasses.

**Field mapping conventions:**

| Python type | neomodel property |
|------------|-------------------|
| `str` | `StringProperty()` |
| `int` | `IntegerProperty()` |
| `int \| None` | `IntegerProperty()` (nullable by default) |
| `bool` | `BooleanProperty()` |
| `list[str]` | `ArrayProperty(StringProperty())` |
| `Literal["a","b"]` | `StringProperty(choices={"a":"a","b":"b"})` |
| Required fields (no default) | No `default=` |
| `FieldTags(...)` | Removed (serialization stays in design layer) |

The key identity field (`qualified_name`) uses `UniqueIdProperty()`.

**Models to migrate:**

| Current (Pydantic) | New (neomodel) |
|-------------------|----------------|
| `nodes.CompoundNode` | `models.compound.CompoundNode` |
| `nodes.MemberNode` | `models.member.MemberNode` |
| `nodes.NamespaceNode` | `models.namespace.NamespaceNode` |
| `nodes.FileNode` | `models.file.FileNode` |
| `nodes.ParameterNode` | `models.parameter.ParameterNode` |

**Relationship definitions (new):** Each model declares graph edges as
class-level descriptors for traversal:

```python
class CompoundNode(StructuredNode):
    members = RelationshipTo('MemberNode', 'COMPOSES')
    parent_namespace = RelationshipFrom('NamespaceNode', 'COMPOSES')
    base = RelationshipTo('CompoundNode', 'GENERALIZES')
    derived = RelationshipFrom('CompoundNode', 'GENERALIZES')
```

### 2. Connection Management (removed)

The entire `src/codegraph/neo4j/` subpackage is deleted. Replaced by:

```python
# src/codegraph/config.py
import os
from neomodel import config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

config.DATABASE_URL = (
    f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{NEO4J_URI.replace('bolt://', '')}"
)
```

| Current feature | Replaced by |
|----------------|-------------|
| `Neo4jConnection` class | neomodel `config.DATABASE_URL` |
| `get_standalone_driver()` | neomodel's internal connection pool |
| `verify_connectivity()` | Auto-verified on first query |
| `ensure_constraints()` | `install_all_labels()` |
| Session context managers | Not needed — `.save()`/`.get()` handles sessions |

**Backward compatibility:** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` env
vars are preserved. All existing public API symbols (`Neo4jConnection`,
`get_standalone_driver`, etc.) are removed from exports. The ticketing system
repository will be updated concurrently.

### 3. Repository Layer (new)

`src/codegraph/repositories/` — thin adapters between design Pydantic models
and neomodel persistence.

**Design principle:** The design layer never imports neomodel. Repositories
are the only code that touches neomodel classes.

```python
class CompoundRepository:
    def save(self, node: CompoundNode) -> CompoundNode:
        return node.save()

    def get(self, qualified_name: str) -> CompoundNode | None:
        return CompoundNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[CompoundNode]:
        return list(CompoundNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[CompoundNode]) -> list[CompoundNode]:
        return [node.save() for node in nodes]

    def delete_all_design_layer(self) -> int:
        nodes = list(CompoundNode.nodes.filter(layer="design"))
        for n in nodes:
            n.delete()
        return len(nodes)

    def connect_member(self, compound_qn: str, member_qn: str):
        c = CompoundNode.nodes.get(qualified_name=compound_qn)
        m = MemberNode.nodes.get(qualified_name=member_qn)
        c.members.connect(m)

    def connect_base(self, child_qn: str, parent_qn: str):
        child = CompoundNode.nodes.get(qualified_name=child_qn)
        parent = CompoundNode.nodes.get(qualified_name=parent_qn)
        child.base.connect(parent)
```

**Repositories to create:**

| Repository | Backing neomodel class |
|-----------|----------------------|
| `CompoundRepository` | `CompoundNode` |
| `MemberRepository` | `MemberNode` |
| `NamespaceRepository` | `NamespaceNode` |
| `FileRepository` | `FileNode` |
| `ParameterRepository` | `ParameterNode` |

### 4. ClassDiagram.to_neo4j() — Internal Save

Currently `to_neo4j()` returns `(compounds, members, edges)` lists for the
caller to insert. After migration, it handles persistence internally:

```python
class ClassDiagram(BaseModel):
    def to_neo4j(self) -> None:
        """Persist the entire diagram to Neo4j via repository layer."""
        compound_repo = CompoundRepository()
        member_repo = MemberRepository()

        for cls in self.classes:
            compound = CompoundNode(...)  # map from ClassNode
            compound_repo.save(compound)
            for attr in cls.attributes:
                member = MemberNode(...)
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)
            for method in cls.methods:
                member = MemberNode(...)
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        # interfaces, enums follow same pattern
        # associations use relationship helpers
```

### 5. Package Structure After Migration

```
src/codegraph/
├── config.py              ← new: neomodel DATABASE_URL setup
├── models/                ← new: neomodel StructuredNode classes
│   ├── __init__.py
│   ├── compound.py
│   ├── member.py
│   ├── namespace.py
│   ├── file.py
│   └── parameter.py
├── repositories/          ← new: thin CRUD wrappers
│   ├── __init__.py
│   ├── compound.py
│   ├── member.py
│   ├── namespace.py
│   ├── file.py
│   └── parameter.py
├── designs/               ← unchanged
├── edges.py               ← stays Pydantic
├── constants.py           ← unchanged
└── graph/                 ← updated to use neomodel traversal (future)
```

### 6. What Gets Deleted

- `src/codegraph/nodes/` — all Pydantic node models
- `src/codegraph/neo4j/connection.py` — driver management
- `src/codegraph/neo4j/__init__.py` — connection exports
- `tests/test_nodes.py` — rewritten against neomodel models
- `tests/test_codegraph_edge_description.py` — rewritten if relevant

## What Stays

| Module | Rationale |
|--------|-----------|
| `designs/` | Pydantic models with FieldTags, LLM serialization, verification — not a persistence concern |
| `constants.py` | Shared vocabulary (kinds, layers, predicates) — consumed by both neomodel models and design models |
| `edges.py` | `CodebaseEdge` stays Pydantic; may get neomodel Relationship equivalents later if traversal performance matters |
| `graph/` | Typed containers for ontology queries — updated to use neomodel traversal in a follow-up |

## What Stays Out of Scope

- `designs/` migration to neomodel (FieldTags doesn't map cleanly)
- `graph/` module query rewrites (cosmetic cleanup, not blocking)
- `CodebaseEdge` migration to neomodel relationships (can be done incrementally)
- SQLite/SQLAlchemy investigation (separate initiative)

## Tests

All existing tests in `tests/` are rewritten to work against neomodel models.
Key test patterns:

- **Model construction:** Create neomodel instances with required fields, verify property values
- **Save and retrieve:** `.save()` then `.get()`, verify round-trip fidelity
- **Relationship traversal:** Connect compounds to members, traverse both directions
- **Repository CRUD:** Test each repository method in isolation
- **Design layer round-trip:** `ClassDiagram.to_neo4j()` persists, `from_neo4j()` reads back

neomodel tests require a running Neo4j instance or neomodel's `db.set_connection()`
pointed at a test database (the existing test setup can be reused if it already
has a Neo4j test instance).

## Consumer Impact

### Ticketing System (updated concurrently)

The ticketing system depends on codegraph for:

- `Neo4jConnection`, `get_standalone_driver`, `get_standalone_session` — for Neo4j access
- `CompoundNode`, `MemberNode`, `NamespaceNode` (Pydantic) — for node construction
- `ClassDiagram.to_neo4j()` — for persisting design diagrams

All three change. The ticketing system **must be updated in the same release
cycle** as codegraph. Its changes:

1. Replace `from codegraph.neo4j import Neo4jConnection` with `from codegraph.config import NEO4J_URI; from neomodel import config`
2. Replace `CompoundNode(qualified_name=..., name=..., ...)` (Pydantic) with `CompoundNode(qualified_name=..., name=..., ...).save()` (neomodel)
3. `ClassDiagram.to_neo4j()` call signature changes — no longer returns lists, persists internally
4. All manual Cypher query strings replaced with neomodel `.filter()` / `.get()` / `.all()` calls

These changes are scoped and tracked in a separate ticketing-system plan.

### Doxygen Dependency Parser

Currently uses `model_dump()` + raw Cypher to write as-built/dependency nodes.
Can be updated to use repository `.save()` calls after the codegraph release.
The old pattern still works if import compatibility shims are kept for one
release cycle (optional).

## Migration Order

### Codegraph

1. Add `neomodel` to `pyproject.toml` dependencies
2. Create `src/codegraph/config.py` with neomodel setup
3. Create `src/codegraph/models/` with neomodel node classes
4. Create `src/codegraph/repositories/` with CRUD wrappers
5. Update `ClassDiagram.to_neo4j()` to use internal save
6. Update `ClassDiagram.from_neo4j()` to read through repositories
7. Update `src/codegraph/__init__.py` exports
8. Remove `src/codegraph/nodes/` and `src/codegraph/neo4j/connection.py`
9. Rewrite tests

### Ticketing System (concurrent, separate plan)

Coordinated release — both repos ship the change together so no consumer
is left with broken imports. The ticketing system plan covers:

- neomodel initialization
- Repository adoption for all CRUD operations
- ClassDiagram.to_neo4j() API change
- Test updates

## Dependencies

```toml
dependencies = [
    "pydantic>=2.0",
    "neo4j",          # kept (neomodel depends on it internally)
    "neomodel>=5.0",  # added
]
```

The `neo4j` driver package stays as a dependency since neomodel uses it
internally. It does not need to be removed from `pyproject.toml`.

## Rejected Options

### Option 1: Nodes only (no design layer changes)
Would have left `ClassDiagram.to_neo4j()` returning raw lists for the caller
to insert. Rejected because it keeps the manual Cypher pattern alive in consumers.

### Option 2: Everything into neomodel
Would have required porting the entire design layer (ClassDiagram, ClassNode,
FieldTags) to neomodel. Rejected because neomodel doesn't support nested
composition (ClassNode has `list[AttributeNode]`) or tagged LLM serialization
natively, and Pydantic's validation is superior for design models.

### Option 3 (chosen): neomodel for persistence, Pydantic for contracts
neomodel handles persistence and traversal. Pydantic handles validation,
serialization, and LLM formatting. Repositories bridge the two.
