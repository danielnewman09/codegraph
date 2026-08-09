# Template contract — cpp pack

The directory layout **is** the template↔node-type mapping (plan R2):
one directory per codegraph node type, mirroring
`src/codegraph/models/`. `TemplatePack.resolve(node_type, kind,
variant)` finds `<NodeType>/<kind>.j2` → `<NodeType>/<kind>_decl.j2`
(declaration is the default render form) → `<NodeType>/<kind>_<variant>.j2`
→ `<NodeType>/default.j2` → pack `default.j2`.

| Node type (model module) | Template file(s) | Kind variants |
|---|---|---|
| `FileNode` (`models/file.py`) | `file_header.j2`, `file_source.j2` (document orchestrators) | header / source |
| `NamespaceNode` (`models/namespace.py`) | `NamespaceNode/namespace_open.j2`, `namespace_close.j2` | namespace |
| `ModuleNode` (`models/compound.py`) | `ModuleNode/module.j2` (renders as class keyword — Phase 1 approximation) | module |
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

## Forward declarations

Class-like compounds carry a **`forward_decls`** key (Phase 2):
`[{"name", "kind"}]` for every `DEPENDS_ON` class/struct target the
header should forward-declare before the class body — same-namespace
targets unqualified, cross-namespace qualified, ordered by name (R4).
Excluded: `std::` references, plain enums (not forward-declarable),
the class itself, and composed children (D9 nested-dups are defined in
this very header — forward-declaring them would be a redefinition).
Rendered by `macros.j2`'s `cg_class` as `class X;` / `struct X;` lines.

## Context keys

Per-node-type context dict keys are produced by
`codegraph.codegen.context.*` builders and pinned by
`tests/codegen/context/test_*.py`. Key conventions beyond the spec's
render-context section:

- **`type` is always the node-type discriminator** (`"ClassNode"`,
  `"MethodNode"`, …) — the attribute's C++ type lives under
  `type_signature` (never clobber `type`; see the ParameterNode
  serialization bug that motivated this).
- **`declaration`** is the authoritative render string for callable
  members (verbatim when the encoding is a full declaration; R3
  reconstruction otherwise) — templates must NOT re-assemble
  `return_type + " " + name + params`.
- **`uid`** (compounds + members) feeds the R7 provenance marker
  `// @codegraph uid:…`, emitted only when the pack runs with
  `emit_markers=True` (CLI `--markers`).  Default off — the markers are
  a provenance side-channel that breaks byte-fidelity with hand-written
  source, and `verify()` never reads them (it compares graph uids).
- **enum values** are under `enumerators`, not `values` (`node.values`
  resolves to `dict.values` in Jinja2).
- **FileContext** carries `namespaces` (qname-nested blocks) plus
  `blocks` (top-level non-namespaced contexts, as-built files).
- Callable members expose `has_body` (header/source split input) and
  `definition_scoped` (fully-qualified out-of-line definition, from the
  as-built `definition + argsstring`).

## Rendering conventions

- Output is normalized in Python (`TemplatePack._normalize`): per-line
  rstrip, ≤1 blank line, single trailing newline — snapshot goldens pin
  the exact bytes.
- Macros in `macros.j2` emit one output line per template line; each
  line ends with a literal newline (Jinja `trim_blocks` eats newlines
  after `%}` tags, so newlines follow expressions, never block tags).
- Unknown node types degrade to the pack-level `default.j2` explicit
  `// TODO(codegen): unsupported <NodeType>` (D6) — never silent output.

## Degradation

`default.j2` (pack level) renders an explicit
`// TODO(codegen): unsupported <NodeType>` comment rather than failing
silently (D6). `_skipped.j2` marks declared-skips in dry-run output.
