The plan has been written to `docs/plans/2025-06-07-composes-direction.md`. It covers all 7 steps in order:

1. **Add `RelationshipFrom('COMPOSES')` descriptors** on MethodNode, AttributeNode, EnumValueNode, FunctionNode, ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode, and NamespaceNode — with exact code and placement for each model file.

2. **Add `walk_edges()` method** on `CodeGraphNode` in `tags.py` — full implementation with `is_outgoing` boolean derived from descriptor type.

3. **Update `_build_layer_graph`** in `repository.py` — swap `serialize_edges()` → `walk_edges()` in Phase 2, add direction-aware COMPOSES nesting in Phase 4 with full replacement code.

4. **Update `from_neo4j`** in `graph.py` — same swap and direction-aware logic.

5. **Add roundtrip tests** — 10 new test files, one per descriptor, following the existing pattern.

6. **Add graph-building tests** — child-seeded query tests in `test_graph_repository.py` and `test_layer_graph.py` verifying that incoming COMPOSES correctly nests children under parents.

7. **Verify existing tests pass** — confirms no existing test files need modification since new incoming edges are additive and don't conflict with parent-side assertions.