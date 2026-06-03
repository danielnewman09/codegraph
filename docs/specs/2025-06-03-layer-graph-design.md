# LayerGraph Design Spec

**Date:** 2025-06-03  
**Status:** Approved

## Summary

Introduce a `LayerGraph` Python-only container that serves as the top-level API for
serializing, deserializing, and querying an entire design view of the codebase graph.
Push layer-aware query capability and `find_relationship_manager` down to
`CodeGraphNode` so that `LayerGraph` stays thin. Retire the standalone `load_graph()` function in
favor of `LayerGraph.from_json()`. Separate persistence (`to_neo4j()`) from
deserialization (`from_json()`) so that constructing a `LayerGraph` from JSON has
no database side-effects.

## Motivation

Currently there is no single entry point for interacting with a complete graph. Tests
use the ad-hoc `load_graph()` function and manually loop over `node.serialize()`. A
`LayerGraph` container provides a clean, typed API: load from JSON, persist to Neo4j,
query from Neo4j by layer, and serialize back to JSON. Crucially, `from_json()` is a
pure deserialization step — it builds a `LayerGraph` in memory with no database
interaction. Persistence is a separate, explicit `to_neo4j()` call.

## Changes

### 1. Add query methods and `find_relationship_manager` to `CodeGraphNode`

**File:** `src/codegraph/models/tags.py`

Add three class methods. No `_node_category` attribute — `fetch_by_layer` uses
`defined_properties()` to check for a `layer` property, and `fetch_all_by_layer`
iterates `_registry`. This avoids redundant metadata since the class hierarchy
and registry already encode everything needed.

```python
class CodeGraphNode:

    @classmethod
    def find_relationship_manager(cls, source, relation_type: str, target):
        """Find the relationship manager on *source* matching both
        *relation_type* and the class of *target*.

        Returns the relationship manager attribute (e.g. ``source.methods``).
        Raises ``ValueError`` if no matching manager is found.
        """

    @classmethod
    def fetch_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
        """Fetch all persisted instances of this type matching the given layer.

        Uses neomodel's .nodes.filter(layer=layer). Returns an empty list
        for types that don't have a ``layer`` property (FileNode, ParameterNode).
        """

    @classmethod
    def fetch_all_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
        """Iterate the _registry, call fetch_by_layer on each, return a flat list
        of all nodes matching the layer across all registered types."""
```

`fetch_by_layer` uses neomodel's `cls.nodes.filter(layer=layer)` for types that have
a `layer` property (discovered via `defined_properties()`), and returns `[]` for
types without one (FileNode, ParameterNode).

`fetch_all_by_layer` iterates `CodeGraphNode._registry`, calls `fetch_by_layer` on
each, and returns a deduplicated flat list.

### 2. Add `LayerGraph` dataclass to `src/codegraph/graph/__init__.py`

```python
@dataclass
class LayerGraph:
    layer: str                                    # "design" | "as-built" | "dependency"
    nodes: dict[str, CodeGraphNode] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)  # logical edges (not yet persisted)

    @classmethod
    def from_neo4j(cls, layer: str) -> "LayerGraph":
        """Query Neo4j for all nodes where .layer == layer, plus their
        first-level neighbors. Collect into a LayerGraph."""

    @classmethod
    def from_json(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from JSON array (as produced by to_json()).
        Pure deserialization — no database interaction.
        Infers layer from the first node that has a ``layer`` field."""

    def to_neo4j(self) -> None:
        """Persist all nodes and edges to Neo4j.
        Saves each node, then connects all edges using
        CodeGraphNode.find_relationship_manager()."""

    def to_json(self) -> list[dict]:
        """Serialize all nodes + edges to a JSON-compatible list of dicts.
        Each dict includes ``type``, properties, and ``edges``."""
```

#### `from_neo4j(layer)` algorithm

1. Call `CodeGraphNode.fetch_all_by_layer(layer)` → get all layer-matched nodes.
2. Build the `nodes` dict keyed by `_node_key()`.
3. For each layer-matched node, call `node.serialize_edges()` → collect all
   neighbor node UIDs.
4. Fetch each neighbor from Neo4j (by UID), add to `nodes` dict if not already
   present. This ensures both endpoints of every edge touching a layer-matched
   node are included, even if the neighbor's layer is different.
5. Return `LayerGraph(layer=layer, nodes=nodes)`.

#### `from_json(data)` algorithm

Pure deserialization — no database side-effects. Steps:

1. Parse each item via `CodeGraphNode.from_json()`. Infer `layer` from the
   first node that has a `layer` field (fallback: `"design"`).
2. Build `nodes` dict keyed by `_node_key()`.
3. Collect logical edges from each item's `"edges"` key into `self.edges`,
   storing `(source_key, relation_type, target_key, target_type)` tuples.
4. Return `LayerGraph(layer=layer, nodes=nodes, edges=edges)`.

#### `to_neo4j()` algorithm

1. Save each node in `self.nodes` to Neo4j (calling `.save()`).
2. For each edge in `self.edges`, look up source and target nodes in `self.nodes`,
   call `CodeGraphNode.find_relationship_manager(source, relation_type, target)`
   to find the correct relationship manager, and call `.connect(target)`.

This is the logic currently in `load_graph()`, extracted into an explicit method.

#### `to_json()` algorithm

Iterate `self.nodes.values()`, call `node.serialize()` on each, return the list.

### 3. Move helpers from `loaders.py` into `CodeGraphNode` / `LayerGraph`

- `_node_key()` → move to `LayerGraph` as a static method. Accepts both
  `dict` (raw JSON) and `CodeGraphNode` instances — for dicts, uses
  `data["type"]` and `data.get("path", data["name"])`; for nodes, uses
  `node.name` / `node.path`.
- `_find_relationship_manager()` → move to `CodeGraphNode` as a class method,
  since it inspects `RelationshipTo`/`RelationshipFrom` descriptors on the
  node class.

### 4. Retire `load_graph()` from `loaders.py`

The public API shifts to `LayerGraph.from_json()`. `loaders.py` is removed or
reduced to a thin re-export for backward compatibility. The integration test
and any other callers update to use `LayerGraph`.

### 5. Update callers

- `tests/test_graph_integration.py` — switch from `load_graph()` to
  `LayerGraph.from_json()`.
- `src/codegraph/__init__.py` — export `LayerGraph`, remove `load_graph`
  (or keep as deprecated alias).
- Any edge tests that use `load_graph()` update accordingly.

### 6. Update integration test

The integration test becomes:

```python
def test_graph_integration():
    with open(FIXTURE) as f:
        nodes_data = json.load(f)

    # Pure deserialization — no DB interaction
    graph = LayerGraph.from_json(nodes_data)

    # Explicit persistence
    graph.to_neo4j()

    # Serialize to JSON and write for roundtrip verification
    serialized = graph.to_json()
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "graph_integration.json"
    with open(out_path, "w") as f:
        json.dump(serialized, f, indent=2)

    # Read back and verify roundtrip
    with open(out_path) as f:
        loaded = json.load(f)

    restored = LayerGraph.from_json(loaded)
    restored.to_neo4j()
    ...  # assertions on types, fields, edges
```

## File impact

| File | Action |
|---|---|
| `src/codegraph/models/tags.py` | Add `find_relationship_manager`, `fetch_by_layer`, `fetch_all_by_layer` |
| `src/codegraph/graph/__init__.py` | Add `LayerGraph` dataclass |
| `src/codegraph/loaders.py` | Remove or reduce (helpers move to `CodeGraphNode`) |
| `src/codegraph/__init__.py` | Export `LayerGraph`, update `load_graph` |
| `tests/test_graph_integration.py` | Switch to `LayerGraph.from_json()` |

## No-gos

- `LayerGraph` is **not** a Neo4j node — it's a Python-only container.
- `from_neo4j()` does **not** recursively expand neighbors — only first-level.
- No changes to the Neo4j schema (no new labels or constraint changes).