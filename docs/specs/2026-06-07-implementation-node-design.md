# Implementation Node — Separate Search & Embedding Storage Design

> **Date:** 2026-06-07  
> **Status:** Draft  
> **Depends on:** Phase 1 storage layer (already implemented, partially reverted here)

---

## Problem

Phase 1 added `implementation`, `doc_embedding`, and `impl_embedding` fields inline on `_MemberMixin` and `_CompoundMixin`. This makes every MethodNode, FunctionNode, and CompoundNode carry potentially large source text (~KB) and embedding vectors (~12KB each) whether or not the consumer needs them.

A lightweight query — listing methods, counting nodes, serializing a graph for LLM context — pulls all of that data from Neo4j on every property access, even though only a fraction of use cases need the implementation body or embeddings.

## Solution

Move `implementation` and `impl_embedding` to a separate `ImplementationNode` connected via `HAS_IMPLEMENTATION`. Keep `doc_embedding` inline on the parent nodes (it's small and derived from parent-scope fields).

```
MethodNode ─[:HAS_IMPLEMENTATION]→ ImplementationNode
FunctionNode ─[:HAS_IMPLEMENTATION]→ ImplementationNode
DefineNode ─[:HAS_IMPLEMENTATION]→ ImplementationNode
ClassNode ─[:HAS_IMPLEMENTATION]→ ImplementationNode
InterfaceNode ─[:HAS_IMPLEMENTATION]→ ImplementationNode
...
```

`LayerGraph` expansion **skips** `HAS_IMPLEMENTATION` by design. Implementation data is **opt-in** — fetched via `node.implementation_ref.all()` when source code is needed.

---

## Node Model

### New file: `src/codegraph/models/implementation.py`

```python
class ImplementationNode(StructuredNode, CodeGraphNode):
    """Source code implementation body and its embedding — Neo4j label ``:Implementation``.

    Connected from MethodNode, FunctionNode, DefineNode, or any CompoundNode
    via a HAS_IMPLEMENTATION relationship.  The implementation text and its
    vector embedding are kept on a separate node so that:

    - Lightweight queries (listing, counting, ``serialize()``) do not pull
      potentially large source text or embedding vectors.
    - LayerGraph construction skips implementation nodes by design.

    To retrieve implementation data, traverse the relationship explicitly:

        impl_nodes = method.implementation_ref.all()
        if impl_nodes:
            source_code = impl_nodes[0].implementation
            embedding = impl_nodes[0].impl_embedding

    Attributes:
        qualified_name: Matches the parent node's qualified_name.
            Used to correlate back to the owning method/function/compound.
        kind: Always "implementation".
        implementation: Full source code body of the method/function.
        impl_embedding: Vector embedding of the implementation source code.
    """

    # --- Identity ---
    qualified_name = StringProperty(default="")
    kind = StringProperty(default="implementation")

    # --- Source code ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Embeddings ---
    impl_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of the implementation source code.")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "kind", "implementation"}
```

Key decisions:

- **`qualified_name`** uses `StringProperty` (not `UniqueIdProperty`) — it's derived from the parent's `qualified_name`, not auto-generated.
- **`_llm_fields`** includes `implementation` (useful in LLM context) but excludes `impl_embedding` (vector floats aren't useful as text).
- Auto-registers in `CodeGraphNode._registry` as `"ImplementationNode"`.

---

## Relationships

### On `_MemberMixin` (`src/codegraph/models/member.py`)

```python
    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this member → ImplementationNode
    #    The full source code body and its vector embedding.  Kept on a
    #    separate node so that lightweight queries (listing, counting,
    #    serializing) do not pull potentially large implementation text or
    #    embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``method.implementation_ref.all()`` when source code is needed.
    # --------------------------------------------------------------------------

    implementation_ref = RelationshipTo('codegraph.models.implementation.ImplementationNode', 'HAS_IMPLEMENTATION')
```

### On `_CompoundMixin` (`src/codegraph/models/compound.py`)

Same relationship descriptor with the same glossary comment.

No `RelationshipFrom` on `ImplementationNode` — the access pattern is parent → implementation, never the reverse.

---

## Field Changes on Existing Mixins

### `_MemberMixin` — remove, add, keep

| Action | Field | Reason |
|---|---|---|
| **Remove** | `implementation` | Moves to `ImplementationNode` |
| **Remove** | `impl_embedding` | Moves to `ImplementationNode` |
| **Keep** | `doc_embedding` | Lightweight, derived from parent-scope fields |
| **Add** | `implementation_ref` | Relationship to `ImplementationNode` |

**`MethodNode._llm_fields`**: Remove `"implementation"` (added in Phase 1).

**`FunctionNode._llm_fields`**: Remove `"implementation"` (added in Phase 1).

**Base `_MemberMixin._llm_fields`**: No change — `implementation` was never in the base set.

### `_CompoundMixin` — remove, add, keep

| Action | Field | Reason |
|---|---|---|
| **Remove** | `implementation` | Moves to `ImplementationNode` |
| **Keep** | `doc_embedding` | Lightweight, derived from parent-scope fields |
| **Add** | `implementation_ref` | Relationship to `ImplementationNode` |

No compound `_llm_fields` sets include `implementation` or `doc_embedding`, so no changes needed there.

---

## LayerGraph Expansion Filter

`LayerGraph._build_layer_graph()` and `LayerGraph.from_neo4j()` both do 1-hop neighbor expansion. `HAS_IMPLEMENTATION` must be excluded so implementation nodes stay out of the graph by default.

### In `src/codegraph/graph/__init__.py`

Both `_build_layer_graph()` (used by `GraphRepository`) and `from_neo4j()` need the same filter. The common pattern is:

```python
for edge_info in node.walk_edges():
    # Skip lazy-loaded relationships — fetched on demand, not in graph expansion
    if edge_info["relation_type"] == "HAS_IMPLEMENTATION":
        continue
    ...
```

This appears in two places:
1. `_build_layer_graph()` — Phase 2 neighbor expansion loop
2. `from_neo4j()` — Phase 2 neighbor expansion loop

---

## Index & DDL Changes

### `src/codegraph/constants.py` — `CONSTRAINTS_AND_INDEXES`

**Remove** from Phase 1:
- The `n.implementation` field in the `doc_search` full-text index (implementation text is no longer on `Compound|Member`)
- The `member_impl_embedding` vector index (embedding moves to `Implementation` label)

**Replace with:**

```python
    # Full-text search — documentation and signatures on compounds and members
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition]",

    # Full-text search — implementation source code on implementation nodes
    "CREATE FULLTEXT INDEX impl_search IF NOT EXISTS FOR (n:Implementation) ON EACH [n.implementation]",

    # Lookup indexes for Implementation nodes
    "CREATE INDEX impl_qualified IF NOT EXISTS FOR (i:Implementation) ON (i.qualified_name)",
    "CREATE INDEX impl_kind IF NOT EXISTS FOR (i:Implementation) ON (i.kind)",

    # Vector search — documentation embeddings on methods and functions
    "CREATE VECTOR INDEX doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",

    # Vector search — implementation embeddings on implementation nodes
    "CREATE VECTOR INDEX impl_embedding IF NOT EXISTS FOR (n:Implementation) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
```

Note: The `doc_search` index keeps `n.definition` but drops `n.implementation` (now on a different label). The `n.definition` field contains the signature (e.g. `void Widget::draw(Canvas c)`), which is still valuable for full-text search.

### `examples/doxygen_to_neo4j.py`

Same DDL changes applied to its `CONSTRAINTS_AND_INDEXES` list.

---

## Module Exports

### `src/codegraph/models/__init__.py`

Add `ImplementationNode` to imports and `__all__`:

```python
from codegraph.models.implementation import ImplementationNode

__all__ = [
    ...
    "ImplementationNode",
]
```

---

## Import Updates

### `src/codegraph/models/member.py`

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom,
)
```

(Keep `ArrayProperty` and `FloatProperty` — still needed for `doc_embedding`.)

### `src/codegraph/models/compound.py`

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)
```

(Keep `FloatProperty` — still needed for `doc_embedding`.)

---

## Test Updates

### Remove from Phase 1 tests

| File | Tests to remove/modify |
|---|---|
| `tests/member/test_member_search_fields.py` | Remove `test_method_implementation_*`, `test_method_impl_embedding_*`, `test_function_implementation_*`, `test_attribute_implementation_*`, `test_define_implementation_*`. Keep `test_method_doc_embedding_*`, `test_function_doc_embedding_*` with adjustments. Change `test_method_serialize_excludes_embeddings` to only check `doc_embedding` exclusion. |

### New test files

- **`tests/implementation/test_implementation_node.py`** — CRUD, `HAS_IMPLEMENTATION` relationship, serialization/deserialization
- **`tests/implementation/test_implementation_search_fields.py`** — `_llm_fields` checks, `impl_embedding` defaults, `implementation` field behavior

### Fixture changes

- **Remove** `implementation`, `impl_embedding` from all member/compound fixture JSON files
- **Keep** `doc_embedding` (now only on member/compound fixtures where it makes sense)
- **Add** `tests/data/implementation_node_full.json` — new fixture for ImplementationNode

### LayerGraph tests

Add test verifying that nodes with `HAS_IMPLEMENTATION` relationships do not expand to include ImplementationNodes in `_build_layer_graph()` or `from_neo4j()`.

---

## Migration Note

For existing Neo4j deployments that applied Phase 1:

```cypher
-- Drop old Phase 1 indexes (renamed in this phase)
DROP INDEX member_doc_embedding IF EXISTS;
DROP INDEX member_impl_embedding IF EXISTS;

-- The doc_search index needs recreation to remove n.implementation
DROP INDEX doc_search IF EXISTS;
-- Recreated by the updated CONSTRAINTS_AND_INDEXES on next schema install

-- New indexes (doc_embedding, impl_embedding, impl_search, impl_qualified, impl_kind)
-- are created by the updated CONSTRAINTS_AND_INDEXES on next schema install.
```

Three index name changes from Phase 1:
- `member_doc_embedding` → `doc_embedding` (still on `Method|Function`, but renamed)
- `member_impl_embedding` → `impl_embedding` (moved to `Implementation` label)
- `doc_search` stays but loses the `n.implementation` field (now on `Implementation` label)

---

## File Change Summary

| File | Action |
|---|---|
| `src/codegraph/models/implementation.py` | **Create** — ImplementationNode model |
| `src/codegraph/models/member.py` | **Modify** — remove `implementation`/`impl_embedding`, add `implementation_ref`, update docstring, update `_llm_fields` |
| `src/codegraph/models/compound.py` | **Modify** — remove `implementation`, add `implementation_ref`, update docstring |
| `src/codegraph/models/__init__.py` | **Modify** — add ImplementationNode import and export |
| `src/codegraph/graph/__init__.py` | **Modify** — add HAS_IMPLEMENTATION skip in both expansion loops |
| `src/codegraph/constants.py` | **Modify** — update DDL |
| `examples/doxygen_to_neo4j.py` | **Modify** — update DDL |
| `tests/data/implementation_node_full.json` | **Create** — new fixture |
| `tests/data/*.json` (8 files) | **Modify** — remove `implementation`/`impl_embedding` fields |
| `tests/member/test_member_search_fields.py` | **Modify** — remove implementation/impl tests, keep doc_embedding tests |
| `tests/compound/test_compound_search_fields.py` | **Modify** — remove implementation tests |
| `tests/implementation/test_implementation_node.py` | **Create** — ImplementationNode model tests |
| `tests/implementation/test_implementation_search_fields.py` | **Create** — search/embedding field tests |
| `tests/test_layer_graph.py` | **Modify** — add test for HAS_IMPLEMENTATION exclusion |