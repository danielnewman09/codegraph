# Nested `to_json` / `from_json` for LayerGraph

## Problem

`LayerGraph.to_json()` outputs a flat list where every node (including
composed children) is a separate entry and COMPOSES edges appear in the
`edges` array alongside other relationship types. The desired output nests
composed children inline under a `composes` key on their parent, recursively.
`from_json()` only accepts the current flat format.

## Current state

The internal model already reflects the nested structure:

- `CompositeEntry` has `children: dict[str, dict[str, CompositeEntry]]` —
  composed children keyed by target type then target key.
- `LayerGraph.entries` holds only root entries (nodes not composed by another).

The gap is in the serialization/deserialization layer only.

## Design

### `to_json()` — nested serialization

Replace the flat `node.serialize()` walk with a recursive tree serializer:

1. Walk root entries only.
2. For each entry, produce a dict from `node.serialize()` but:
   - Remove COMPOSES edges from the `edges` array.
   - Add a `composes` key containing a list of recursively serialized
     child entries (one per composed child across all target types).
3. If a node has no composed children, omit the `composes` key entirely.
4. Composed children must not appear as top-level entries.

The children appear as a flat list under `composes` (not keyed by type),
matching the `updated_graph_integration.json` example format.

### `from_json()` — accept both formats

Detect the format by checking whether any entry has a `composes` key.

**Nested format** (new): recursively walk each entry's `composes` list
to build the `CompositeEntry` tree directly. Edges in `edges` are
non-COMPOSES only and stored as references. No two-phase COMPOSES
resolution needed.

**Flat format** (existing): retain current logic — Phase 1 create entries,
Phase 2 resolve edges into nesting/references, Phase 3 determine roots.

### Test

Add a `TestToJsonNested` class that:

1. Ingests `design_graph.json` via `from_json`.
2. Persists to Neo4j via `to_neo4j`.
3. Calls `to_json()` and writes the output to
   `tests/unit_test_data/layer_graph_export.json`.
4. Asserts structural properties of the output:
   - Root-level entries have no COMPOSES edges in their `edges` arrays.
   - Entries that compose children have a `composes` key.
   - Entries without composed children have no `composes` key.
   - Composed children do not appear as root-level entries.

## Files to modify

| File | Change |
|---|---|
| `src/codegraph/graph/__init__.py` | Rewrite `to_json()` for nested output; add nested-format path in `from_json()` |
| `tests/test_layer_graph.py` | Add `TestToJsonNested` class; add `from_json` nested-format tests |
| `tests/unit_test_data/layer_graph_export.json` | New: persisted nested output fixture |