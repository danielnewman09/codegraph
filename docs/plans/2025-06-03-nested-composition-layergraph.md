# Implementation Plan: Nested Composition LayerGraph

Spec: `docs/specs/2025-06-03-nested-composition-layergraph-design.md`

## Step 1: Remove reverse COMPOSES RelationshipFrom from member nodes

**Files:** `src/codegraph/models/member.py`

Remove four `RelationshipFrom` declarations that create the directionality
ambiguity. Also remove the `RelationshipFrom` import if no longer used by
this file.

- Delete `MethodNode.parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')`
- Delete `MethodNode.parent_interface = RelationshipFrom(InterfaceNode, 'COMPOSES')`
- Delete `AttributeNode.parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')`
- Delete `EnumValueNode.parent_enum = RelationshipFrom(EnumNode, 'COMPOSES')`
- Remove `RelationshipFrom` from the neomodel import if no other uses remain
- Update docstring comments on each class that reference the removed attributes

**Test:** Run the existing member serialization tests
(`test_method_serialization`, `test_attribute_serialization`,
`test_enum_value_serialization`). These don't use the removed
attributes. Also run `test_attribute_defined_in_file`,
`test_method_defined_in_file`, `test_method_invokes_method` — these use
only outgoing relationships (DEFINED_IN, INVOKES) which are unaffected.

## Step 2: Add CompositeEntry dataclass and redesign LayerGraph fields

**Files:** `src/codegraph/graph/__init__.py`

Add the `CompositeEntry` dataclass above `LayerGraph`. Replace
`LayerGraph.nodes` and `LayerGraph.edges` with a single `entries:
dict[str, CompositeEntry]` field. Keep `_node_key` as-is. Remove the
`CodeGraphEdge` dataclass if present (partial change from earlier
session).

```python
@dataclass
class CompositeEntry:
    node: CodeGraphNode
    children: dict[str, dict[str, "CompositeEntry"]] = field(default_factory=dict)
    references: list[tuple[str, str, str]] = field(default_factory=list)
```

Leave `from_json`, `to_neo4j`, `to_json`, `from_neo4j` as stubs raising
`NotImplementedError` — they will be reimplemented in subsequent steps.

**Test:** `LayerGraph(layer="design")` should create an empty graph.
Layer validation should still work. Direct instantiation of
`CompositeEntry` should work. No existing tests pass yet — that is
expected until steps 3-5.

## Step 3: Implement LayerGraph.from_json with nesting logic

**Files:** `src/codegraph/graph/__init__.py`

Rewrite `from_json` to build the nested `entries` structure:

1. Parse all nodes, build a `uid_to_key` lookup and a flat
   `key_to_entry` dict (each key → `CompositeEntry(node=...)`).
2. Walk each node's JSON edge data:
   - If `relation_type == "COMPOSES"`: look up the target entry in
     `key_to_entry`, remove it from the root candidates set, and nest
     it under the source entry's `children[target_type][target_key]`.
     Handle both `target_local_id` and `target_uid` formats.
   - Otherwise: append `(relation_type, target_key, target_type)` to the
     source entry's `references`.
3. After walking all edges, root entries are the ones not removed from
   the root candidates set. Assign them to `self.entries`.
4. Infer `layer` from the first node with a `layer` field (fallback:
   `"design"`).

Add a helper method `_walk_entries` that yields all `CompositeEntry`
instances depth-first for later use by `to_neo4j` and `to_json`.

**Test:**
- `test_creates_nodes_from_fixture` — load `design_graph.json`, assert
  root entries contain files, namespaces, and orphan compounds.
- `test_node_types_are_correct` — spot-check root entry node types.
- `test_composes_children_nested` — `CalculatorEngine` entry has
  `MethodNode` and `AttributeNode` children.
- `test_non_composes_edges_as_references` — `CalculatorEngine` entry
  has `REALIZES` and `DEPENDS_ON` in `references`.
- `test_layer_inference`, `test_layer_defaults_to_design`,
  `test_empty_data`.

## Step 4: Implement LayerGraph.to_neo4j

**Files:** `src/codegraph/graph/__init__.py`

Rewrite `to_neo4j` to work from the nested structure:

1. Walk all entries depth-first, save every node instance.
2. For each entry:
   - **COMPOSES children:** call the parent node's relationship manager
     to connect each child. Use `find_relationship_manager(parent,
     "COMPOSES", child.node)` to resolve the correct manager (e.g.
     `class_node.methods` for MethodNode, `class_node.attributes` for
     AttributeNode, `namespace_node.compounds` for ClassNode).
   - **References:** look up the target entry by key (need a flat lookup
     across the tree; build one during the walk). Connect via
     `find_relationship_manager(source, relation_type, target_node)`.

Build a `_flat_index: dict[str, CompositeEntry]` during the save walk
so that reference targets can be resolved across the tree.

**Test:**
- `test_full_graph_roundtrip` — from_json → to_neo4j → to_json, assert
  types match, node count matches.
- `test_edge_persistence` — for each fixture edge, verify it appears in
  `serialize()["edges"]` after persistence. Replace `graph.nodes[key]`
  with entry lookup.

## Step 5: Implement LayerGraph.to_json and LayerGraph.from_neo4j

**Files:** `src/codegraph/graph/__init__.py`

**to_json:** Walk all entries depth-first via `_walk_entries`, call
`node.serialize()` on each. Return the flat JSON array. Order: root
entries first, then their children recursively.

**from_neo4j:** Fetch layer-matched nodes and 1-hop neighbors as today.
Build a flat dict of all nodes + uid-to-key map. Walk each compound
node's edges: COMPOSES edges → nest children; others → references.
Identify root nodes (not a COMPOSES target of any other node in the
set).

**Test:**
- `test_fetches_design_layer_nodes` — from_neo4j returns non-empty
  entries with ClassNode instances.
- `test_includes_neighbors_of_layer_nodes` — FileNodes appear.
- `test_to_json_roundtrip` — to_json produces a flat array with correct
  `type` fields.

## Step 6: Update GraphRepository._build_layer_graph

**Files:** `src/codegraph/repository.py`

Rewrite `_build_layer_graph` to return a `LayerGraph` with `entries`
instead of `nodes`/`edges`:

1. Collect all seed + neighbor nodes into a flat dict (as today).
2. Build `CompositeEntry` instances for each node.
3. Walk each node's edges: COMPOSES → nest children, others → references.
4. Determine root entries (nodes not composed by another node in the
   set).
5. Return `LayerGraph(layer=layer, entries={...})`.

Update all read methods that build `LayerGraph` to pass `entries`
instead of `nodes`/`edges`. The public API signatures don't change.

**Test:** Run `tests/repository/test_graph_repository.py` with updated
assertions (see step 8).

## Step 7: Update package exports

**Files:** `src/codegraph/__init__.py`

- Add `CompositeEntry` to imports and `__all__`.
- Remove `CodeGraphEdge` if present.
- Ensure `LayerGraph` still exports correctly.

**Test:** `python -c "from codegraph import CompositeEntry, LayerGraph"`
succeeds.

## Step 8: Update all tests

**Files:** Multiple test files.

Update every test that accesses `graph.nodes` or `graph.edges` to use
the new `entries`-based API.

### tests/test_layer_graph.py

- Replace `graph.nodes[key]` with entry lookup via depth-first walk.
  Add a `find_entry(graph, key)` test helper.
- Replace `len(graph.nodes)` with total node count across all entries.
- Replace `graph.edges` assertions with `entry.children` and
  `entry.references` assertions.
- Update `TestFromNeo4j` to use `graph.entries`.

### tests/test_graph_integration.py

- Replace `graph.nodes[key]` with entry lookup.
- Replace `graph.nodes.values()` iteration with tree walk.
- Update edge verification to check `entry.children` and
  `entry.references`.

### tests/repository/test_graph_repository.py

- Replace `result.nodes.values()` with entry walk.
- Replace `result.nodes` length checks with entry-count checks.
- Remove `TestBuildLayerGraphEdges` class (no `graph.edges` to check).
  Replace with assertions on `entry.children` and `entry.references`.

### tests/compound/test_class_composes_method.py, test_class_composes_attribute.py, test_enum_composes_value.py, test_interface_composes_method.py, test_namespace_composes_class.py

- These tests work at the individual-node level (not LayerGraph). They
  test `serialize()` output, which includes COMPOSES edges. After
  removing reverse COMPOSES from members, MethodNode/AttributeNode/
  EnumValueNode `serialize_edges()` will no longer emit incoming COMPOSES.
  Verify these tests still pass — the parent-side COMPOSES should still
  appear in the parent node's `serialize()["edges"]`.

### Member-level tests (test_attribute_defined_in_file, test_method_defined_in_file, test_method_invokes_method, test_method_deserialization, test_attribute_deserialization)

- These don't use `graph.nodes` or `graph.edges` directly. Verify they
  still pass. After removing reverse COMPOSES, MethodNode/AttributeNode
  serialization will have fewer edges (no incoming COMPOSES). If any test
  asserts edge count specifically, update it.

**Test:** Full pytest run. All tests should pass.

## Dependency order

```
Step 1 (remove reverse COMPOSES)
  ↓
Step 2 (CompositeEntry + LayerGraph fields)
  ↓
Step 3 (from_json)
  ↓
Step 4 (to_neo4j)
  ↓
Step 5 (to_json + from_neo4j)
  ↓
Step 6 (GraphRepository)
  ↓
Step 7 (exports)
  ↓
Step 8 (all tests)
```

Steps 1 and 7 can be tested independently. Steps 2-5 must be sequential
(each builds on the previous). Step 6 depends on steps 2-5. Step 8 is
the final validation gate.