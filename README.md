# Codegraph

Shared Neo4j codebase graph data model with tag-aware graph containers.

Provides atomized neomodel Node models (`ClassNode`, `InterfaceNode`,
`EnumNode`, `MethodNode`, `AttributeNode`, `FileNode`, `NamespaceNode`,
`ParameterNode`, etc.), a `LayerGraph` container for loading and persisting
complete design views, PlantUML export/import for diagram generation,
graph visualization containers (`CompoundGraph`, `NamespaceGraph`,
`OntologyGraph`), and constants (kinds, tags, predicates, schema DDL).

Used by:
- [Doxygen Dependency Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser) — populates `as-built` and `dependency` tags
- [Ticketing System](https://github.com/danielnewman09/ticketing-system) — adds the `design` tag

## Install

```bash
pip install codegraph
```

For development:

```bash
pip install codegraph[dev]
```

### PlantUML (optional)

To compile PlantUML diagrams to PNG in tests, download the PlantUML jar:

```bash
mkdir -p tools
curl -L -o tools/plantuml.jar \
  https://github.com/plantuml/plantuml/releases/download/v1.2024.8/plantuml-1.2024.8.jar
```

Requires Java runtime (`java` on PATH). The `tools/` directory is
gitignored. Tests that compile PNGs are automatically skipped if the
jar is not present.

## Tags

Nodes are tagged with provenance tags indicating their origin:

| Tag | Description |
|---|---|
| `design` | Intended architecture (from UML, tickets, design docs) |
| `as-built` | Actual implementation (from Doxygen, static analysis) |
| `dependency` | Compile-time and runtime dependencies |

A node can carry multiple tags simultaneously — a class that exists in
both the design and as-built views would have `tags=["design", "as-built"]`.
Tags can be added or removed independently:

```python
node.add_tag("as-built")   # node now has ["design", "as-built"]
node.remove_tag("design")  # node now has ["as-built"]
node.has_tag("design")     # False
```

## Node models

Every node inherits from `CodeGraphNode`, which provides `serialize()`,
`deserialize()`, and relationship introspection.

Each node has a deterministic `uid` (SHA-1 hash of identity fields)
that is stable across codebases — the same logical symbol produces the
same `uid` regardless of where it was loaded from.  Human-readable
fields (`qualified_name`, `refid`) are indexed but not unique.

| Category | Node types | Identity fields |
|---|---|---|
| Compound | `ClassNode`, `InterfaceNode`, `EnumNode`, `UnionNode`, `ModuleNode` | `qualified_name` |
| Member | `MethodNode`, `FunctionNode` | `qualified_name` + `argsstring` (normalised types) |
| Member | `AttributeNode`, `EnumValueNode`, `DefineNode` | `qualified_name` |
| Namespace | `NamespaceNode` | `qualified_name` |
| File | `FileNode` | `path` |
| Parameter | `ParameterNode` | `member_refid` + `position` |

Method and function nodes include the normalised `argsstring` in their
uid computation, so overloads with the same name but different parameter
types get distinct uids.  Parameter names and default values are stripped;
only the types are retained.

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
        "tags": ["design"],
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
        "tags": ["design"],
        "visibility": "public",
        "type_signature": "CalculatorResult",
        "edges": []
    }
]
```

Each edge has:
- `relation_type` — Neo4j relationship label (e.g. `COMPOSES`, `INHERITS_FROM`, `DEFINED_IN`)
- `target_type` — the node class of the target
- `target_local_id` — the target node's `uid` (deterministic hash of identity fields)

## PlantUML Export / Import

`export_plantuml` converts a `LayerGraph` to a PlantUML class diagram.
`import_plantuml` parses PlantUML back into a `LayerGraph`, deriving
qualified names from the nesting structure — no alias parsing needed.

```python
from codegraph.plantuml import export_plantuml, import_plantuml

# Export
puml = export_plantuml(graph)  # LayerGraph → PlantUML string
print(puml)

# Import — qualified names derived from nesting
restored = import_plantuml(puml, tags=frozenset({"design"}))
```

### Import design

Qualified names are derived from nesting, not from `as alias` text.
A class `"CalculatorEngine"` inside `package "calc"` becomes
`calc::CalculatorEngine`. Arrow targets are resolved using the same
`_sanitize_alias` convention the exporter uses, so export→import
round-trips preserve core structure (namespaces, compounds, members,
relationships) without any JSON metadata blob.

This supports the workflow: export a diagram, edit it manually or via
an LLM agent, then import the modified diagram back as a fresh graph.

### Node-type mapping

| CodeGraph type | PlantUML element |
|---|---|
| `NamespaceNode` | `package` |
| `ClassNode` | `class` |
| `InterfaceNode` | `interface` |
| `EnumNode` | `enum` |
| `UnionNode` | `class <<union>>` |
| `ModuleNode` | `package <<module>>` |
| `ConceptNode` | `class <<concept>>` |
| `MethodNode` | method inside parent class |
| `AttributeNode` | field inside parent class |
| `EnumValueNode` | constant inside parent enum |
| `FunctionNode` | `class <<function>>` |
| `FileNode` | `note` |

### Relationship mapping

| CodeGraph predicate | PlantUML arrow |
|---|---|
| `INHERITS_FROM` | `<\|--` |
| `REALIZES` | `..\|>` |
| `COMPOSES` | nesting / `*--` |
| `DEPENDS_ON` | `..>` |
| `REFERENCES` | `-->` |
| `INVOKES` | `..>` (labelled) |
| `ASSOCIATES` | `-->` |
| `AGGREGATES` | `o--` |

### Compile to PNG

```bash
java -jar tools/plantuml.jar -tpng diagram.puml
```

Or programmatically via the test suite, which compiles exported
PlantUML to PNG files in `unit_test_data/`.

## HTML Visualization

`codegraph-html` is a command-line tool that reads a code-graph JSON
file and produces a self-contained interactive HTML visualisation using
[Cytoscape.js](https://js.cytoscape.org/).  No Neo4j connection required —
it loads directly from JSON.

### Configuration

The tool reads a config file from the project directory, in priority
order:

1. **`.codegraph.toml`** (standalone codegraph config):

   ```toml
   [project]
   name = "design"
   output_dir = "build/docs"
   ```

2. **`.doxygen-index.toml`** (the config used by
   [Doxygen-Dependency-Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser)'s
   `doxygen-index` tool). When `.codegraph.toml` is absent, the HTML
   output directory is taken from the optional `[codegraph-html]`
   section (defaulting to `"codegraph"`), and the project name from
   `[project].name`:

   ```toml
   [project]
   name = "codegraph"
   language = "python"
   input_paths = ["src"]

   [codegraph-html]
   output_dir = "codegraph"
   ```

This lets a project keep a single `.doxygen-index.toml` for both the
parser and the HTML renderer.

- **`name`** — the project / graph name, used for the input JSON filename
  (`{output_dir}/{name}.json`) and the default output HTML filename
  (`{output_dir}/{name}.html`).
- **`output_dir`** — directory containing the code-graph JSON file.

### Usage

```bash
# Auto-detect .codegraph.toml or .doxygen-index.toml in the current dir
codegraph-html

# Use a config file in another directory
codegraph-html --project-dir ../my-project

# Override the output path
codegraph-html --output custom.html

# Use compact layout
codegraph-html --size small
```

### Example workflow

```bash
# 1. Generate a code-graph JSON (e.g. via LayerGraph.serialize())
python -c '
import json
from codegraph import LayerGraph
graph = LayerGraph.from_neo4j("design")
with open("build/docs/design.json", "w") as f:
    json.dump(graph.serialize(), f, indent=2)
'

# 2. Render as HTML
codegraph-html
# → writes build/docs/design.html
```

### Python API

You can also call the export functions directly:

```python
from codegraph.viz import export_html_from_json

# Load from JSON file → HTML (no Neo4j needed)
export_html_from_json("path/to/graph.json", "output.html")

# Or fetch from Neo4j by tag → HTML
from codegraph.viz import export_html
export_html("design", "design.html")
```

## CodeGraphNode API

All node types inherit from `CodeGraphNode`, which provides:

| Method | Description |
|---|---|
| `serialize(fields="llm")` | Dict with `type`, property fields, and `edges`. `fields="llm"` (default) includes only `_llm_fields`; `fields="all"` includes every defined property |
| `deserialize(data)` | Factory: dispatches to the correct subclass by `type` key, then instantiates |
| `serialize_edges()` | Live edges from Neo4j (requires saved node) |
| `serialize_relationships()` | Static relationship descriptors (no DB call) |
| `find_relationship_manager(source, relation_type, target)` | Find the neomodel relationship manager matching a relation type and target class |
| `fetch_by_tag(tag)` | Fetch all persisted nodes of this type matching a tag |
| `fetch_all_by_tag(tag)` | Fetch all nodes across all registered types matching a tag |
| `add_tag(tag)` | Add a tag, persist to Neo4j. Returns self for chaining |
| `remove_tag(tag)` | Remove a tag, persist to Neo4j. Returns self for chaining |
| `has_tag(tag)` | Check whether a tag is present |

## Neo4j Docker Container (codegraph-db)

`codegraph-db` is a command-line tool that manages a project-local Neo4j
Docker container.  Each project gets its own container named
`neo4j-<project_name>` with the Neo4j data files bind-mounted under
`<project_root>/codegraph/neo4j/`.  This keeps every project's graph
data self-contained and portable — stop the container, and the database
files persist on disk; start it again, and the database is loaded from
the persisted files.

### Prerequisites

* Docker Desktop (or Docker Engine + CLI) running locally.
* A `.codegraph.toml` or `.doxygen-index.toml` in the project root
  with a `[project].name` field.

### Configuration

The `[codegraph-db]` section (in either config file) customises the
Docker settings.  All fields are optional:

```toml
[codegraph-db]
image = "neo4j:5-community"   # Docker image (default: neo4j:5-community)
bolt_port = 7687              # Host Bolt port  (default: 7687)
http_port = 7474              # Host HTTP port  (default: 7474)
password = "codegraph-dev"   # Initial password (default: codegraph)
```

If you run multiple codegraph-backed projects simultaneously, give
each project different `bolt_port` / `http_port` values to avoid
conflicts.

### Directory layout

```
<project_root>/
└── codegraph/
    └── neo4j/
        ├── data/       →  /data        (database files — persisted)
        ├── logs/       →  /logs        (server logs)
        ├── import/     →  /import      (bulk-import CSVs)
        └── plugins/    →  /plugins     (APOC, etc.)
```

The `codegraph/neo4j/` directory is automatically git-ignored.

### Commands

```bash
# Initialise directories and pull the image (optional — start does this too)
codegraph-db init

# Create and start the container (loads persisted data if present)
codegraph-db start

# Stop the container (data is preserved on disk)
codegraph-db stop

# Restart
codegraph-db restart

# Show status, ports, and Bolt connectivity
codegraph-db status

# View logs (add -f to follow)
codegraph-db logs -f

# Open an interactive Cypher shell
codegraph-db shell

# Print / open the Neo4j Browser
codegraph-db browser

# Remove the container (data files are preserved)
codegraph-db rm --force
```

All commands accept `--project-dir DIR` to target a project other
than the current directory.

### .env management

On `start` and `init`, `codegraph-db` updates the project's `.env` file
with a managed block so that `codegraph` itself connects to the right
container:

```bash
# >>> codegraph-db >>>
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=codegraph-dev
# <<< codegraph-db <<<
```

Lines outside the managed block are preserved.  Repeated `start` calls
are idempotent — the block is replaced, not duplicated.

### Typical workflow

```bash
# 1. Start the project's Neo4j container
codegraph-db start

# 2. Load graph data into Neo4j
python scripts/load_api_to_neo4j.py

# 3. Query / visualise
python -c '
from codegraph import LayerGraph
design = LayerGraph.from_neo4j("design")
'

# 4. Stop when done — data is preserved
codegraph-db stop
```

### Python module entry point

You can also invoke the tool via the package's `__main__`:

```bash
python -m codegraph db start
python -m codegraph db status
python -m codegraph db stop
```

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

### PlantUML compilation tests

Tests in `TestPngCompilation` compile exported PlantUML to PNG and
save the results to `unit_test_data/`. These tests are automatically
skipped if `tools/plantuml.jar` is not present or `java` is not on
PATH. To run them:

```bash
# Download PlantUML jar (one-time setup)
mkdir -p tools
curl -L -o tools/plantuml.jar \
  https://github.com/plantuml/plantuml/releases/download/v1.2024.8/plantuml-1.2024.8.jar

# Run all tests (PNG compilation tests included if jar is present)
pytest
```

## License

MIT