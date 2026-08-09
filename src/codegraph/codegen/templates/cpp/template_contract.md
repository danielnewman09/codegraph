# Template contract — cpp pack

The directory layout **is** the template↔node-type mapping (plan R2):
one directory per codegraph node type, mirroring
`src/codegraph/models/`. `TemplatePack.resolve(node_type, kind)` finds
`<NodeType>/<kind>.j2` → `<NodeType>/default.j2` → pack `default.j2`.

| Node type (model module) | Template file(s) | Kind variants |
|---|---|---|
| `FileNode` (`models/file.py`) | `file_header.j2`, `file_source.j2` (document orchestrators) | header / source |
| `NamespaceNode` (`models/namespace.py`) | `NamespaceNode/namespace_open.j2`, `namespace_close.j2` | namespace |
| `ModuleNode` (`models/compound.py`) | `ModuleNode/module.j2` (renders as namespace) | module |
| `ClassNode` | `ClassNode/class.j2`, `ClassNode/struct.j2`, `ClassNode/type_parameter.j2` | class / struct / type_parameter |
| `InterfaceNode` | `InterfaceNode/interface.j2` | interface |
| `EnumNode` | `EnumNode/enum.j2`, `EnumNode/enum_class.j2` | enum / enum_class |
| `UnionNode` | `UnionNode/union.j2` | union |
| `ConceptNode` | `ConceptNode/concept.j2` | concept |
| `MethodNode` | `MethodNode/method_decl.j2`, `MethodNode/method_defn.j2` | method (decl in header, defn in source) |
| `FunctionNode` | `FunctionNode/function_decl.j2`, `FunctionNode/function_defn.j2` | function |
| `AttributeNode` | `AttributeNode/attribute.j2`, `AttributeNode/typedef.j2` | attribute / typedef |
| `EnumValueNode` | `EnumValueNode/enumvalue.j2` | enumvalue |
| `DefineNode` | `DefineNode/define.j2` | define |
| `ParameterNode` | `ParameterNode/parameter.j2` | parameter |
| `ImplementationNode` | `ImplementationNode/implementation.j2` | implementation |
| declared skips | `_skipped.j2` | Literal / Test* / HLR / LLR / Component / Dependency / Language / ProjectMeta |
| abstract bases | (resolved by concrete subclass dir) | CompoundNode / MemberNode |

## Context keys

Per-node-type context dict keys are documented in the render-context
section of `docs/specs/2026-08-08-codegen-export-design.md` (file /
compound / member contexts). Phase 1 pins them exactly via
`tests/codegen/context/test_*.py` goldens — templates may rely on
documented keys and nothing else (D3).

## Degradation

`default.j2` (pack level) renders an explicit
`// TODO: unsupported <NodeType>` comment rather than failing silently
(D6). `_skipped.j2` marks declared-skips in dry-run output.
