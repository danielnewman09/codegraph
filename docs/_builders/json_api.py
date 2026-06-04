"""JsonApiBuilder — Sphinx builder that emits API metadata as JSON."""

from __future__ import annotations

import inspect
import json
from typing import Any

from neomodel import RelationshipTo, RelationshipFrom, StructuredNode
from neomodel.properties import (
    ArrayProperty,
    BooleanProperty,
    FloatProperty,
    IntegerProperty,
    Property,
    StringProperty,
    UniqueIdProperty,
)
from sphinx.builders import Builder

from codegraph.models.tags import CodeGraphNode

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
            # Skip re-exports: only include classes/functions defined in codegraph
            if inspect.isclass(obj):
                obj_mod = getattr(obj, "__module__", None)
                if obj_mod and not obj_mod.startswith("codegraph"):
                    continue
                self._extract_class(obj, mod.__name__)
            elif inspect.isfunction(obj):
                obj_mod = getattr(obj, "__module__", None)
                if obj_mod and not obj_mod.startswith("codegraph"):
                    continue
                # Use the object's own module for FQN to avoid re-export duplicates
                self._extract_function(obj, obj_mod if obj_mod else mod.__name__)

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