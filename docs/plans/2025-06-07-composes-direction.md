# Implementation Plan: COMPOSES Edge Direction

Spec: `docs/specs/2026-06-07-composes-direction-design.md`

## Step 1: Add `RelationshipFrom('COMPOSES')` descriptors on all child types

Add incoming COMPOSES descriptors that mirror existing outgoing ones. Each new descriptor goes immediately after the "Composition" or "Relationships" section comment in its respective model class, with a brief doc comment.

**Files to modify:**

### `src/codegraph/models/member.py`

Add `RelationshipFrom` to the import (line 4–7):

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipTo, RelationshipFrom,
)
```

**MethodNode** — add after doc comment section, before `invokes`:

```python
    # Incoming composition (parent compound/interface)
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')
    parent_interface = RelationshipFrom('codegraph.models.compound.InterfaceNode', 'COMPOSES')
```

Update the existing note (currently: "COMPOSES is declared only on parent compound nodes…") to:

```
    #  ── Composition (incoming) ──
    #  • COMPOSES (incoming) — ClassNode | InterfaceNode → this MethodNode
    #    The parent compound or interface owns this method.
    #    Traversed via ``parent_compound`` / ``parent_interface``.
```

**AttributeNode** — add incoming COMPOSES:

```python
    # ── Composition (incoming) ──
    # • COMPOSES (incoming) — ClassNode → this AttributeNode
    #   The parent class owns this attribute.
    #   Traversed via ``parent_compound``.
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')
```

**EnumValueNode** — add incoming COMPOSES:

```python
    # ── Composition (incoming) ──
    # • COMPOSES (incoming) — EnumNode → this EnumValueNode
    #   The parent enum owns this value.
    #   Traversed via ``parent_enum``.
    parent_enum = RelationshipFrom('codegraph.models.compound.EnumNode', 'COMPOSES')
```

**FunctionNode** — add incoming COMPOSES:

```python
    # ── Composition (incoming) ──
    # • COMPOSES (incoming) — NamespaceNode → this FunctionNode
    #   The parent namespace owns this function.
    #   Traversed via ``parent_namespace``.
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

**DefineNode** — No COMPOSES RelationshipFrom. Not composed by any parent type.

### `src/codegraph/models/compound.py`

All five compound types under namespaces get a `parent_namespace` descriptor.

**ClassNode** — add after `realizes`:

```python
    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

**InterfaceNode** — add after `dependencies`:

```python
    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

**EnumNode** — add after `values`:

```python
    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

**UnionNode** — add at end of class body:

```python
    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

**ModuleNode** — add at end of class body:

```python
    # Incoming composition (parent namespace)
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
```

### `src/codegraph/models/namespace.py`

Add `RelationshipFrom` to the import:

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom,
)
```

**NamespaceNode** — add after `namespaces` line:

```python
    # Incoming composition (parent namespace for nesting)
    parent_namespace = RelationshipFrom('NamespaceNode', 'COMPOSES')
```

Update the doc comment to mention the incoming relationship.

---

## Step 2: Add `walk_edges()` method on `CodeGraphNode` in `tags.py`

Add the method after `serialize_edges()` in `src/codegraph/models/tags.py`.

```python
    def walk_edges(self) -> list[dict]:
        """Walk relationship descriptors, classifying each edge by direction.

        Unlike serialize_edges(), this method distinguishes outgoing
        (RelationshipTo) from incoming (RelationshipFrom) edges so that
        callers can handle COMPOSES nesting direction correctly.

        Direction is derived from the descriptor type — no extra field
        is added to serialize_edges() output.

        Requires the node to be saved in Neo4j (the relationship managers
        query the database).

        Returns:
            A list of dicts, each with keys:
            - relation_type: Neo4j relationship label
            - target_uid: connected node's unique id value
            - target_type: connected node's class name
            - is_outgoing: True for RelationshipTo, False for RelationshipFrom
        """
        from neomodel import RelationshipTo, RelationshipFrom

        edges: list[dict] = []
        seen: set[str] = set()

        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)

                is_outgoing = isinstance(val, RelationshipTo)
                manager = getattr(self, name)

                for target in manager.all():
                    edges.append({
                        "relation_type": val.definition["relation_type"],
                        "target_uid": target._uid_value(),
                        "target_type": type(target).__name__,
                        "is_outgoing": is_outgoing,
                    })

        return edges
```

Key points:
- Same descriptor-walking pattern as `serialize_edges()`
- Adds `is_outgoing` boolean derived from `isinstance(val, RelationshipTo)`
- No changes to `serialize_edges()` itself — it stays unchanged for JSON serialization paths

---

## Step 3: Update `_build_layer_graph` in `repository.py`

Replace both `serialize_edges()` calls with `walk_edges()` and add direction-aware COMPOSES handling.

**Phase 2 — neighbor expansion** (~line 91):

Change `node.serialize_edges()` to `node.walk_edges()`. The loop body only uses `target_uid` and `target_type`, so it's direction-agnostic. The change is just the method call swap.

**Phase 4 — nesting and references** (~lines 118–135):

Replace the entire loop body:

```python
        for node in nodes.values():
            source_key = LayerGraph._node_key(node)
            source_entry = key_to_entry[source_key]

            for edge_info in node.walk_edges():
                relation_type = edge_info["relation_type"]
                target_uid = edge_info["target_uid"]
                target_type = edge_info["target_type"]
                is_outgoing = edge_info["is_outgoing"]
                target_key = uid_to_key.get(target_uid)

                if target_key is None or target_key not in key_to_entry:
                    continue

                if relation_type == "COMPOSES":
                    if is_outgoing:
                        # Parent → child: nest target under source
                        target_entry = key_to_entry[target_key]
                        source_entry.children.setdefault(target_type, {})[target_key] = target_entry
                        child_keys.add(target_key)
                    else:
                        # Child → parent: nest source under target
                        source_type = type(node).__name__
                        target_entry = key_to_entry[target_key]
                        target_entry.children.setdefault(source_type, {})[source_key] = source_entry
                        child_keys.add(source_key)
                else:
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )
```

---

## Step 4: Update `from_neo4j` in `graph.py`

Same pattern as Step 3.

**Neighbor expansion** (~line 510): Change `node.serialize_edges()` to `node.walk_edges()`.

**Edge walking** (~lines 539–554): Replace with direction-aware logic matching Step 3:

```python
        for node in list(nodes.values()):
            source_key = cls._node_key(node)
            source_entry = key_to_entry[source_key]

            for edge in node.walk_edges():
                relation_type = edge["relation_type"]
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                is_outgoing = edge["is_outgoing"]
                target_key = uid_to_key.get(target_uid)

                if target_key is None:
                    continue

                if relation_type == "COMPOSES":
                    target_entry = key_to_entry.get(target_key)
                    if target_entry is not None:
                        if is_outgoing:
                            source_entry.children.setdefault(target_type, {})[target_key] = target_entry
                            child_keys.add(target_key)
                        else:
                            source_type = type(node).__name__
                            target_entry.children.setdefault(source_type, {})[source_key] = source_entry
                            child_keys.add(source_key)
                else:
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )
```

---

## Step 5: Add roundtrip tests for each new `RelationshipFrom` descriptor

Create test files following the existing pattern (`tests/compound/test_class_composes_method.py` as template). Each test:
1. Creates + saves parent and child nodes
2. Connects via the parent's outgoing RelationshipTo
3. Asserts the child's incoming RelationshipFrom `.all()` returns the parent

**New files:**

| File | Descriptor tested |
|---|---|
| `tests/member/test_method_composed_by_parent.py` | `MethodNode.parent_compound` + `MethodNode.parent_interface` |
| `tests/member/test_attribute_composed_by_class.py` | `AttributeNode.parent_compound` |
| `tests/member/test_enum_value_composed_by_enum.py` | `EnumValueNode.parent_enum` |
| `tests/member/test_function_composed_by_namespace.py` | `FunctionNode.parent_namespace` |
| `tests/compound/test_class_composed_by_namespace.py` | `ClassNode.parent_namespace` |
| `tests/compound/test_interface_composed_by_namespace.py` | `InterfaceNode.parent_namespace` |
| `tests/compound/test_enum_composed_by_namespace.py` | `EnumNode.parent_namespace` |
| `tests/compound/test_union_composed_by_namespace.py` | `UnionNode.parent_namespace` |
| `tests/compound/test_module_composed_by_namespace.py` | `ModuleNode.parent_namespace` |
| `tests/namespace/test_namespace_composed_by_namespace.py` | `NamespaceNode.parent_namespace` |

The MethodNode test covers two descriptors (`parent_compound` from ClassNode and `parent_interface` from InterfaceNode) — one test function for each.

---

## Step 6: Add graph-building tests for nesting direction (child-seeded queries)

Add tests to `tests/repository/test_graph_repository.py` and `tests/test_layer_graph.py`.

### Repository tests — `test_graph_repository.py`

**`test_method_seed_discovers_parent_class`** in `TestGetByNeighbourhood`:

```python
def test_method_seed_discovers_parent_class(self, repo, seeded_graph):
    """When a MethodNode is the seed, its parent ClassNode should be
    discovered via incoming COMPOSES and the method should be nested
    under the class."""
    result = repo.get_by_neighbourhood("calc::CalculatorEngine::add")
    # The method should NOT be a root entry
    assert "calc::CalculatorEngine::add" not in result.entries
    # The parent class should be in the graph
    engine_entry = _find_entry(result, "calc::CalculatorEngine")
    assert engine_entry is not None
    # The method should be nested under the class
    assert "MethodNode" in engine_entry.children
    assert "calc::CalculatorEngine::add" in engine_entry.children["MethodNode"]
```

**`test_class_seed_discovers_parent_namespace`** in `TestGetByNeighbourhood`:

```python
def test_class_seed_discovers_parent_namespace(self, repo, seeded_graph):
    """When a ClassNode is the seed, the parent NamespaceNode should be
    discovered via incoming COMPOSES."""
    result = repo.get_by_neighbourhood("calc::CalculatorEngine")
    calc_entry = _find_entry(result, "calc")
    assert calc_entry is not None
    assert "ClassNode" in calc_entry.children
    assert "calc::CalculatorEngine" in calc_entry.children["ClassNode"]
```

**`test_no_duplicate_children`** in `TestBuildLayerGraphEntries`:

```python
def test_no_duplicate_children_when_both_directions_processed(self, repo, seeded_graph):
    """When both outgoing and incoming COMPOSES are processed, children
    should appear exactly once in the parent's children dict."""
    result = repo.get_by_namespace("calc")
    engine_entry = _find_entry(result, "calc::CalculatorEngine")
    assert engine_entry is not None
    method_keys = list(engine_entry.children.get("MethodNode", {}).keys())
    assert len(method_keys) == len(set(method_keys))
```

### Layer graph tests — `test_layer_graph.py`

**`test_incoming_composes_nests_child`** in `TestFromNeo4j`:

```python
def test_incoming_composes_nests_child_under_parent(self):
    """from_neo4j should nest children under parents even when discovered
    via incoming COMPOSES from the child side."""
    with open(FIXTURE) as f:
        data = json.load(f)
    LayerGraph.from_json(data).to_neo4j()

    result = LayerGraph.from_neo4j("design")
    engine = _find_entry(result, "calc::CalculatorEngine")
    assert engine is not None
    assert "MethodNode" in engine.children
```

---

## Step 7: Verify existing tests pass without modification

After adding `RelationshipFrom('COMPOSES')` descriptors, `serialize_edges()` on child nodes will now include incoming COMPOSES edges. Review all existing tests that call `serialize()` on nodes with COMPOSES connections:

- `tests/compound/test_class_composes_method.py` — serializes **parent** (ClassNode). No change needed.
- `tests/compound/test_class_composes_attribute.py` — serializes **parent** (ClassNode). No change needed.
- `tests/compound/test_interface_composes_method.py` — serializes **parent** (InterfaceNode). No change needed.
- `tests/compound/test_enum_composes_value.py` — serializes **parent** (EnumNode). No change needed.
- `tests/namespace/test_namespace_composes_*.py` — all serialize **parent** (NamespaceNode). No change needed.
- `tests/member/test_method_*.py` — MethodNode tests don't create COMPOSES connections to parents. No change needed.
- `tests/test_layer_graph.py` → `test_edge_persistence` — uses `>=` for edge count assertions. Adding incoming edges only increases the count. No change needed.

**No existing test files need modification.** The new incoming COMPOSES edges are additive and don't conflict with existing assertions.

---

## Verification Checklist

After all steps:

1. Run all existing tests: `pytest tests/ -v`
2. Verify that `serialize_edges()` output is unchanged (no `is_outgoing` field)
3. Verify that `walk_edges()` returns `is_outgoing` for every edge
4. Verify that `_build_layer_graph` correctly nests children under parents regardless of which side the COMPOSES edge comes from
5. Verify that `from_neo4j` correctly nests children under parents
6. Verify that `to_json` / `from_json` are unaffected (COMPOSES still represented by nesting, stripped from edges)
7. Verify that `find_relationship_manager` still works for COMPOSES connections in `to_neo4j()` — it should find the outgoing `RelationshipTo` descriptor on the parent node