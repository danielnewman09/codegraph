# Namespace Composition Design — Expand COMPOSES to All Compound Types + FunctionNode

**Date:** 2026-06-05  
**Status:** Approved  

## Overview

Expand `NamespaceNode.COMPOSES` relationships from a single target type (`ClassNode`) to all compound types plus `FunctionNode` and self-referential `NamespaceNode`. This allows namespaces to own the full set of entities they semantically contain — interfaces, enums, unions, modules, free functions, and nested namespaces — not just classes.

## 1. NamespaceNode Model Changes

Replace the single `compounds` descriptor with 7 named `RelationshipTo` descriptors, one per target type, all using the `COMPOSES` relationship label. This mirrors the pattern used by `ClassNode` (which has `methods` → MethodNode and `attributes` → AttributeNode via COMPOSES).

**Before:**

```python
compounds = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')
```

**After:**

```python
# --- NamespaceNode relationships ----------------------------------------
#
#  • COMPOSES  — NamespaceNode → ClassNode | InterfaceNode | EnumNode |
#    UnionNode | ModuleNode | FunctionNode | NamespaceNode
#    The namespace owns/contains these entities.  Each target type gets
#    its own descriptor so neomodel can dispatch correctly.
#
#  Self-referential COMPOSES (namespaces → namespaces) supports
#  nested namespaces (e.g. outer::inner).
# --------------------------------------------------------------------------

classes     = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')
interfaces  = RelationshipTo('codegraph.models.compound.InterfaceNode', 'COMPOSES')
enums       = RelationshipTo('codegraph.models.compound.EnumNode', 'COMPOSES')
unions      = RelationshipTo('codegraph.models.compound.UnionNode', 'COMPOSES')
modules     = RelationshipTo('codegraph.models.compound.ModuleNode', 'COMPOSES')
functions   = RelationshipTo('codegraph.models.member.FunctionNode', 'COMPOSES')
namespaces  = RelationshipTo('NamespaceNode', 'COMPOSES')
```

The old `compounds` attribute is removed entirely — replaced by `classes`. No backwards-compatibility alias. The previous name was misleading (it targeted only `ClassNode` despite implying "all compound types").

The `_llm_fields` set (`{"qualified_name", "name", "kind", "description"}`) is unchanged.

## 2. GraphRepository Changes

`get_by_namespace` currently seeds only `ClassNode` children:

```python
seeds = [ns] + list(ns.compounds.all())
```

Updated to traverse all 7 COMPOSES descriptors:

```python
seeds = (
    [ns]
    + list(ns.classes.all())
    + list(ns.interfaces.all())
    + list(ns.enums.all())
    + list(ns.unions.all())
    + list(ns.modules.all())
    + list(ns.functions.all())
    + list(ns.namespaces.all())
)
```

No other `GraphRepository` changes needed. The `_build_layer_graph` method is generic — it walks `serialize_edges()` on every collected node, which already iterates all relationship descriptors.

The method docstring is updated from "Fetch a namespace, its compounds, and their 1-hop neighbors." to "Fetch a namespace, its composed entities (classes, interfaces, enums, unions, modules, functions, and sub-namespaces), and their 1-hop neighbors."

## 3. LayerGraph and Serialization — No Changes Needed

All LayerGraph code handles COMPOSES generically:

- **`find_relationship_manager`** — Dispatches on `(source_class, relation_type, target_class)`. Adding new descriptors on `NamespaceNode` means the correct manager is found automatically.
- **`serialize_edges`** — Walks all `RelationshipTo`/`RelationshipFrom` descriptors. New ones are included automatically.
- **`from_json` / `_from_json_flat` / `_from_json_nested`** — Operates on generic dict data keyed by `target_type` and `relation_type` strings.
- **`to_neo4j`** — Uses `find_relationship_manager(source_node, "COMPOSES", child_entry.node)` which dispatches correctly.
- **`to_json` / `_serialize_entry`** — Iterates all type groups in `entry.children` generically.
- **`from_neo4j`** — Fetches all layer-matched nodes, then walks their `serialize_edges()` output.

No modifications to `src/codegraph/graph/__init__.py` are required.

## 4. Constants — No Changes Needed

`PREDICATE_TO_REL_TYPE` and `DEFAULT_PREDICATES` already define `"composes": "COMPOSES"`. The predicate vocabulary is unchanged — only the relationships using it on `NamespaceNode` have expanded.

## 5. Test Changes

### 5a. Existing namespace test — rename

`tests/namespace/test_namespace_composes_class.py`: update `ns.compounds.connect()` → `ns.classes.connect()` and `ns.compounds.all()` → `ns.classes.all()`.

### 5b. New roundtrip tests — one per target type

Add 6 new test files following the same pattern as `test_namespace_composes_class.py`:

| File | Tests |
|---|---|
| `tests/namespace/test_namespace_composes_interface.py` | NamespaceNode → InterfaceNode COMPOSES roundtrip |
| `tests/namespace/test_namespace_composes_enum.py` | NamespaceNode → EnumNode COMPOSES roundtrip |
| `tests/namespace/test_namespace_composes_union.py` | NamespaceNode → UnionNode COMPOSES roundtrip |
| `tests/namespace/test_namespace_composes_module.py` | NamespaceNode → ModuleNode COMPOSES roundtrip |
| `tests/namespace/test_namespace_composes_function.py` | NamespaceNode → FunctionNode COMPOSES roundtrip |
| `tests/namespace/test_namespace_composes_namespace.py` | NamespaceNode → NamespaceNode COMPOSES roundtrip (nesting) |

Each test: create namespace, create target node, connect via named descriptor, verify edge in `serialize()`, verify `from_json()` roundtrip, verify `.all()` returns connected node.

### 5c. Design graph fixture — add non-ClassNode compositions

Update `tests/data/design_graph.json` to make the `calc` namespace compose `ICalculator` (InterfaceNode) and `Operation` (EnumNode) in addition to the existing `CalculatorEngine` and `CalculatorResult` (ClassNode). Add a `FunctionNode` under one namespace. This ensures LayerGraph roundtrip tests exercise the new composition types.

### 5d. GraphRepository test — update references

`tests/repository/test_graph_repository.py`: update `ns.compounds.all()` → `ns.classes.all()` and add assertions that the seeded graph includes non-Class composition targets.

## 6. Files Modified

| File | Change |
|---|---|
| `src/codegraph/models/namespace.py` | Replace 1 descriptor with 7, update docstring |
| `src/codegraph/repository.py` | Update `get_by_namespace` seeds, update docstring |
| `tests/namespace/test_namespace_composes_class.py` | `compounds` → `classes` |
| `tests/namespace/test_namespace_composes_interface.py` | New |
| `tests/namespace/test_namespace_composes_enum.py` | New |
| `tests/namespace/test_namespace_composes_union.py` | New |
| `tests/namespace/test_namespace_composes_module.py` | New |
| `tests/namespace/test_namespace_composes_function.py` | New |
| `tests/namespace/test_namespace_composes_namespace.py` | New |
| `tests/data/design_graph.json` | Add non-ClassNode compositions under namespaces |
| `tests/repository/test_graph_repository.py` | Update `compounds` → `classes`, expand assertions |

## 7. Out of Scope

- `DefineNode` composition — defines are preprocessor-level, not namespace-level.
- Adding COMPOSES to other node types (e.g., `ModuleNode` composing types) — separate future work.
- Aggregator convenience methods on `NamespaceNode` (e.g., `_all_children()`) — can be added later if needed.