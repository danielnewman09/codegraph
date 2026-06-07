# Codegraph

Shared Neo4j codebase graph data model with layer-aware graph containers.

Provides atomized neomodel Node models (`ClassNode`, `InterfaceNode`,
`EnumNode`, `MethodNode`, `AttributeNode`, `FileNode`, `NamespaceNode`,
`ParameterNode`, etc.), a `LayerGraph` container for loading and persisting
complete design views, graph visualization containers (`CompoundGraph`,
`NamespaceGraph`, `OntologyGraph`), and constants
(kinds, layers, predicates, schema DDL).

Used by:
- [Doxygen Dependency Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser) — populates `as-built` and `dependency` layers
- [Ticketing System](https://github.com/danielnewman09/ticketing-system) — adds the `design` layer

## Install

```bash
pip install codegraph
```

For development:

```bash
pip install codegraph[dev]
```

## Layers

Nodes are tagged with a `layer` property indicating their origin:

| Layer | Description |
|---|---|
| `design` | Intended architecture (from UML, tickets, design docs) |
| `as-built` | Actual implementation (from Doxygen, static analysis) |
| `dependency` | Compile-time and runtime dependencies |

## Node models

Every node inherits from `CodeGraphNode`, which provides `serialize()`,
`deserialize()`, and relationship introspection.

| Category | Node types | UID property |
|---|---|---|
| Compound | `ClassNode`, `InterfaceNode`, `EnumNode`, `UnionNode`, `ModuleNode` | `qualified_name` |
| Member | `MethodNode`, `AttributeNode`, `EnumValueNode`, `FunctionNode`, `DefineNode` | `qualified_name` |
| Namespace | `NamespaceNode` | `qualified_name` |
| File | `FileNode` | `refid` |
| Parameter | `ParameterNode` | `name` |

## LayerGraph

`LayerGraph` is the top-level API for interacting with an entire design view.
It is a Python-only container (not a Neo4j node) that holds a nested
composition structure. Root entries are nodes not composed by any other
node (files, namespaces, orphan compounds). COMPOSES edges create nesting
— children live inside their parent entry. All other relationship types are
stored as references on each entry.

```python
from codegraph import LayerGraph
```

### Load from JSON

Deserialize a JSON array of node payloads. **No database interaction** —
pure in-memory construction:

```python
graph = LayerGraph.deserialize(nodes_data)

# Access root entries (files, namespaces, orphan compounds)
calc_ns = graph.entries["calc"]  # NamespaceNode entry

# Navigate the composition tree
calc_engine = calc_ns.children["ClassNode"]["CalculatorEngine"]
print(calc_engine.node.name)  # "CalculatorEngine"
print(calc_engine.children.keys())  # {"MethodNode", "AttributeNode"}

# Non-COMPOSES relationships are stored as references
for rel_type, target_key, target_type in calc_engine.references:
    print(f"{rel_type} -> {target_type} {target_key}")

# The layer is inferred from the node data (defaults to "design")
print(graph.layer)  # "design"
```

### Persist to Neo4j

Explicitly save all nodes and connect all relationships:

```python
graph.to_neo4j()
```

After persistence, each node owns its live relationships via neomodel.
Call ``node.serialize()`` to see both COMPOSES children and other edges.

### Serialize back to JSON

```python
serialized = graph.serialize()
# Returns a list of dicts, each with "type", properties, and "edges"
# Convert to JSON externally with json.dumps(serialized)
```

### Query from Neo4j

Fetch all nodes in a layer, plus their first-level neighbors (nodes
connected by any edge to a layer-matched node):

```python
design = LayerGraph.from_neo4j("design")
as_built = LayerGraph.from_neo4j("as-built")
deps = LayerGraph.from_neo4j("dependency")

# Walk all entries depth-first
for entry in design._all_entries():
    node = entry.node
    print(f"{node.__class__.__name__}: {node.name}")
    for child_type, children in entry.children.items():
        for child_key, child_entry in children.items():
            print(f"  COMPOSES {child_type}: {child_key}")
```

### Roundtrip workflow

```python
# Load → persist → serialize → reload
graph = LayerGraph.deserialize(nodes_data)
graph.to_neo4j()
json_data = graph.serialize()

# Write to file
import json
with open("my_graph.json", "w") as f:
    json.dump(json_data, f, indent=2)

# Read back
with open("my_graph.json") as f:
    loaded = json.load(f)
restored = LayerGraph.deserialize(loaded)
```

## JSON format

`LayerGraph.deserialize()` accepts a list of dicts where each item is a
serialized node with a `type` discriminator:

```json
[
    {
        "type": "ClassNode",
        "name": "CalculatorEngine",
        "kind": "class",
        "layer": "design",
        "visibility": "public",
        "brief_description": "Core calculator engine",
        "edges": [
            {
                "relation_type": "COMPOSES",
                "target_type": "MethodNode",
                "target_local_id": "add"
            }
        ]
    },
    {
        "type": "MethodNode",
        "name": "add",
        "kind": "method",
        "layer": "design",
        "visibility": "public",
        "type_signature": "CalculatorResult",
        "edges": []
    }
]
```

Each edge has:
- `relation_type` — Neo4j relationship label (e.g. `COMPOSES`, `INHERITS_FROM`, `DEFINED_IN`)
- `target_type` — the node class of the target
- `target_local_id` — the lookup key for the target node (`name` for most
  nodes, `path` for `FileNode`)

When deserializing output from `serialize()`, edges use `target_uid` (the
Neo4j unique ID) instead of `target_local_id`. Both formats are accepted.

## CodeGraphNode API

All node types inherit from `CodeGraphNode`, which provides:

| Method | Description |
|---|---|
| `serialize()` | Full dict with `type`, properties, and `edges` |
| `deserialize(data)` | Factory: dispatches to the correct subclass by `type` key, then instantiates |
| `serialize_edges()` | Live edges from Neo4j (requires saved node) |
| `serialize_relationships()` | Static relationship descriptors (no DB call) |
| `find_relationship_manager(source, relation_type, target)` | Find the neomodel relationship manager matching a relation type and target class |
| `fetch_by_layer(layer)` | Fetch all persisted nodes of this type matching a layer |
| `fetch_all_by_layer(layer)` | Fetch all nodes across all registered types matching a layer |

## Testing

```bash
# Run all tests (requires Neo4j)
pytest

# Run with coverage
pytest --cov=codegraph --cov-report=term-missing
```

Neo4j credentials are loaded from a `.env` file via `python-dotenv`:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

## License

MIT