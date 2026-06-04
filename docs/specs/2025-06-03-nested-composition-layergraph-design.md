# Nested Composition LayerGraph

## Problem

`LayerGraph` currently stores nodes in a flat `dict[str, CodeGraphNode]` and
edges as a separate `list[dict]` of raw dicts. This has several issues:

- Edges are raw dicts, not model objects — inconsistent with nodes.
- The flat edge list loses the per-node ownership structure encoded by
  COMPOSES relationships.
- Reverse COMPOSES `RelationshipFrom` on member types
  (`MethodNode.parent_compound`, `AttributeNode.parent_compound`,
  `EnumValueNode.parent_enum`) create directionality ambiguity in
  `serialize_edges()`. Both outgoing and incoming COMPOSES appear as
  `relation_type: "COMPOSES"` with no direction flag, making it impossible
  to distinguish parent→child from child→parent during deserialization.

## Design

### Remove reverse COMPOSES from member nodes

COMPOSES becomes strictly one-directional: only the parent (compound) node
declares it. Members already have `compound_refid` on `_MemberMixin` for
looking up their parent, so the reverse `RelationshipFrom` is redundant.

| Node | Remove |
|---|---|
| `MethodNode` | `parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')` |
| `MethodNode` | `parent_interface = RelationshipFrom(InterfaceNode, 'COMPOSES')` |
| `AttributeNode` | `parent_compound = RelationshipFrom(ClassNode, 'COMPOSES')` |
| `EnumValueNode` | `parent_enum = RelationshipFrom(EnumNode, 'COMPOSES')` |

After this change, `serialize_edges()` on a MethodNode emits only INVOKES,
HAS_ARGUMENT, RETURNS, and DEFINED_IN — never COMPOSES. The directionality
ambiguity is eliminated.

### CompositeEntry dataclass

A new dataclass bundles each node with its composed children and
non-composition references:

```python
@dataclass
class CompositeEntry:
    node: CodeGraphNode
    children: dict[str, dict[str, "CompositeEntry"]] = field(default_factory=dict)
    #   target_type → {target_key → CompositeEntry}
    references: list[tuple[str, str, str]] = field(default_factory=list)
    #   (relation_type, target_key, target_type)
```

- `children` — composed children keyed by target type, then by target key.
  Only COMPOSES edges create entries here.
- `references` — non-composition edges stored as tuples. Target nodes live
  elsewhere in the tree under their true COMPOSES parent.

### LayerGraph redesign

Replace the flat `nodes` dict and separate `edges` list with a nested
composition structure:

```python
@dataclass
class LayerGraph:
    layer: Layer
    entries: dict[str, CompositeEntry] = field(default_factory=dict)
```

- `entries` contains **root nodes only** — nodes not composed by any other
  node (files, namespaces, orphan compounds/enums/interfaces).
- Children live inside their parent's `children` dict, recursively.
- No separate edge list anywhere.

### from_json flow

1. Parse all nodes from the JSON array, create `CodeGraphNode` instances.
2. Build a uid-to-key lookup from node unique identifiers.
3. Walk each node's edges:
   - **COMPOSES** → locate the target node, nest it as a child under the
     source entry's `children` dict.
   - **Everything else** → append `(relation_type, target_key, target_type)`
     to the source entry's `references` list.
4. Root entries = nodes that no other entry composed. Nodes appearing as
   COMPOSES targets are excluded from the root level.

### to_neo4j flow

1. Walk the entry tree depth-first, save every node instance.
2. For each entry, connect COMPOSES children by calling the parent node's
   relationship manager (e.g. `class_node.methods.connect(method_node)`).
3. For each entry's `references`, look up the target node in the graph and
   connect via `CodeGraphNode.find_relationship_manager(source, relation_type, target)`.

### to_json flow

Unchanged — call `node.serialize()` on each node. Since nodes are saved and
own their live relationships via neomodel, the flat JSON array is produced
by walking the tree and serializing each node.

### from_neo4j flow

Fetch layer-matched nodes and their neighbors as today, but organize into
`CompositeEntry` instances: identify COMPOSES relationships from compound
nodes, nest children accordingly, and store non-COMPOSES edges as references.

### Example structure

From the calculator fixture, the nested `entries` dict would look like:

```
entries:
  "calc" (NamespaceNode)
    children:
      ClassNode:
        "CalculatorEngine"
          children:
            MethodNode: {add, validateInput}
            AttributeNode: {precision}
          references: (REALIZES, ICalculator), (DEPENDS_ON, CalculatorResult),
                       (DEFINED_IN, /src/calc/calculator_engine.h)
        "CalculatorResult"
          children:
            MethodNode: {get_value}
            AttributeNode: {value}
          references: (DEFINED_IN, /src/calc/calculator_result.h)
  "ui" (NamespaceNode)
    children:
      ClassNode:
        "BaseWindow"
          children: MethodNode: {show}
          references: (DEFINED_IN, /src/ui/base_window.h)
        "CalculatorWindow"
          children:
            AttributeNode: {display, currentInput}
            MethodNode: {handleEquals}
          references: (INHERITS_FROM, BaseWindow),
                      (DEPENDS_ON, CalculatorEngine),
                      (DEFINED_IN, /src/ui/calculator_window.h)
  "ICalculator" (InterfaceNode)
    children: MethodNode: {calculate}
    references: (DEFINED_IN, /src/calc/icalculator.h)
  "Operation" (EnumNode)
    children: EnumValueNode: {ADD, SUBTRACT}
    references: (DEFINED_IN, /src/calc/operation.h)
  "/src/calc/calculator_engine.h" (FileNode)
  "/src/calc/icalculator.h" (FileNode)
  "/src/calc/operation.h" (FileNode)
  "/src/calc/calculator_result.h" (FileNode)
  "/src/ui/base_window.h" (FileNode)
  "/src/ui/calculator_window.h" (FileNode)
```

## Files to modify

| File | Change |
|---|---|
| `src/codegraph/models/member.py` | Remove `parent_compound`, `parent_interface`, `parent_enum` RelationshipFrom definitions |
| `src/codegraph/graph/__init__.py` | Add `CompositeEntry` dataclass; replace `LayerGraph.nodes`/`edges` with `entries`; rewrite `from_json`, `to_neo4j`, `to_json`, `from_neo4j` |
| `src/codegraph/repository.py` | Update `_build_layer_graph` to produce `CompositeEntry` structure; update all read methods |
| `src/codegraph/__init__.py` | Export `CompositeEntry`; remove `CodeGraphEdge` if present |
| `tests/test_layer_graph.py` | Update to use `entries` and `CompositeEntry`; remove dict-style edge assertions |
| `tests/test_graph_integration.py` | Update roundtrip tests for new structure |
| `tests/repository/test_graph_repository.py` | Update edge assertions to use `CompositeEntry` fields |
| `tests/member/test_attribute_defined_in_file.py` | Update if reverse COMPOSES was used |
| `tests/member/test_method_defined_in_file.py` | Update if reverse COMPOSES was used |
| `tests/member/test_method_invokes_method.py` | Update if edge dict access patterns changed |
| Tests referencing `graph.edges` | Update all assertions from dict access to attribute access |