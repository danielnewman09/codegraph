# GraphRepository Design Spec

**Date:** 2025-06-03  
**Status:** Approved

## Summary

Introduce a `GraphRepository` class as the single data access layer for the
codegraph. It provides six scope-based read methods that each return a
`LayerGraph`, a single bulk write method (`save_layer_graph`), and a shared
private builder that handles 1-hop neighbor expansion and edge collection.
`LayerGraph` remains an unmodified data container. Two new `CodeGraphNode`
class methods (`fetch_all_by_source`, `fetch_all_by_kind`) support the new
scopes.

## Motivation

Currently there is no single entry point for querying the codebase graph.
`LayerGraph.from_neo4j(layer)` fetches by layer, but there is no way to
retrieve a subgraph scoped to a namespace, a compound, a neighbourhood, a
project source, or a node kind. Writing a separate `DesignRepository`-style
class (as in the ticketing system) would work, but that approach returns
specialized container types (`CompoundGraph`, `NamespaceGraph`,
`OntologyGraph`) instead of reusing the existing `LayerGraph`. A
`GraphRepository` that always returns `LayerGraph` objects is simpler, more
consistent, and lets callers use the same API regardless of query scope.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 GraphRepository                  │
│  ─────────────────────────────────────────────  │
│  Read methods (return LayerGraph):               │
│    get_by_layer(layer)                           │
│    get_by_namespace(qualified_name)              │
│    get_by_compound(qualified_name)               │
│    get_by_neighbourhood(qualified_name)          │
│    get_by_source(source)                         │
│    get_by_kind(kind, layer?)                     │
│                                                  │
│  Write method:                                   │
│    save_layer_graph(graph: LayerGraph)           │
│                                                  │
│  Private:                                        │
│    _build_layer_graph(seeds) -> LayerGraph        │
│    _get_node_by_qualified_name(qn)               │
│    _get_member_by_qualified_name(qn)              │
└─────────────────────────────────────────────────┘
         │                              │
         │ reads via                     │ writes via
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│   neomodel ORM   │            │   LayerGraph     │
│   .nodes.filter  │            │   .to_neo4j()    │
│   .nodes.get     │            │   (existing)    │
│   rel managers   │            └─────────────────┘
└─────────────────┘
```

**Key invariants:**

- `GraphRepository` holds no mutable state beyond a reference to neomodel's
  `db` for connection management.
- All read methods return `LayerGraph` — no special container types.
- `LayerGraph` is not modified — it stays a data container. The repository
  constructs new ones.
- `save_layer_graph()` delegates to the existing `LayerGraph.to_neo4j()`.
- All label dispatch uses `CodeGraphNode._registry` and the atomized model
  classes.

## The Shared Builder — `_build_layer_graph(seeds)`

All six scope methods delegate to this private method. It takes a list of
neomodel node instances (seeds) and produces a fully-populated `LayerGraph`.

**Algorithm:**

1. **Collect seed nodes** into a dict keyed by `LayerGraph._node_key()`.
2. **Expand 1-hop neighbors** — for each seed, call
   `node.serialize_edges()` to discover connected node UIDs and types. Fetch
   each neighbor from Neo4j if not already in the dict.
3. **Collect edges** — walk each seed's `serialize_edges()` results,
   recording `(source_key, relation_type, target_key, target_type)` for every
   edge where both endpoints are in the dict.
4. **Derive layer** — infer from the first seed node that has a `layer`
   property (fallback: `"design"`).
5. **Return `LayerGraph(layer=layer, nodes=nodes, edges=edges)`**.

**Reuse of existing logic:**

| Existing code | Reused by |
|---|---|
| `CodeGraphNode.fetch_all_by_layer(layer)` | `get_by_layer` |
| `node.serialize_edges()` | Builder — neighbor UID + type discovery |
| `CodeGraphNode._registry` + `target_cls.nodes.get_or_none()` | Builder — neighbor fetch by UID |
| `LayerGraph._node_key()` | Builder — consistent key derivation |
| `LayerGraph.to_neo4j()` | `save_layer_graph` — direct delegation |

The builder generalizes `LayerGraph.from_neo4j()`: instead of always seeding
from `fetch_all_by_layer()`, it accepts any seed list. `from_neo4j()` may be
refactored to delegate to the builder in a follow-up, but for now both can
coexist independently.

**No recursive expansion.** A `get_by_namespace` returns the namespace node +
its compounds + each compound's members + 1-hop neighbors. It does not
recursively follow transitive dependencies. Callers who need deeper traversal
call `get_by_compound` on specific nodes.

## The Six Scope Methods

Each is a short seed-fetcher that delegates to `_build_layer_graph`.

### `get_by_layer(layer: str) -> LayerGraph`

Fetches all nodes where `layer` matches, plus their 1-hop neighbors.

```python
seeds = CodeGraphNode.fetch_all_by_layer(layer)
return self._build_layer_graph(seeds)
```

Replaces `LayerGraph.from_neo4j(layer)`. The existing method can remain as a
thin alias or be deprecated in a follow-up.

### `get_by_source(source: str) -> LayerGraph`

Fetches all nodes where `source` matches, plus neighbors.

```python
seeds = CodeGraphNode.fetch_all_by_source(source)
return self._build_layer_graph(seeds)
```

Requires the new `CodeGraphNode.fetch_all_by_source()` class method (see
below).

### `get_by_namespace(qualified_name: str) -> LayerGraph`

Fetches the namespace node, then its direct compounds via the `compounds`
relationship manager. Seeds are the namespace + its compounds. The builder's
expansion step brings in each compound's members and 1-hop neighbors.

```python
ns = NamespaceNode.nodes.get(qualified_name=qualified_name)
seeds = [ns] + list(ns.compounds.all())
return self._build_layer_graph(seeds)
```

Raises `NamespaceNode.DoesNotExist` if the namespace is not found.

### `get_by_compound(qualified_name: str) -> LayerGraph`

Fetches a single compound node. The builder expands to its members and
neighbors.

```python
compound = self._get_node_by_qualified_name(qualified_name)
if compound is None:
    return LayerGraph(layer="design")
return self._build_layer_graph([compound])
```

### `get_by_neighbourhood(qualified_name: str) -> LayerGraph`

Fetches a single node of any type (compound, member, namespace), then the
builder's 1-hop expansion provides the neighbourhood.

```python
node = self._get_node_by_qualified_name(qualified_name)
if node is None:
    node = self._get_member_by_qualified_name(qualified_name)
if node is None:
    return LayerGraph(layer="design")
return self._build_layer_graph([node])
```

### `get_by_kind(kind: str, layer: str | None = None) -> LayerGraph`

Fetches all nodes of a given `kind`. Optional `layer` filter narrows the
result.

```python
seeds = CodeGraphNode.fetch_all_by_kind(kind, layer=layer)
return self._build_layer_graph(seeds)
```

Requires the new `CodeGraphNode.fetch_all_by_kind()` class method (see
below).

## Write Method

### `save_layer_graph(graph: LayerGraph) -> None`

Direct delegation to the existing `LayerGraph.to_neo4j()`:

```python
def save_layer_graph(self, graph: LayerGraph) -> None:
    graph.to_neo4j()
```

No new persistence logic. The method exists to keep all data access behind
the `GraphRepository` interface.

## New CodeGraphNode Class Methods

### `fetch_all_by_source(source: str) -> list[CodeGraphNode]`

Iterates `CodeGraphNode._registry`, calls `.nodes.filter(source=source)` on
each type that has a `source` property (checked via `defined_properties()`),
returns a flat list. Mirrors the existing `fetch_all_by_layer` pattern.

### `fetch_all_by_kind(kind: str, layer: str | None = None) -> list[CodeGraphNode]`

Iterates `_registry`, builds a neomodel filter with `kind=kind` (and
`layer=layer` if provided). Only applies to types that have both `kind` and
(optionally) `layer` properties. Returns a flat list.

Both methods check `defined_properties()` to skip types that don't have the
relevant field, following the same pattern as `fetch_by_layer`.

## Private Helpers on GraphRepository

### `_get_node_by_qualified_name(qualified_name: str) -> CodeGraphNode | None`

Searches compound and namespace types for a node matching the given
`qualified_name`. Tries `ClassNode`, `InterfaceNode`, `EnumNode`,
`UnionNode`, `ModuleNode`, `NamespaceNode` in order via
`.nodes.get_or_none(qualified_name=qn)`. Returns first match or `None`.

Needed because `qualified_name` is a `UniqueIdProperty` — each type owns its
own label in Neo4j, so there is no single label to query across.

### `_get_member_by_qualified_name(qualified_name: str) -> CodeGraphNode | None`

Same pattern for member types: `MethodNode`, `AttributeNode`,
`EnumValueNode`, `FunctionNode`, `DefineNode`.

## File Impact

### New file

| File | Contents |
|---|---|
| `src/codegraph/repository.py` | `GraphRepository` class |

### Modified files

| File | Change |
|---|---|
| `src/codegraph/models/tags.py` | Add `fetch_all_by_source()`, `fetch_all_by_kind()` |
| `src/codegraph/__init__.py` | Export `GraphRepository` |

### Unchanged

| File | Reason |
|---|---|
| `src/codegraph/models/compound.py` | No changes — models already atomized |
| `src/codegraph/models/member.py` | No changes |
| `src/codegraph/models/namespace.py` | No changes |
| `src/codegraph/models/file.py` | No changes |
| `src/codegraph/models/parameter.py` | No changes |
| `src/codegraph/constants.py` | No changes |
| `src/codegraph/diagram.py` | No changes |
| `src/codegraph/graph/__init__.py` | No changes in this iteration |

### Test impact

| Path | Change |
|---|---|
| `tests/repository/` | New — unit tests for each scope method, `save_layer_graph`, builder |
| `tests/test_graph_integration.py` | May update if `from_neo4j` refactoring is done |

## No-gos

- **Delete operations** — not in this iteration. Can be added to
  `GraphRepository` later.
- **`find_nodes()` or general filtered search** — not needed. The six scope
  methods cover the access patterns. Filtering a `LayerGraph` in Python is
  sufficient for ad-hoc queries.
- **`stats()`** — not needed. Derivable from a `LayerGraph` in Python.
- **Specialized container types** — `CompoundGraph`, `NamespaceGraph`,
  `OntologyGraph` are not introduced. `LayerGraph` is the universal return
  type.
- **`LayerGraph` modifications** — `LayerGraph` stays a data container. New
  methods go on `GraphRepository`.
- **Raw Cypher** — uses neomodel ORM for all queries. Only falls back to raw
  Cypher if a required query cannot be expressed through the ORM.