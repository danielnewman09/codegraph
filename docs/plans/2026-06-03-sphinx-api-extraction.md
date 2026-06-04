# Sphinx API Metadata Extraction — Implementation Plan

**Spec:** `docs/specs/2026-06-03-sphinx-api-extraction-design.md`

## Step 1: Add sphinx dev dependency

**File:** `pyproject.toml`

Add `sphinx>=7.0` to the `dev` optional dependency group:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "sphinx>=7.0"]
```

Install: `pip install -e ".[dev]"`

---

## Step 2: Create Sphinx source directory and conf.py

**Directory:** `docs/source/` (new)

**File:** `docs/source/conf.py`

```python
"""Sphinx configuration for codegraph API metadata extraction."""

import sys
from pathlib import Path

# Make the source package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

project = "codegraph"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autodoc.typehints",
    "_builders.json_api",
]

# No theme needed — we only build JSON
html_theme = "basic"
```

Key points:
- `sys.path` insertion so autodoc can import `codegraph` from `src/`
- `_builders.json_api` extension loaded so the custom builder is registered
- `html_theme` is set to the built-in `"basic"` as a fallback; the JSON builder
  never renders HTML so this is inert but required by Sphinx validation

---

## Step 3: Create index.rst

**File:** `docs/source/index.rst`

```rst
API Reference
=============

.. automodule:: codegraph
   :members:

.. automodule:: codegraph.models
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

.. automodule:: codegraph.models.tags
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

Notes:
- Added `codegraph.models` and `codegraph.models.tags` which were not in the
  spec's index.rst but are public modules with docstrings worth extracting
- `:members:` emits only public members (no leading-underscore names)

---

## Step 4: Implement the custom JsonApiBuilder

**Directory:** `docs/_builders/` (new)

**File:** `docs/_builders/__init__.py` — empty, makes it a package.

**File:** `docs/_builders/json_api.py`

This is the core of the implementation. The builder:

1. Extends `sphinx.builders.Builder`
2. During the write phase, inspects the documented Python objects
3. For each documented class: extracts properties (from neomodel Property
   descriptors), relationships (from RelationshipTo/RelationshipFrom), methods,
   docstrings, and signatures
4. Writes a single `api_metadata.json` to the output directory

### Implementation structure

```python
"""JsonApiBuilder — Sphinx builder that emits API metadata as JSON."""

from __future__ import annotations

import inspect
import json
from typing import Any

from neomodel import (
    RelationshipTo,
    RelationshipFrom,
    StringProperty,
    IntegerProperty,
    FloatProperty,
    BooleanProperty,
    ArrayProperty,
    UniqueIdProperty,
    Property,
)
from sphinx.builders import Builder


# Map neomodel property classes to JSON-schema type strings
_NEOMODEL_TYPE_MAP: dict[type, str] = {
    StringProperty: "str",
    IntegerProperty: "int",
    FloatProperty: "float",
    BooleanProperty: "bool",
    ArrayProperty: "list[str]",
    UniqueIdProperty: "str",
}


class JsonApiBuilder(Builder):
    """Sphinx builder that writes API metadata to api_metadata.json."""

    name = "json_api"
    format = "json"
    epilog = "API metadata written to %(outdir)s/api_metadata.json"
    out_suffix = ".json"
    allow_parallel = False

    def init(self) -> None:
        self._metadata: dict[str, Any] = {}

    def get_outdated_docs(self):
        return ["index"]

    def get_target_uri(self, docname: str, typ: str | None = None) -> str:
        return docname

    def prepare_writing(self, docnames: set[str]) -> None:
        pass

    def write_doc(self, docname: str, doctree: Any) -> None:
        # We don't write per-doc; we collect after all docs are processed.
        pass

    def finish(self) -> None:
        """After all documents are processed, walk the documented objects and
        extract metadata."""
        self._extract_from_registry()
        output_path = self.outdir / "api_metadata.json"
        with open(output_path, "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)

    def _extract_from_registry(self) -> None:
        """Walk documented modules and extract metadata."""
        documented_modules = [
            "codegraph",
            "codegraph.models",
            "codegraph.models.compound",
            "codegraph.models.member",
            "codegraph.models.file",
            "codegraph.models.namespace",
            "codegraph.models.parameter",
            "codegraph.models.tags",
            "codegraph.graph",
            "codegraph.repository",
            "codegraph.constants",
            "codegraph.diagram",
        ]

        for mod_name in documented_modules:
            try:
                mod = __import__(mod_name, fromlist=[""])
            except ImportError:
                continue
            self._extract_module(mod)

    def _extract_module(self, mod) -> None:
        """Extract metadata from a module's public members."""
        if mod.__doc__:
            fqn = mod.__name__
            if fqn not in self._metadata:
                self._metadata[fqn] = {
                    "kind": "module",
                    "doc": inspect.cleandoc(mod.__doc__),
                }

        for name in sorted(dir(mod)):
            if name.startswith("_"):
                continue
            obj = getattr(mod, name, None)
            if obj is None:
                continue
            if inspect.isclass(obj):
                self._extract_class(obj, mod.__name__)
            elif inspect.isfunction(obj):
                self._extract_function(obj, mod.__name__)

    def _extract_class(self, cls: type, module_name: str) -> None:
        """Extract metadata for a class: properties, relationships, methods."""
        if not (cls.__module__ or "").startswith("codegraph"):
            return

        fqn = f"{cls.__module__}.{cls.__name__}"
        if fqn in self._metadata:
            return

        entry: dict[str, Any] = {
            "kind": "class",
            "doc": inspect.cleandoc(cls.__doc__) if cls.__doc__ else "",
        }

        bases = [
            b.__name__
            for b in inspect.getmro(cls)[1:]
            if b.__name__ not in ("object", "StructuredNode", "CodeGraphNode")
            and not b.__name__.startswith("_")
        ]
        if bases:
            entry["bases"] = bases

        properties = self._extract_properties(cls)
        if properties:
            entry["properties"] = properties

        relationships = self._extract_relationships(cls)
        if relationships:
            entry["relationships"] = relationships

        methods = self._extract_methods(cls)
        if methods:
            entry["methods"] = methods

        self._metadata[fqn] = entry

    def _extract_properties(self, cls: type) -> dict[str, Any]:
        """Extract neomodel property declarations from a class and its MRO."""
        props: dict[str, Any] = {}

        for klass in reversed(cls.__mro__):
            if klass is object:
                continue
            for name, val in vars(klass).items():
                if not isinstance(val, Property):
                    continue
                prop_entry: dict[str, Any] = {}

                for prop_cls, type_name in _NEOMODEL_TYPE_MAP.items():
                    if isinstance(val, prop_cls):
                        prop_entry["type"] = type_name
                        break
                if "type" not in prop_entry:
                    prop_entry["type"] = "any"

                if getattr(val, "required", False):
                    prop_entry["required"] = True

                default = getattr(val, "default", None)
                if default is not None and not callable(default):
                    prop_entry["default"] = str(default)

                help_text = getattr(val, "help_text", None)
                if help_text:
                    prop_entry["doc"] = help_text

                props[name] = prop_entry

        return props

    def _extract_relationships(self, cls: type) -> dict[str, Any]:
        """Extract neomodel RelationshipTo/RelationshipFrom descriptors."""
        rels: dict[str, Any] = {}

        for klass in reversed(cls.__mro__):
            if klass is object:
                continue
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue

                definition = val.definition
                is_outgoing = isinstance(val, RelationshipTo)

                target = definition.get("model") or val._raw_class
                if isinstance(target, str) and "." in target:
                    target = target.rsplit(".", 1)[-1]

                rels[name] = {
                    "label": definition["relation_type"],
                    "direction": "outgoing" if is_outgoing else "incoming",
                    "target": target,
                }

        return rels

    def _extract_methods(self, cls: type) -> dict[str, Any]:
        """Extract public methods with signatures and docstrings."""
        methods: dict[str, Any] = {}

        for name in sorted(dir(cls)):
            if name.startswith("_") and name not in ("__init__",):
                continue
            obj = getattr(cls, name, None)
            if obj is None:
                continue
            if not (inspect.isfunction(obj) or inspect.ismethod(obj)):
                continue
            if name in dir(object) and name != "__init__":
                continue

            method_entry: dict[str, Any] = {}

            try:
                sig = inspect.signature(obj)
                method_entry["signature"] = str(name) + str(sig)
            except (ValueError, TypeError):
                method_entry["signature"] = name + "(...)"

            doc = inspect.getdoc(obj)
            if doc:
                method_entry["doc"] = doc

            if doc and "Args:" in doc:
                args = self._parse_google_args(doc)
                if args:
                    method_entry["args"] = args

            if doc and "Returns:" in doc:
                returns = self._parse_google_returns(doc)
                if returns:
                    method_entry["returns"] = returns

            methods[name] = method_entry

        return methods

    def _parse_google_args(self, doc: str) -> dict[str, str]:
        """Parse Args: section from a Google-style docstring."""
        args: dict[str, str] = {}
        in_args = False
        for line in doc.splitlines():
            stripped = line.strip()
            if stripped == "Args:":
                in_args = True
                continue
            if in_args:
                if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                    break
                if ":" in stripped:
                    parts = stripped.split(":", 1)
                    param_name = parts[0].strip().rstrip("*")
                    param_desc = parts[1].strip()
                    if param_name:
                        args[param_name] = param_desc
        return args

    def _parse_google_returns(self, doc: str) -> str:
        """Parse Returns: section from a Google-style docstring."""
        lines: list[str] = []
        in_returns = False
        for line in doc.splitlines():
            stripped = line.strip()
            if stripped == "Returns:":
                in_returns = True
                continue
            if in_returns:
                if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                    break
                if stripped:
                    lines.append(stripped)
        return " ".join(lines)

    def _extract_function(self, func, module_name: str) -> None:
        """Extract metadata for a module-level function."""
        fqn = f"{module_name}.{func.__name__}"
        if fqn in self._metadata:
            return

        entry: dict[str, Any] = {
            "kind": "function",
            "doc": inspect.cleandoc(func.__doc__) if func.__doc__ else "",
        }

        try:
            sig = inspect.signature(func)
            entry["signature"] = func.__name__ + str(sig)
        except (ValueError, TypeError):
            entry["signature"] = func.__name__ + "(...)"

        doc = inspect.getdoc(func)
        if doc and "Args:" in doc:
            args = self._parse_google_args(doc)
            if args:
                entry["args"] = args
        if doc and "Returns:" in doc:
            returns = self._parse_google_returns(doc)
            if returns:
                entry["returns"] = returns

        self._metadata[fqn] = entry


def setup(app) -> dict:
    """Register the JsonApiBuilder with Sphinx."""
    app.add_builder(JsonApiBuilder)
    return {"version": "0.1", "parallel_read_safe": True}
```

### Key design notes

- The builder does **not** try to intercept autodoc's internal documenter
  registry. Instead, after the build phase completes, it re-imports and
  inspects the documented modules directly. This is more robust and testable
  than depending on Sphinx internals that may change between versions.
- The `finish()` hook is the right place — it runs after autodoc has resolved
  all objects, which means the modules are guaranteed importable with the
  `sys.path` set in `conf.py`.
- `neomodel` Property inspection checks the MRO so inherited properties are
  captured (e.g., `ClassNode` inherits `qualified_name` from `_CompoundMixin`).
- Relationship extraction also walks the MRO for the same reason.
- Duplicated entries are prevented by checking `fqn in self._metadata` before
  processing.

---

## Step 5: Add docs/_build/ to .gitignore

**File:** `.gitignore`

Append:

```
docs/_build/
```

---

## Step 6: Upgrade docstrings to Google style

Each file listed below needs its public class and method docstrings updated
to include `Args:` and `Returns:` sections where applicable. Properties that
already have `help_text` on neomodel Property descriptors don't need doc
changes — the builder reads `help_text` directly.

### File-by-file changes

#### `src/codegraph/models/tags.py`

- `CodeGraphNode` class docstring: already comprehensive narrative. Add
  structured sections for the key methods.
- `find_relationship_manager`: add `Args:` (source, relation_type, target)
  and `Returns:`
- `fetch_by_layer`: add `Args:` (layer) and `Returns:`
- `fetch_all_by_layer`: add `Args:` (layer) and `Returns:`
- `fetch_all_by_source`: add `Args:` (source) and `Returns:`
- `fetch_all_by_kind`: add `Args:` (kind, layer) and `Returns:`
- `serialize`: add `Returns:`
- `deserialize`: add `Args:` (data) and `Returns:`
- `from_json`: add `Args:` (data) and `Returns:`, keep existing `Raises` note
- `serialize_relationships`: add `Returns:`
- `serialize_edges`: add `Returns:`
- `_uid_prop`: add `Returns:`
- `_uid_value`: add `Returns:`

#### `src/codegraph/models/compound.py`

- `ClassNode`: ensure class docstring describes purpose. Field descriptions
  come from `help_text` where available, otherwise add an `Attributes:`
  section to the class docstring.
- `InterfaceNode`, `EnumNode`, `UnionNode`, `ModuleNode`: same treatment.
- These classes have no custom methods beyond inherited ones, so only
  class-level docstrings matter.

#### `src/codegraph/models/member.py`

- `MethodNode`, `AttributeNode`, `EnumValueNode`, `FunctionNode`,
  `DefineNode`: ensure class docstrings describe purpose. Add `Attributes:`
  sections for class-specific fields that lack `help_text`.
- These classes have no custom methods beyond inherited ones.

#### `src/codegraph/models/file.py`

- `FileNode`: class docstring already has a `Fields` section in a non-Google
  format. Convert to Google style with an `Attributes:` section listing each
  property with its type and description.

#### `src/codegraph/models/namespace.py`

- `NamespaceNode`: add `Attributes:` section describing `qualified_name`,
  `kind`, `layer`, `component_id`, `description`.

#### `src/codegraph/models/parameter.py`

- `ParameterNode`: add `Attributes:` section for `position`, `type`,
  `default_value`, `member_refid`.

#### `src/codegraph/graph/__init__.py`

- `LayerGraph` class: add `Attributes:` for `layer`, `nodes`, `edges`.
- `LayerGraph._node_key`: add `Args:` (obj) and `Returns:`.
- `LayerGraph.from_json`: add `Args:` (data) and `Returns:`.
- `LayerGraph.to_neo4j`: no changes needed (no args, no return).
- `LayerGraph.to_json`: add `Returns:`.
- `LayerGraph.from_neo4j`: add `Args:` (layer) and `Returns:`.

#### `src/codegraph/repository.py`

- `GraphRepository` class docstring: already short and descriptive. Keep.
- `_get_node_by_qualified_name`: add `Args:` (qualified_name), `Returns:`.
- `_get_member_by_qualified_name`: add `Args:` (qualified_name), `Returns:`.
- `_build_layer_graph`: add `Args:` (seeds), `Returns:`.
- `get_by_layer`: add `Args:` (layer), `Returns:`.
- `get_by_source`: add `Args:` (source), `Returns:`.
- `get_by_namespace`: add `Args:` (qualified_name), `Returns:`.
- `get_by_compound`: add `Args:` (qualified_name), `Returns:`.
- `get_by_neighbourhood`: add `Args:` (qualified_name), `Returns:`.
- `get_by_kind`: add `Args:` (kind, layer), `Returns:`.
- `save_layer_graph`: add `Args:` (graph).

#### `src/codegraph/diagram.py`

- `_ensure_list`: add `Args:` (parent, attr_name), `Returns:`.
- `_is_relationship_property`: add `Args:` (prop), `Returns:`.
- `Association`: add `Attributes:` for all fields.
- `ClassDiagram.__init__`: add `Args:` for all parameters.
- `ClassDiagram.model_validate`: add `Args:` (data), `Returns:`.
- `ClassDiagram.model_json_schema`: add `Returns:`.
- `ClassDiagram.from_layer`: add `Args:` (layer), `Returns:`.
- `ClassDiagram.get_entity`: add `Args:` (qualified_name), `Returns:`.
- `ClassDiagram.classes_in_module`: add `Args:` (module), `Returns:`.
- `ClassDiagram.to_summary`: add `Returns:`.
- `ClassDiagram.to_verification_dicts`: add `Returns:`.
- `ClassDiagram.to_draft_lookup`: add `Returns:`.
- `ClassDiagram.to_class_lookup`: add `Returns:`.
- `ClassDiagram.to_graph_dict`: add `Returns:`.
- `ClassDiagram.from_graph_dict`: add `Args:` (data), `Returns:`.

#### `src/codegraph/constants.py`

- No methods to update. Module docstring is already descriptive. The
  builder will capture it as a module-level entry with `kind: "module"`.
- `valid_specializations`: add `Args:` (language, kind) and `Returns:`.

#### `src/codegraph/__init__.py`

- Module docstring is already descriptive. No methods (it's just imports).
  The builder captures it as a module entry.

---

## Step 7: Verify the build runs

Run the extraction build:

```bash
sphinx-build -b json_api docs/source docs/_build
```

Verify:

1. Command exits with code 0 (no warnings or errors)
2. `docs/_build/api_metadata.json` exists and is valid JSON
3. The JSON contains entries for all expected classes:
   - `codegraph.models.compound.ClassNode`
   - `codegraph.models.compound.InterfaceNode`
   - `codegraph.models.compound.EnumNode`
   - `codegraph.models.compound.UnionNode`
   - `codegraph.models.compound.ModuleNode`
   - `codegraph.models.member.MethodNode`
   - `codegraph.models.member.AttributeNode`
   - `codegraph.models.member.EnumValueNode`
   - `codegraph.models.member.FunctionNode`
   - `codegraph.models.member.DefineNode`
   - `codegraph.models.file.FileNode`
   - `codegraph.models.namespace.NamespaceNode`
   - `codegraph.models.parameter.ParameterNode`
   - `codegraph.models.tags.CodeGraphNode`
   - `codegraph.graph.LayerGraph`
   - `codegraph.repository.GraphRepository`
   - `codegraph.diagram.ClassDiagram`
   - `codegraph.diagram.Association`
4. Each class entry has `properties`, `relationships`, and `methods` sub-objects
   where applicable
5. ClassNode has relationships like `defined_in`, `methods`, `attributes`,
   `base`, `references`, `realizes`
6. Method signatures include type annotations (from `inspect.signature`)

---

## Step 8: Run existing tests to confirm no regressions

```bash
pytest
```

Ensures docstring changes haven't broken anything. Docstring changes are
purely additive — they should not affect runtime behavior — but this is a
safety check.

---

## Summary of files changed

| File | Change |
|------|--------|
| `pyproject.toml` | Add `sphinx>=7.0` to dev deps |
| `docs/source/conf.py` | New — Sphinx config |
| `docs/source/index.rst` | New — automodule directives |
| `docs/_builders/__init__.py` | New — package marker |
| `docs/_builders/json_api.py` | New — JsonApiBuilder implementation |
| `.gitignore` | Add `docs/_build/` |
| `src/codegraph/models/tags.py` | Google-style Args/Returns on all public methods |
| `src/codegraph/models/compound.py` | Google-style Attributes on ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode |
| `src/codegraph/models/member.py` | Google-style Attributes on MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode |
| `src/codegraph/models/file.py` | Convert Fields section to Google Attributes |
| `src/codegraph/models/namespace.py` | Add Attributes section |
| `src/codegraph/models/parameter.py` | Add Attributes section |
| `src/codegraph/graph/__init__.py` | Google-style Args/Returns on LayerGraph methods |
| `src/codegraph/repository.py` | Google-style Args/Returns on GraphRepository methods |
| `src/codegraph/diagram.py` | Google-style Args/Returns on ClassDiagram/Association methods |
| `src/codegraph/constants.py` | Google-style Args/Returns on `valid_specializations` |