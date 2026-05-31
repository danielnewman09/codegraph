# Atomize Models Design — Single Neomodel Layer

**Date:** 2026-05-31  
**Status:** Draft  
**Scope:** Replace two-layer Pydantic+neomodel architecture with a single canonical neomodel layer

## Overview

Remove the Pydantic design layer (`designs/`) entirely. neomodel `StructuredNode`
subclasses become the sole source of truth for all node types. Each domain concept
gets its own neomodel class with its own Neo4j label, its own fields, and a
`serialize()`/`deserialize()` contract via an ABC for LLM-facing serialization.

`ClassDiagram` becomes a plain dataclass container that reads from Neo4j via
neomodel directly — no persistence responsibilities, no Pydantic.

**Architecture after:**

```
                    ┌──────────────────────────┐
                    │   neomodel models          │
                    │   ClassNode, InterfaceNode, │
                    │   EnumNode, MethodNode, ... │
                    │   (StructuredNode +         │
                    │    LlmSerializable ABC)     │
                    └─────────────┬────────────┘
                                  │ uses
                    ┌─────────────▼────────────┐
                    │   ClassDiagram (dataclass)│
                    │   Snapshot container —     │
                    │   from_layer(), to_summary()│
                    │   to_verification_dicts()  │
                    └─────────────┬────────────┘
                                  │ reads
                    ┌─────────────▼────────────┐
                    │         Neo4j              │
                    └──────────────────────────┘
```

## 1. Model Hierarchy

### 1.1 Compounds

Each compound kind gets its own neomodel class and Neo4j label. No umbrella
`:Compound` label — queries target specific labels.

| Neomodel class | Neo4j label | Kind-specific fields |
|---|---|---|
| `ClassNode` | `:Class` | `module`, `base_classes[]`, `is_final`, `is_abstract`, `members` relationship (MethodNode/AttributeNode via COMPOSES), `base` relationship (GENERALIZES to ClassNode) |
| `InterfaceNode` | `:Interface` | `module`, `methods` relationship (MethodNode via COMPOSES; no attributes), implicitly abstract |
| `EnumNode` | `:Enum` | `module`, `values` relationship (EnumValueNode via COMPOSES) |
| `UnionNode` | `:Union` | `module` |
| `ModuleNode` | `:Module` | (none beyond common; not a direct ClassDiagram member) |

**Common fields** (on every compound, either via a shared mixin or repeated):

| Field | neomodel type | Notes |
|---|---|---|
| `qualified_name` | `UniqueIdProperty()` | Primary identity |
| `name` | `StringProperty(default="")` | Unqualified name |
| `kind` | `StringProperty()` | Literal per subclass ("class", "interface", "enum", "union", "module") |
| `layer` | `StringProperty(default="design")` | Provenance layer |
| `component_id` | `IntegerProperty()` | Ticketing FK (nullable) |
| `refid` | `StringProperty(default="")` | Doxygen refid |
| `brief_description` | `StringProperty(default="")` | One-line summary |
| `detailed_description` | `StringProperty(default="")` | Full doc comment |
| `file_path` | `StringProperty(default="")` | Source file path |
| `line_number` | `IntegerProperty()` | Declaration line |
| `source` | `StringProperty(default="")` | Provenance label (e.g. "msd", "stdlib") |
| `definition` | `StringProperty(default="")` | Full definition string |
| `source_type` | `StringProperty(default="")` | e.g. "header", "source" |

**LLM fields** — each class declares a `_llm_fields` set:

- `ClassNode`: `{"qualified_name", "name", "kind", "brief_description", "base_classes"}`
- `InterfaceNode`: `{"qualified_name", "name", "kind", "brief_description"}`
- `EnumNode`: `{"qualified_name", "name", "kind", "brief_description"}`
- `UnionNode`: `{"qualified_name", "name", "kind", "brief_description"}`
- `ModuleNode`: `{"qualified_name", "name", "kind", "brief_description"}`

ModuleNode exists in the model hierarchy but is **not** collected by
`ClassDiagram.from_layer()` — module names are derived from qualified names.

### 1.2 Members

The single `MemberNode` is atomized by kind. No `:Member` umbrella label.

| Neomodel class | Neo4j label | Key fields | Parent relationship |
|---|---|---|---|
| `MethodNode` | `:Method` | `type_signature`, `argsstring`, `protection`, `is_virtual`, `is_static`, `is_const`, `is_inline` | COMPOSES from ClassNode/InterfaceNode |
| `AttributeNode` | `:Attribute` | `type_signature`, `protection`, `is_static`, `is_const` | COMPOSES from ClassNode |
| `EnumValueNode` | `:EnumValue` | (name only) | COMPOSES from EnumNode |
| `FunctionNode` | `:Function` | `type_signature`, `argsstring`, `file_path` | (file-level, no compound parent) |
| `DefineNode` | `:Define` | `definition`, `file_path` | (file-level, no compound parent) |

Common member fields: `qualified_name` (unique), `name`, `kind` (literal per subclass),
`layer`, `component_id`, `refid`, `compound_refid`, `brief_description`,
`detailed_description`, `file_path`, `line_number`, `source`.

### 1.3 Staying (unchanged or type-only updates)

| Neomodel class | Neo4j label | Notes |
|---|---|---|
| `NamespaceNode` | `:Namespace` | Already 1:1, no atomization needed |
| `FileNode` | `:File` | Already 1:1, no atomization needed |
| `ParameterNode` | `:Parameter` | Already 1:1, no atomization needed |

## 2. LlmSerializable ABC

Lives at `src/codegraph/models/tags.py`. Every model node that should be
presentable to LLMs implements this.

```python
from abc import ABC, abstractmethod

class LlmSerializable(ABC):
    @abstractmethod
    def serialize(self) -> dict:
        """Return a dict of only LLM-visible fields."""
        ...

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict) -> "LlmSerializable":
        """Instantiate a node from LLM-provided dict data."""
        ...
```

Implementation pattern on a concrete node:

```python
class ClassNode(StructuredNode, LlmSerializable):
    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "base_classes"}

    def serialize(self) -> dict:
        props = dict(self.__properties__)
        return {k: props[k] for k in self._llm_fields if k in props}

    @classmethod
    def deserialize(cls, data: dict) -> "ClassNode":
        return cls(**{k: v for k, v in data.items()
                      if k in cls.defined_properties()})
```

`serialize()` filters `__properties__` to `_llm_fields`. `deserialize()` hydrates
only fields that match the model's `defined_properties()` — ignoring extraneous
keys the LLM might include.

## 3. ClassDiagram

Lives at `src/codegraph/diagram.py`. A plain dataclass container — no Pydantic,
no persistence responsibilities, no associations list (relationships are
traversable directly from neomodel nodes).

ModuleNode is **not** a direct member of ClassDiagram. Module names are derived
from compound qualified names (e.g. ``"calc::Calculator"`` → module ``"calc"``).
The ``module_names`` list is populated automatically during ``from_layer()``.

```python
from dataclasses import dataclass, field

@dataclass
class ClassDiagram:
    module_names: list[str] = field(default_factory=list)
    classes: list[ClassNode] = field(default_factory=list)
    interfaces: list[InterfaceNode] = field(default_factory=list)
    enums: list[EnumNode] = field(default_factory=list)

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode] = \
        field(default_factory=dict, init=False)
```

**Post-init:** `__post_init__` builds `_entity_index` for O(1) `get_entity()` lookups.

**Methods that stay:**

| Method | Behavior |
|---|---|
| `from_layer(layer: str) -> ClassDiagram` | Queries :Class, :Interface, :Enum where `layer=...`, traverses relationships to fetch members, derives module names from qualified names, returns populated diagram |
| `get_entity(qn: str)` | O(1) lookup across classes, interfaces, enums |
| `classes_in_module(module: str)` | Filters `self.classes` by `.module` |
| `to_summary() -> dict` | Returns `{"classes": N, "interfaces": N, "enums": N, "attributes": N, "methods": N}` |
| `to_verification_dicts() -> list[dict]` | Iterates nodes, traverses `.base.all()`, `.methods.all()` to build flat verification dicts |
| `to_draft_lookup() -> dict` | `qualified_name` → entity info with `source: "draft"` |
| `to_class_lookup() -> dict` | `name` → `qualified_name` map |

**Methods that go away:**
- `to_neo4j()` — individual nodes handle persistence (`.save()`, `.connect()`)
- `from_neo4j(compounds, members, edges)` — replaced by `from_layer()`
- `associations_for(qn)` / `associations_involving(qn)` — consumers traverse relationships directly (`node.base.all()`, `node.derived.all()`)
- `model_dump(tags=...)` — replaced by `serialize()` on individual nodes

## 4. What Gets Deleted

| Path | Reason |
|---|---|
| `src/codegraph/designs/` | Entire submodule — Pydantic design models no longer needed |
| `src/codegraph/repositories/` | No more bridge layer — callers use neomodel directly |
| `tests/test_designs_compound.py` | Pydantic design tests |
| `tests/test_designs_edges.py` | Pydantic design tests |
| `tests/test_designs_member.py` | Pydantic design tests |
| `tests/test_designs_namespace.py` | Pydantic design tests |
| `tests/test_repositories.py` | Repository tests |
| `tests/test_codegraph_edge_description.py` | `CodebaseEdge` deleted |
| `tests/test_edges.py` | `CodebaseEdge` deleted (keep `test_constants.py` for predicates) |

## 5. What Gets Created or Modified

| Path | Change |
|---|---|
| `src/codegraph/models/tags.py` | **New** — `LlmSerializable` ABC |
| `src/codegraph/models/compound.py` | **Rewrite** — split `CompoundNode` into `ClassNode`, `InterfaceNode`, `EnumNode`, `UnionNode`, `ModuleNode` |
| `src/codegraph/models/member.py` | **Rewrite** — split `MemberNode` into `MethodNode`, `AttributeNode`, `EnumValueNode`, `FunctionNode`, `DefineNode` |
| `src/codegraph/models/__init__.py` | **Update** — new exports |
| `src/codegraph/diagram.py` | **New** — dataclass `ClassDiagram` |
| `src/codegraph/__init__.py` | **Update** — remove Pydantic exports, remove `CodebaseEdge`, update for new model exports |
| `src/codegraph/edges.py` | **Trim** — delete `CodebaseEdge` class, keep predicate constants (or move to `constants.py`) |
| `src/codegraph/constants.py` | **Update** — add PREDICATES if moved from `edges.py` |
| `src/codegraph/graph/__init__.py` | **Update** — type annotations for atomized models |
| `tests/test_models.py` | **Rewrite** — tests for each new atomized class |
| `tests/test_class_diagram_neo4j.py` | **Rewrite** — for new `ClassDiagram` dataclass |
| `tests/test_public_api.py` | **Update** — remove deleted exports |
| `tests/test_edges.py` | **Delete** |
| `tests/test_field_tags.py` | **Rewrite or delete** — replace with `serialize()` tests |

## 6. edges.py and graph/

### 6.1 edges.py

`CodebaseEdge` (Pydantic model) is deleted. The predicate vocabulary (`PREDICATES`,
`PREDICATE_TO_REL_TYPE`, `DEFAULT_PREDICATES`) moves into `constants.py` — it
remains useful as a shared vocabulary for Neo4j relationship types.

Consumers that need to represent edges in-memory can use neomodel relationship
traversal (`node.base.all()`) or define their own lightweight dataclasses as needed.

### 6.2 graph/ Module

Type annotations updated for atomized models:

- `CompoundGraph.node`: `CompoundNode` → `ClassNode | InterfaceNode | EnumNode | UnionNode`
- `CompoundGraph.members`: `list[MemberNode]` → `list[MethodNode | AttributeNode | EnumValueNode]`
- `NamespaceGraph.compounds`: `list[CompoundGraph]` → stays, just wraps union type

The `to_raw()` path relies on `__properties__` which every `StructuredNode` has —
no logic changes required.

## 7. Migration Plan

### Phase 1 — New Models
1. Create `models/tags.py` — `LlmSerializable` ABC with `serialize()`/`deserialize()`
2. Rewrite `models/compound.py` — atomize into 5 classes, each with its own label, fields, relationships, and `_llm_fields`
3. Rewrite `models/member.py` — atomize into 5 classes
4. Update `models/__init__.py` exports

### Phase 2 — ClassDiagram
5. Create `diagram.py` — dataclass `ClassDiagram` with `from_layer()`, `get_entity()`, `to_summary()`, `to_verification_dicts()`, `to_draft_lookup()`, `to_class_lookup()`
6. Delete `designs/` submodule entirely
7. Delete `repositories/` submodule

### Phase 3 — Cleanup
8. Trim `edges.py` — delete `CodebaseEdge`, move predicate constants to `constants.py`
9. Update `graph/` type annotations
10. Update `src/codegraph/__init__.py` public API exports

### Phase 4 — Tests
11. Rewrite `test_models.py` — per-class create/save/retrieve/serialize tests
12. Delete `test_designs_*.py`, `test_repositories.py`, `test_edges.py`, `test_codegraph_edge_description.py`
13. Rewrite `test_class_diagram_neo4j.py` for new dataclass `ClassDiagram`
14. Update `test_public_api.py` — verify new exports, remove deleted ones
15. Rewrite `test_field_tags.py` — test `serialize()`/`deserialize()` on each model

## 8. Consumer Impact

### Ticketing System
Uses `ClassDiagram.to_neo4j()` and Pydantic `CompoundNode`/`MemberNode` imports.
Must be updated to:
- Use neomodel nodes directly (`.save()`, `.connect()`)
- Call `ClassDiagram.from_layer()` instead of `from_neo4j(compounds, members, edges)`
- Call `node.serialize()` instead of `model_dump(tags={"llm"})`

### Doxygen Parser
Currently uses `model_dump()` + raw Cypher. Can be updated to use neomodel
`.save()` directly. The codegraph release should coordinate with both consumers.

## 9. Benefits

- **Single mental model** — no mapping between two parallel type systems
- **Kind safety** — `ClassNode`, `EnumNode` etc. carry only their relevant fields, not the union of all possible compound fields
- **Cleaner Neo4j schema** — specific labels (`:Class`, `:Enum`, `:Method`) instead of umbrella labels (`:Compound`, `:Member`)
- **Relationship traversal** — neomodel relationships are type-aware: `node.methods.all()` returns `MethodNode` instances, `node.values.all()` returns `EnumValueNode` instances
- **Simpler serialization** — `serialize()` on each node vs. centralized `model_dump(tags={...})` with field filtering infrastructure
- **Fewer lines** — ~800 lines deleted (`designs/`, `repositories/`, old test files), replaced with focused neomodel classes

## 10. Risks

- **Neo4j schema migration** — existing `:Compound` and `:Member` labeled nodes in databases need to be re-labeled or re-created. A migration script may be needed for production data.
- **Consumer breakage** — ticketing system and doxygen parser both depend on the Pydantic layer. Coordination required.
- **Relationship cardinality** — neomodel `RelationshipTo` with different target types requires separate descriptor declarations (`methods`, `attributes`) which is slightly more verbose than a single `members` relationship.
