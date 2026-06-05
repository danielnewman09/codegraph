# Implementation Plan: Namespace COMPOSES Expansion

**Design spec:** `docs/specs/2026-06-05-namespace-composes-design.md`  
**Date:** 2026-06-05

## Summary

Expand `NamespaceNode.COMPOSES` from a single `ClassNode` target to 7 explicit named descriptors (`classes`, `interfaces`, `enums`, `unions`, `modules`, `functions`, `namespaces`). Update all references. Add roundtrip tests for each new target type. Update integration fixture.

---

## Step 1: Update NamespaceNode model

**File:** `src/codegraph/models/namespace.py`

1. Add the `RelationshipTo` import (already present via `neomodel` import — verify).
2. Remove the `compounds` descriptor and its doc comment block.
3. Add 7 new descriptors with the expanded doc comment block:

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

**Verification:** After saving, run `python -c "from codegraph.models.namespace import NamespaceNode; print([r for r in NamespaceNode.serialize_relationships()])"` to confirm 7 COMPOSES relationship descriptors are registered, all with direction OUTGOING and relation_type COMPOSES.

---

## Step 2: Update GraphRepository

**File:** `src/codegraph/repository.py`

1. In `get_by_namespace`, replace:

```python
seeds = [ns] + list(ns.compounds.all())
```

with:

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

2. Update the docstring from:

```
Fetch a namespace, its compounds, and their 1-hop neighbors.
```

to:

```
Fetch a namespace, its composed entities (classes, interfaces, enums,
unions, modules, functions, and sub-namespaces), and their -hop neighbors.
```

**Verification:** `grep -n "compounds" src/codegraph/repository.py` returns no results.

---

## Step 3: Update existing namespace test — rename `compounds` → `classes`

**File:** `tests/namespace/test_namespace_composes_class.py`

1. Change `namespace_node.compounds.connect(class_node)` → `namespace_node.classes.connect(class_node)`
2. Change `namespace_node.compounds.all()` → `namespace_node.classes.all()`

**Verification:** Run `pytest tests/namespace/test_namespace_composes_class.py` (requires Neo4j).

---

## Step 4: Add 6 new roundtrip test files

Create one test file per new target type, following the existing `test_namespace_composes_class.py` pattern. Each test creates a NamespaceNode, creates the target node, connects via the named descriptor, verifies the COMPOSES edge in `serialize()`, verifies `from_json()` roundtrip, and verifies `.all()` returns the connected node.

### 4a. `tests/namespace/test_namespace_composes_interface.py`

```python
"""Unit test: NamespaceNode COMPOSES InterfaceNode relationship roundtrip."""
from codegraph.models.compound import InterfaceNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `namespace_node.interfaces.connect(interface_node)`
- Assert: `composes_edges[0]["target_type"] == "InterfaceNode"`
- Assert: `len(namespace_node.interfaces.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_interface.json`

### 4b. `tests/namespace/test_namespace_composes_enum.py`

```python
"""Unit test: NamespaceNode COMPOSES EnumNode relationship roundtrip."""
from codegraph.models.compound import EnumNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `namespace_node.enums.connect(enum_node)`
- Assert: `composes_edges[0]["target_type"] == "EnumNode"`
- Assert: `len(namespace_node.enums.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_enum.json`

### 4c. `tests/namespace/test_namespace_composes_union.py`

```python
"""Unit test: NamespaceNode COMPOSES UnionNode relationship roundtrip."""
from codegraph.models.compound import UnionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `namespace_node.unions.connect(union_node)`
- Assert: `composes_edges[0]["target_type"] == "UnionNode"`
- Assert: `len(namespace_node.unions.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_union.json`

### 4d. `tests/namespace/test_namespace_composes_module.py`

```python
"""Unit test: NamespaceNode COMPOSES ModuleNode relationship roundtrip."""
from codegraph.models.compound import ModuleNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `namespace_node.modules.connect(module_node)`
- Assert: `composes_edges[0]["target_type"] == "ModuleNode"`
- Assert: `len(namespace_node.modules.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_module.json`

### 4e. `tests/namespace/test_namespace_composes_function.py`

```python
"""Unit test: NamespaceNode COMPOSES FunctionNode relationship roundtrip."""
from codegraph.models.member import FunctionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `namespace_node.functions.connect(function_node)`
- Assert: `composes_edges[0]["target_type"] == "FunctionNode"`
- Assert: `len(namespace_node.functions.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_function.json`

### 4f. `tests/namespace/test_namespace_composes_namespace.py`

```python
"""Unit test: NamespaceNode COMPOSES NamespaceNode relationship roundtrip (nesting)."""
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
```

- Connect: `outer_ns.namespaces.connect(inner_ns)`
- Assert: `composes_edges[0]["target_type"] == "NamespaceNode"`
- Assert: `len(outer_ns.namespaces.all()) == 1`
- Fixture: `unit_test_data/namespace_composes_namespace.json`

**Verification:** Run each new test individually: `pytest tests/namespace/test_namespace_composes_<type>.py`

---

## Step 5: Update design_graph.json fixture

**File:** `tests/data/design_graph.json`

Add COMPOSES edges from the `calc` namespace to `ICalculator` (InterfaceNode) and `Operation` (EnumNode). Add a `FunctionNode` under the `calc` namespace. This ensures LayerGraph roundtrip tests exercise the new composition types.

Specific additions:

### 5a. Add FunctionNode to the flat data

Add a new `FunctionNode` entry (e.g., `calc::formatResult`) to the top-level JSON array:

```json
{
    "type": "FunctionNode",
    "name": "formatResult",
    "qualified_name": "calc::formatResult",
    "kind": "function",
    "type_signature": "string",
    "argsstring": "(double value)",
    "visibility": "public",
    "brief_description": "Formats a numeric result as a string.",
    "source": "calculator",
    "edges": []
}
```

### 5b. Add COMPOSES edges to the calc NamespaceNode

Add 3 new edges to the `calc` NamespaceNode's `edges` array:

```json
{
    "relation_type": "COMPOSES",
    "target_type": "InterfaceNode",
    "target_local_id": "calc::ICalculator"
},
{
    "relation_type": "COMPOSES",
    "target_type": "EnumNode",
    "target_local_id": "calc::Operation"
},
{
    "relation_type": "COMPOSES",
    "target_type": "FunctionNode",
    "target_local_id": "calc::formatResult"
}
```

This changes the `calc` namespace from composing 2 ClassNodes to composing 2 ClassNodes + 1 InterfaceNode + 1 EnumNode + 1 FunctionNode (5 entities total).

### 5c. Verify fixture counts

After edits, the fixture should have:
- 6 FileNodes (unchanged)
- 2 NamespaceNodes (unchanged, but `calc` has more COMPOSES edges)
- 1 InterfaceNode (unchanged)
- 4 ClassNodes (unchanged)
- 1 EnumNode (unchanged)
- 2 EnumValueNodes (unchanged)
- 7 MethodNodes (6 original + unchanged)
- 4 AttributeNodes (unchanged)
- 1 FunctionNode (new)

Total: 28 nodes (was 27).

**Verification:** Run `pytest tests/test_layer_graph.py` to confirm all LayerGraph tests pass with the updated fixture. This is critical — if any test breaks here, the fixture edits need adjustment.

---

## Step 6: Update GraphRepository test

**File:** `tests/repository/test_graph_repository.py`

1. In `TestGetByNamespace.test_includes_namespace_and_compounds`, rename references:
   - No explicit `.compounds` calls in this test currently, but the test name is descriptive. Consider adding a new assertion that non-Class composed entities appear in the result.

2. Add a new test method `test_includes_non_class_composed_entities` to `TestGetByNamespace`:

```python
def test_includes_non_class_composed_entities(self, repo, seeded_graph):
    """Namespace should include interfaces, enums, and functions composed by it."""
    result = repo.get_by_namespace("calc")
    node_types = {type(n).__name__ for n in _all_nodes(result)}
    # The calc namespace composes classes, interface, enum, and function
    assert "InterfaceNode" in node_types
    assert "EnumNode" in node_types
    assert "FunctionNode" in node_types
```

**Verification:** Run `pytest tests/repository/test_graph_repository.py -k "test_includes"` (requires Neo4j).

---

## Step 7: Update LayerGraph roundtrip assertions (if needed)

**File:** `tests/test_layer_graph.py`

The `test_composes_key_present_for_parents` test currently asserts:

```python
# NamespaceNode "calc" composes CalculatorEngine, CalculatorResult
calc_entry = next(e for e in output if e.get("name") == "calc")
assert "composes" in calc_entry
assert len(calc_entry["composes"]) == 2
```

After the fixture update (Step 5), the `calc` namespace now composes 5 children (2 ClassNodes + 1 InterfaceNode + 1 EnumNode + 1 FunctionNode). Update this assertion:

```python
assert len(calc_entry["composes"]) == 5
```

**Verification:** Run `pytest tests/test_layer_graph.py` and confirm all tests pass.

---

## Step 8: Final integration verification

Run the full test suite:

```bash
pytest tests/ -v
```

Verify:
- All 7 namespace COMPOSES roundtrip tests pass
- LayerGraph roundtrip tests pass with updated fixture
- GraphRepository tests pass
- No references to `NamespaceNode.compounds` or `ns.compounds` remain in source or tests

```bash
grep -rn "\.compounds\b" src/ tests/ --include="*.py"
```

Should return zero results.

---

## File change summary

| Step | File | Change |
|------|------|--------|
| 1 | `src/codegraph/models/namespace.py` | Replace `compounds` with 7 named COMPOSES descriptors |
| 2 | `src/codegraph/repository.py` | Update `get_by_namespace` seeds, update docstring |
| 3 | `tests/namespace/test_namespace_composes_class.py` | `compounds` → `classes` (2 lines) |
| 4a | `tests/namespace/test_namespace_composes_interface.py` | New file |
| 4b | `tests/namespace/test_namespace_composes_enum.py` | New file |
| 4c | `tests/namespace/test_namespace_composes_union.py` | New file |
| 4d | `tests/namespace/test_namespace_composes_module.py` | New file |
| 4e | `tests/namespace/test_namespace_composes_function.py` | New file |
| 4f | `tests/namespace/test_namespace_composes_namespace.py` | New file |
| 5 | `tests/data/design_graph.json` | Add FunctionNode, add COMPOSES edges from calc namespace |
| 6 | `tests/repository/test_graph_repository.py` | Add test for non-Class composed entities |
| 7 | `tests/test_layer_graph.py` | Update `calc_entry["composes"]` assertion count 2→5 |

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Neo4j schema needs updating for new relationship types | neomodel creates relationship types dynamically; no schema migration needed. Running `db.install_all_labels()` in conftest.py handles this. |
| Existing Neo4j data with `:COMPOSES` from NamespaceNode to ClassNode only | The `COMPOSES` relationship type already exists; this just adds more target node labels. Existing data is compatible — old `ns.compounds` edges still work as `COMPOSES` to `ClassNode`. However, calling `ns.compounds.all()` will now fail (renamed to `ns.classes`). This is a breaking API change, which is acceptable since the codebase has full control over all callers. |
| `test_layer_graph.py` assertion on `calc_entry["composes"]` count | Updated in Step 7. |

## Rollback

If issues arise, the changes are confined to:
- 1 model file (namespace.py)
- 1 repository file (repository.py)
- 1 existing test file rename (test_namespace_composes_class.py)
- 1 fixture file (design_graph.json) — git can revert
- 6 new test files — can be deleted
- 2 test assertion updates — easily reverted

A single `git revert` of the commit restores the previous state.