# Sphinx API Metadata Extraction — Design

**Date:** 2026-06-03
**Status:** Approved

## Goal

Use Sphinx as a metadata extraction pipeline to auto-generate an LLM tool
schema from the codegraph Python source, keeping the schema in sync as the
codebase evolves.

## Architecture

```
Python source + docstrings
        │
        ▼
   Sphinx (autodoc + napoleon + typehints)
        │
        ▼
   api_metadata.json   ──►  LLM tool schema
        │
        ▼
   LLM produces codegraph JSON  ──►  LayerGraph.from_json()  ──►  Neo4j
```

Sphinx is the **parser**, not a documentation publisher. There is no HTML
rendering. The build target is a single `.json` file containing structured
metadata about every public class, method, parameter, relationship, and
constant.

## Components

### 1. Sphinx configuration

**File:** `docs/source/conf.py`

Minimal configuration purpose-built for extraction:

```python
project = "codegraph"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autodoc.typehints",
]
```

No theme, no templates, no intersphinx. Napoleon parses Google-style
docstrings; typehints renders annotations into the documenter data.

### 2. Custom Sphinx Builder

**File:** `docs/_builders/json_api.py`

A Sphinx builder registered as `-b json_api`. It reads autodoc's parsed
`Documenter` objects and serializes the relevant fields into the JSON
structure specified below.

Structure:

- `JsonApiBuilder` extends `sphinx.builders.Builder`
- Collects `Documenter` instances from autodoc's internal registry during the
  build
- After the read phase, walks the documenters and extracts: name, docstring,
  signature, args, type hints, neomodel property declarations, relationship
  declarations
- Writes a single `api_metadata.json` to the output directory
- Skips HTML/template rendering entirely

The builder module defines a top-level `setup(app)` function that Sphinx
calls when the extension is loaded. It is added to `extensions` in
`conf.py` (e.g. `extensions = ["_builders.json_api", ...]`) so that
`sphinx-build -b json_api` recognizes the builder name.

### 3. index.rst

**File:** `docs/source/index.rst`

Tells autodoc what to document:

```rst
API Reference
=============

.. automodule:: codegraph
   :members:

.. automodule:: codegraph.models.compound
   :members:

.. automodule:: codegraph.models.member
   :members:

.. automodule:: codegraph.models.file
   :members:

.. automodule:: codegraph.models.namespace
   :members:

.. automodule:: codegraph.models.parameter
   :members:

.. automodule:: codegraph.graph
   :members:

.. automodule:: codegraph.repository
   :members:

.. automodule:: codegraph.constants
   :members:

.. automodule:: codegraph.diagram
   :members:
```

Private helpers (leading underscore) are excluded — they are not emitted by
automodule's `:members:` directive.

### 4. JSON output format

The builder produces a single JSON file keyed by fully-qualified names. Each
entry contains the metadata the LLM needs to reason about constructing
codegraph objects:

```json
{
  "codegraph.models.compound.ClassNode": {
    "doc": "Represents a class in the codebase graph.",
    "bases": ["_CompoundMixin"],
    "properties": {
      "qualified_name": {"type": "str", "required": true, "doc": "Unique identifier"},
      "kind": {"type": "str", "required": true, "doc": "One of: class, struct"},
      "layer": {"type": "str", "default": "design", "doc": "Origin layer"},
      "visibility": {"type": "str", "default": "", "doc": "Access level"}
    },
    "relationships": {
      "defined_in": {"target": "FileNode", "label": "DEFINED_IN", "direction": "outgoing"},
      "inherits_from": {"target": "ClassNode", "label": "INHERITS_FROM", "direction": "incoming"}
    },
    "methods": {
      "serialize": {
        "signature": "serialize() -> dict",
        "doc": "Full dict with type, properties, and edges."
      },
      "from_json": {
        "signature": "from_json(data: dict) -> ClassNode",
        "doc": "Instantiate from a dict.",
        "args": {"data": "dict — serialized node payload"}
      }
    }
  },
  "codegraph.graph.LayerGraph": {
    "doc": "A Python-only container for all nodes in a design view.",
    "properties": {
      "layer": {"type": "str", "required": true, "doc": "design | as-built | dependency"},
      "nodes": {"type": "dict[str, CodeGraphNode]", "doc": "Nodes keyed by local identifier"},
      "edges": {"type": "list[dict]", "doc": "Logical edge tuples for deferred persistence"}
    },
    "methods": {
      "from_json": {
        "signature": "from_json(data: list[dict]) -> LayerGraph",
        "doc": "Deserialize from a JSON array.",
        "args": {"data": "list[dict] — JSON array of node payloads"}
      },
      "to_neo4j": {
        "signature": "to_neo4j() -> None",
        "doc": "Persist all nodes and edges to Neo4j."
      }
    }
  }
}
```

Key decisions:

- **Nodes and relationships are first-class** — neomodel `RelationshipTo`/
  `RelationshipFrom` declarations are extracted, since those define the valid
  graph structure the LLM needs to know about.
- **Properties come from neomodel Property declarations** —
  `StringProperty(required=True)`, `IntegerProperty(default=0)`, etc. give
  type, required, and default directly.
- **Methods include signatures + args** — so the LLM knows how to call them.
- **Constants module included** — `PREDICATES`, `LAYERS`, `COMPOUND_KINDS`,
  etc. are enumerated so the LLM knows the valid values.

### 5. Docstring upgrade

Current docstrings are narrative — descriptive but without structured
`Args:`/`Returns:` sections. Napoleon needs those to extract parameter and
return-type metadata into the JSON. Without them, the LLM gets descriptions
but not the argument spec.

Each public class and method docstring needs Google-style sections where
applicable. Example:

```python
# Before
"""Derive a stable local key from a node instance or raw dict.

For dicts (raw JSON data), uses ``type`` and ``path``/``name``.
For CodeGraphNode instances, uses ``path`` for FileNode, ``name``
otherwise.
"""

# After
"""Derive a stable local key from a node instance or raw dict.

For dicts (raw JSON data), uses ``type`` and ``path``/``name``.
For CodeGraphNode instances, uses ``path`` for FileNode, ``name``
otherwise.

Args:
    obj: A CodeGraphNode instance or raw dict with ``type``/``name``/``path`` keys.

Returns:
    The stable local key string.
"""
```

**Scope:** Public API only — the `__all__` exports plus the key internal
methods the LLM needs to know about (`serialize`, `from_json`, `to_neo4j`,
`fetch_by_layer`, etc.). Private helpers with leading underscores are
excluded via the automodule directives.

**Modules to update:**

- `models/compound.py` — 5 classes + `_CompoundMixin`
- `models/member.py` — 5 classes + `_MemberMixin`
- `models/file.py` — `FileNode`
- `models/namespace.py` — `NamespaceNode`
- `models/parameter.py` — `ParameterNode`
- `models/tags.py` — `CodeGraphNode` base
- `graph/__init__.py` — `LayerGraph`
- `repository.py` — `GraphRepository`
- `diagram.py` — `ClassDiagram`, `Association`
- `constants.py` — module docstring only (no methods)

### 6. Dev dependencies & build integration

**`pyproject.toml` change:**

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "sphinx>=7.0"]
```

Only `sphinx` itself. `autodoc`, `napoleon`, and `typehints` are built-in
extensions. No additional theme package needed since no HTML is rendered.

**Run command:**

```bash
sphinx-build -b json_api docs/source docs/_build
# Output: docs/_build/api_metadata.json
```

**Git:** `docs/_build/` is gitignored (generated output). `docs/source/`
(`conf.py`, `index.rst`) and `docs/_builders/json_api.py` are committed.