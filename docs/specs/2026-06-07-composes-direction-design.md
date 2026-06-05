# COMPOSES Edge Direction Design

## Problem

When child nodes (MethodNode, AttributeNode, EnumValueNode, FunctionNode, and
compound types under namespaces) lack an incoming `RelationshipFrom('COMPOSES')`
descriptor, `serialize_edges()` on those nodes cannot discover their parent.
This means `_build_layer_graph` and `from_neo4j` cannot find the parent when a
child is a seed node — the child appears as a root entry with no nesting.

The incoming `RelationshipFrom('COMPOSES')` descriptors were previously removed
because `serialize_edges()` is direction-blind: it emits every edge as
`{relation_type, target_uid, target_type}` with no distinction between outgoing
and incoming. When `_build_layer_graph` encounters a COMPOSES edge from a child
pointing back to its parent, it incorrectly nests the parent under the child.

## Solution

Re-add `RelationshipFrom('COMPOSES')` on all child types, and replace the
`serialize_edges()` calls in `_build_layer_graph` and `from_neo4j` with a
direct walk of `RelationshipTo`/`RelationshipFrom` descriptors. Direction is
determined by the descriptor type at walk time — no direction field is added
to any edge dict.

## Changes

### 1. Re-add `RelationshipFrom('COMPOSES')` on child types

Each mirrors an existing outgoing `RelationshipTo('COMPOSES')` on the parent:

| Model | New descriptor | Mirrors |
|---|---|---|
| `MethodNode` | `parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')` | `ClassNode.methods` |
| `MethodNode` | `parent_interface = RelationshipFrom(InterfaceNode, 'COMPOSES')` | `InterfaceNode.methods` |
| `AttributeNode` | `parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')` | `ClassNode.attributes` |
| `EnumValueNode` | `parent_enum = RelationshipFrom(EnumNode, 'COMPOSES')` | `EnumNode.values` |
| `FunctionNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.functions` |
| `ClassNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.classes` |
| `InterfaceNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.interfaces` |
| `EnumNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.enums` |
| `UnionNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.unions` |
| `ModuleNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.modules` |
| `NamespaceNode` | `parent_namespace = RelationshipFrom(NamespaceNode, 'COMPOSES')` | `NamespaceNode.namespaces` |

Neomodel creates a single Neo4j relationship for each `(source, target,
relation_type)` triple regardless of how many Python descriptors reference it.
Adding `RelationshipFrom` does not create new edges in the database — it gives
Python code a traversal path from the child side.

### 2. Add `walk_edges()` method on `CodeGraphNode`

A new instance method that walks `RelationshipTo` and `RelationshipFrom`
descriptors directly, classifying each edge by whether the descriptor is
outgoing or incoming. Placed next to `serialize_edges()` on `CodeGraphNode`.

```python
def walk_edges(self) -> list[dict]:
    """Walk relationship descriptors on this node, classifying each edge.

    Unlike serialize_edges(), this method distinguishes outgoing
    (RelationshipTo) from incoming (RelationshipFrom) edges so that
    callers can handle COMPOSES nesting direction correctly.

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

Direction is derived from `isinstance(val, RelationshipTo)` — the model
declaration is the single source of truth.

### 3. Update `_build_layer_graph` (repository.py)

Replace both `serialize_edges()` calls (neighbor expansion and edge walking)
with `walk_edges()`. The nesting logic now checks `is_outgoing` for COMPOSES
edges:

- **Outgoing COMPOSES** (`is_outgoing=True`): source is parent, target is
  child — nest target under source. (Current behavior, unchanged.)
- **Incoming COMPOSES** (`is_outgoing=False`): source is child, target is
  parent — nest source under target.

The Phase 2 (neighbor expansion) and Phase 4 (nesting/references)
remain separate loops, just as in the current code. Both switch from
`serialize_edges()` to `walk_edges()`.

**Phase 2 — neighbor expansion** (direction is irrelevant here;
any connected node is a 1-hop neighbor):

```python
for node in list(seeds):
    for edge_info in node.walk_edges():
        target_uid = edge_info["target_uid"]
        target_type = edge_info["target_type"]
        if target_uid not in uid_to_key:
            target_cls = CodeGraphNode._registry.get(target_type)
            if target_cls:
                uid_prop = target_cls._uid_prop()
                if uid_prop:
                    neighbor = target_cls.nodes.get_or_none(
                        **{uid_prop: target_uid}
                    )
                    if neighbor:
                        neighbor_key = LayerGraph._node_key(neighbor)
                        nodes[neighbor_key] = neighbor
                        uid_to_key[target_uid] = neighbor_key
```

**Phase 4 — nesting and references** (direction determines who is
parent and who is child for COMPOSES):

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

If both the parent's outgoing edge and the child's incoming edge are processed,
the dict-key semantics (`children[target_type][target_key]`) and set semantics
(`child_keys`) handle deduplication automatically.

### 4. Update `from_neo4j` (graph.py)

Same change as `_build_layer_graph`. Replace `serialize_edges()` calls with
`walk_edges()`, apply the same direction-aware nesting logic.

### 5. `serialize_edges()` and `to_json` — unchanged

`serialize_edges()` remains the public API for JSON serialization (`serialize()`
calls it, and `to_json` strips all COMPOSES edges into nesting anyway). No
direction field is added to its output. The only callers that change are
`_build_layer_graph` and `from_neo4j`, which switch to `walk_edges()`.

### 6. `from_json` — unchanged

The nested format (`composes` key) and flat format (`edges` array with
`target_local_id`/`target_uid`) are both unchanged. COMPOSES edges in the flat
format are always expressed from the parent's side in external data (e.g.
`design_graph.json`), and `to_json` represents COMPOSES as nesting rather than
edges. No format changes needed.

## Test Impact

### New tests

Roundtrip tests for each new `RelationshipFrom` descriptor, mirroring the
existing `test_namespace_composes_*.py` pattern from the child's side:

- `test_method_composed_by_class` — `method.parent_compound.all()` returns the
  ClassNode
- `test_method_composed_by_interface` — `method.parent_interface.all()` returns
  the InterfaceNode
- `test_attribute_composed_by_class`
- `test_enum_value_composed_by_enum`
- `test_function_composed_by_namespace`
- `test_class_composed_by_namespace`
- `test_interface_composed_by_namespace`
- `test_enum_composed_by_namespace`
- `test_union_composed_by_namespace`
- `test_module_composed_by_namespace`
- `test_namespace_composed_by_namespace`

### Graph-building tests

When a child node is included in a seed set (e.g.
`get_by_neighbourhood("calc::CalculatorEngine::add")`), the incoming COMPOSES
edge should now discover the parent ClassNode and nest the method correctly.
Existing tests in `test_layer_graph.py` and `test_graph_repository.py` may need
assertion updates for this new behavior.

### Serialization tests — no changes needed

`serialize()` and `to_json()` use `serialize_edges()` (not `walk_edges()`).
These output paths are unchanged. Any test that asserts on the exact `edges`
array from a child node's `serialize()` will now include incoming COMPOSES
edges — those assertions need updating, but `to_json` strips all COMPOSES
anyway so most tests are unaffected.

## What this does NOT change

- `serialize_edges()` output format — no direction field added
- `to_json()` / `from_json()` — COMPOSES still represented by nesting
- `design_graph.json` fixture — COMPOSES edges still from parent's side
- `find_relationship_manager()` — still used by `to_neo4j()`, unaffected
- `compound_refid` on `_MemberMixin` — remains as a plain-data field; not used
  for graph traversal (the `RelationshipFrom` descriptors handle that)