The implementation plan is written to `docs/plans/2025-06-03-nested-composition-layergraph.md`. Here's a summary of the 8 steps in dependency order:

1. **Remove reverse COMPOSES** from member nodes — eliminates the directionality ambiguity at its source
2. **Add CompositeEntry + redesign LayerGraph fields** — structural foundation (entries replacing nodes/edges)
3. **Implement from_json** — builds the nested composition structure from JSON
4. **Implement to_neo4j** — persists from the nested structure, connecting COMPOSES children and references
5. **Implement to_json + from_neo4j** — serialization and Neo4j query with nesting
6. **Update GraphRepository** — adapt `_build_layer_graph` and all read methods
7. **Update package exports** — add CompositeEntry, clean up CodeGraphEdge
8. **Update all tests** — final validation gate, update every `graph.nodes`/`graph.edges` assertion

Each step is independently testable and builds on the previous one.