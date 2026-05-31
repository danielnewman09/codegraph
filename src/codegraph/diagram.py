"""ClassDiagram — typed snapshot container for a scoped design graph.

Reads atomized neomodel nodes from Neo4j for a given layer and presents
them as typed lists with O(1) entity lookup.

Provides ``model_validate`` and ``model_json_schema`` classmethods
for LLM tool-loop compatibility — the LLM outputs flat dicts that
are validated here; neomodel node construction happens in the mapper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode


@dataclass
class Association:
    """A relationship between two named entities in a ClassDiagram.

    This is the LLM-facing shape — not a neomodel node. The mapper
    and repository translate these into neomodel relationships.
    """

    subject: str
    predicate: str
    object: str
    requirement_ids: list[str] = field(default_factory=list)
    mechanism: str = ""
    position: int | None = None
    name: str = ""
    display_name: str = ""


class ClassDiagram:
    """Complete class diagram for a query scope.

    Holds typed lists of neomodel node instances. No persistence —
    nodes handle their own ``.save()``.

    Provides ``model_validate()`` and ``model_json_schema()`` for
    LLM tool-loop compatibility.
    """

    def __init__(
        self,
        module_names: list[str] | None = None,
        classes: list[ClassNode] | None = None,
        interfaces: list[InterfaceNode] | None = None,
        enums: list[EnumNode] | None = None,
        associations: list[Association] | None = None,
    ):
        self.module_names: list[str] = module_names or []
        self.classes: list[ClassNode] = classes or []
        self.interfaces: list[InterfaceNode] = interfaces or []
        self.enums: list[EnumNode] = enums or []
        self.associations: list[Association] = associations or []
        self._entity_index: dict[str, ClassNode | InterfaceNode | EnumNode] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    # -- Classmethods for LLM tool-loop compatibility --

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "ClassDiagram":
        """Validate a dict produced by the LLM into a ClassDiagram.

        The LLM produces flat dicts with simple fields. Neomodel node
        construction happens here — LLM field names are mapped to
        neomodel property names.
        """
        def _map_llm_fields(d: dict) -> dict:
            """Map LLM field names to neomodel property names."""
            out = dict(d)
            if "description" in out:
                out.setdefault("brief_description", out.pop("description"))
            if "visibility" in out:
                out.setdefault("protection", out.pop("visibility"))
            if "inherits_from" in out:
                out.setdefault("base_classes", out.pop("inherits_from"))
            # Map realizes_interfaces to realizes (LLM may use either name)
            if "realizes_interfaces" in out:
                out.setdefault("realizes", out.pop("realizes_interfaces"))
            # Drop ticketing-specific fields not on atomized types
            out.pop("is_intercomponent", None)
            out.pop("specialization", None)
            out.pop("requirement_ids", None)
            return out
        def _to_assoc(a: dict) -> Association:
            return Association(
                subject=a.get("subject", ""),
                predicate=a.get("predicate", ""),
                object=a.get("object", ""),
                requirement_ids=a.get("requirement_ids", []),
                mechanism=a.get("mechanism", ""),
                position=a.get("position"),
                name=a.get("name", ""),
                display_name=a.get("display_name", ""),
            )

        return cls(
            module_names=data.get("module_names", []),
            classes=[ClassNode(**_map_llm_fields(c)) for c in data.get("classes", [])],
            interfaces=[InterfaceNode(**_map_llm_fields(i)) for i in data.get("interfaces", [])],
            enums=[EnumNode(**_map_llm_fields(e)) for e in data.get("enums", [])],
            associations=[_to_assoc(a) for a in data.get("associations", [])],
        )

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        """Return the JSON schema for LLM tool definitions.

        Describes the shape expected from the LLM — flat dicts with
        simple field types, not the neomodel node structure.
        """
        return {
            "type": "object",
            "properties": {
                "module_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Module/namespace names used in the design",
                },
                "classes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "module": {"type": "string"},
                            "brief_description": {"type": "string"},
                            "kind": {"type": "string"},
                            "requirement_ids": {"type": "array", "items": {"type": "string"}},
                            "inherits_from": {"type": "array", "items": {"type": "string"}},
                            "realizes": {"type": "array", "items": {"type": "string"}},
                            "is_intercomponent": {"type": "boolean"},
                            "specialization": {"type": "string"},
                            "attributes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "visibility": {"type": "string"},
                                        "type_signature": {"type": "string"},
                                        "brief_description": {"type": "string"},
                                    },
                                },
                            },
                            "methods": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "visibility": {"type": "string"},
                                        "type_signature": {"type": "string"},
                                        "argsstring": {"type": "string"},
                                        "brief_description": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "interfaces": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "module": {"type": "string"},
                            "brief_description": {"type": "string"},
                            "requirement_ids": {"type": "array", "items": {"type": "string"}},
                            "is_intercomponent": {"type": "boolean"},
                            "specialization": {"type": "string"},
                            "inherits_from": {"type": "array", "items": {"type": "string"}},
                            "methods": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "visibility": {"type": "string"},
                                        "type_signature": {"type": "string"},
                                        "argsstring": {"type": "string"},
                                        "brief_description": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "enums": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "module": {"type": "string"},
                            "brief_description": {"type": "string"},
                            "requirement_ids": {"type": "array", "items": {"type": "string"}},
                            "values": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "associations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "object": {"type": "string"},
                            "mechanism": {"type": "string"},
                            "requirement_ids": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        }

    # -- Factory --

    @classmethod
    def from_layer(cls, layer: str) -> "ClassDiagram":
        """Build a ClassDiagram from all design entities in a given layer."""
        classes = list(ClassNode.nodes.filter(layer=layer))
        interfaces = list(InterfaceNode.nodes.filter(layer=layer))
        enums = list(EnumNode.nodes.filter(layer=layer))

        seen_modules: set[str] = set()
        module_names: list[str] = []

        for node in (*classes, *interfaces, *enums):
            if "::" in node.qualified_name:
                module = node.qualified_name.rsplit("::", 1)[0]
                if module and module not in seen_modules:
                    seen_modules.add(module)
                    module_names.append(module)

        return cls(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
        )

    # -- Query --

    def get_entity(self, qualified_name: str) -> ClassNode | InterfaceNode | EnumNode | None:
        """Look up any entity by fully-qualified name. O(1)."""
        return self._entity_index.get(qualified_name)

    def classes_in_module(self, module: str) -> list[ClassNode]:
        """Return all classes belonging to the given module."""
        return [c for c in self.classes if c.module == module]

    # -- Transformations --

    def to_summary(self) -> dict:
        """Return a high-level summary of the diagram's contents."""
        attributes_count = 0
        methods_count = 0
        for c in self.classes:
            if c.element_id and hasattr(c, 'attributes'):
                attributes_count += len(c.attributes.all())
            elif hasattr(c, 'attributes') and isinstance(c.attributes, list):
                attributes_count += len(c.attributes)
            if c.element_id and hasattr(c, 'methods'):
                methods_count += len(c.methods.all())
            elif hasattr(c, 'methods') and isinstance(c.methods, list):
                methods_count += len(c.methods)

        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "attributes": attributes_count,
            "methods": methods_count,
            "associations": len(self.associations),
        }

    def to_verification_dicts(self) -> list[dict]:
        """Convert the diagram into a list of dicts suitable for verification."""
        results = []

        for cls_node in self.classes:
            attrs = []
            raw_attrs = getattr(cls_node, 'attributes', None)
            if raw_attrs is not None:
                # Handle both neomodel manager and plain list
                attr_list = raw_attrs.all() if hasattr(raw_attrs, 'all') else raw_attrs
                attrs = [
                    {
                        "name": a.name,
                        "qualified_name": a.qualified_name,
                        "kind": "attribute",
                        "visibility": a.protection or "",
                        "type_signature": a.type_signature or "",
                        "description": a.brief_description or "",
                    }
                    for a in attr_list
                ]
            meths = []
            raw_meths = getattr(cls_node, 'methods', None)
            if raw_meths is not None:
                # Handle both neomodel manager and plain list
                meth_list = raw_meths.all() if hasattr(raw_meths, 'all') else raw_meths
                meths = [
                    {
                        "name": m.name,
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "visibility": m.protection or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in meth_list
                ]
            results.append({
                "qualified_name": cls_node.qualified_name,
                "kind": cls_node.kind,
                "description": cls_node.brief_description or "",
                "attributes": sorted(attrs, key=lambda x: x["name"]),
                "methods": sorted(meths, key=lambda x: x["name"]),
                "relationships": [],
            })

        for iface_node in self.interfaces:
            meths = []
            raw_meths = getattr(iface_node, 'methods', None)
            if raw_meths is not None:
                meth_list = raw_meths.all() if hasattr(raw_meths, 'all') else raw_meths
                meths = [
                    {
                        "name": m.name,
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "visibility": m.protection or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in meth_list
                ]
            results.append({
                "qualified_name": iface_node.qualified_name,
                "kind": iface_node.kind,
                "description": iface_node.brief_description or "",
                "attributes": [],
                "methods": sorted(meths, key=lambda x: x["name"]),
                "relationships": [],
            })

        return sorted(results, key=lambda x: x["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        """Build a flat lookup table of all entities in the diagram."""
        lookup: dict[str, dict] = {}
        for cls_node in self.classes:
            lookup[cls_node.qualified_name] = {
                "qualified_name": cls_node.qualified_name,
                "kind": "class",
                "description": cls_node.brief_description or "",
                "source": "draft",
            }
            if hasattr(cls_node, 'attributes'):
                raw_attrs = getattr(cls_node, 'attributes', None)
                if raw_attrs is not None:
                    attr_list = raw_attrs.all() if hasattr(raw_attrs, 'all') else raw_attrs
                    for a in attr_list:
                        lookup[a.qualified_name] = {
                            "qualified_name": a.qualified_name,
                            "kind": "attribute",
                            "description": a.brief_description or "",
                            "source": "draft",
                        }
            if hasattr(cls_node, 'methods'):
                raw_meths = getattr(cls_node, 'methods', None)
                if raw_meths is not None:
                    meth_list = raw_meths.all() if hasattr(raw_meths, 'all') else raw_meths
                    for m in meth_list:
                        lookup[m.qualified_name] = {
                            "qualified_name": m.qualified_name,
                            "kind": "method",
                            "description": m.brief_description or "",
                            "source": "draft",
                        }
        for iface_node in self.interfaces:
            lookup[iface_node.qualified_name] = {
                "qualified_name": iface_node.qualified_name,
                "kind": "interface",
                "description": iface_node.brief_description or "",
                "source": "draft",
            }
            if hasattr(iface_node, 'methods'):
                raw_meths = getattr(iface_node, 'methods', None)
                if raw_meths is not None:
                    meth_list = raw_meths.all() if hasattr(raw_meths, 'all') else raw_meths
                    for m in meth_list:
                        lookup[m.qualified_name] = {
                            "qualified_name": m.qualified_name,
                            "kind": "method",
                            "description": m.brief_description or "",
                            "source": "draft",
                        }
        for enum_node in self.enums:
            lookup[enum_node.qualified_name] = {
                "qualified_name": enum_node.qualified_name,
                "kind": "enum",
                "description": enum_node.brief_description or "",
                "source": "draft",
            }
        return lookup

    def to_class_lookup(self) -> dict[str, str]:
        """Build a simple name → qualified_name lookup."""
        lookup: dict[str, str] = {}
        for cls_node in self.classes:
            lookup[cls_node.name] = cls_node.qualified_name
        for iface_node in self.interfaces:
            lookup[iface_node.name] = iface_node.qualified_name
        for enum_node in self.enums:
            lookup[enum_node.name] = enum_node.qualified_name
        return lookup
