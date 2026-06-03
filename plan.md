Implementation plan written to `docs/plans/2025-06-01-test-suite-completion.md`. It covers all three layers:

- **Layer 1**: 10 JSON fixtures + 10 test files for per-type roundtrip (ClassNode, InterfaceNode, EnumNode, ModuleNode, UnionNode, EnumValueNode, FunctionNode, DefineNode, NamespaceNode, ParameterNode)
- **Layer 2**: 9 edge test files — one per relationship type (COMPOSES ×5, INHERITS_FROM, REALIZES, DEPENDS_ON, INVOKES)
- **Layer 3**: Updated `design_graph.json` in `CodeGraphNode.serialize()` format + `test_graph_integration.py`