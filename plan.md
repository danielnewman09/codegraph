The implementation plan has been written to `docs/plans/2025-06-03-layer-graph-implementation.md`. Here's a summary of the 7 steps:

1. **Add `_node_category` and query methods to `CodeGraphNode`** — `_node_category` attribute, `find_relationship_manager()`, `fetch_by_layer()`, `fetch_all_by_layer()`
2. **Add `_node_category` to all concrete subclasses** — compound/member/namespace/file/parameter
3. **Add `LayerGraph` dataclass** — `from_json()`, `to_neo4j()`, `to_json()`, `from_neo4j()`, `_node_key()` in `graph/__init__.py`
4. **Update `__init__.py` exports** — swap `load_graph` for `LayerGraph`
5. **Rewrite integration test** — use `LayerGraph.from_json()` + `.to_neo4j()` instead of `load_graph()`
6. **Delete `loaders.py`** — all logic moved to `LayerGraph` and `CodeGraphNode`
7. **Final cleanup** — remove stale imports

Each step is independently testable with the 28 existing tests.