"""ClassDiagram — typed snapshot container for a scoped design graph.

Reads atomized neomodel nodes from Neo4j for a given layer and presents
them as typed lists with O(1) entity lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class ClassDiagram:
    """Complete class diagram for a query scope.

    A lightweight dataclass container that holds typed lists of neomodel
    node instances. No persistence — nodes handle their own ``.save()``.
    """

    module_names: list[str] = field(default_factory=list)
    classes: list[ClassNode] = field(default_factory=list)
    interfaces: list[InterfaceNode] = field(default_factory=list)
    enums: list[EnumNode] = field(default_factory=list)
    associations: list[Association] = field(default_factory=list)

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode] = field(
        default_factory=dict, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

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
            if c.element_id and hasattr(c, 'methods'):
                methods_count += len(c.methods.all())

        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "attributes": attributes_count,
            "methods": methods_count,
        }

    def to_verification_dicts(self) -> list[dict]:
        """Convert the diagram into a list of dicts suitable for verification."""
        results = []

        for cls_node in self.classes:
            attrs = []
            if hasattr(cls_node, 'attributes'):
                attrs = [
                    {
                        "name": a.name,
                        "qualified_name": a.qualified_name,
                        "kind": "attribute",
                        "visibility": a.protection or "",
                        "type_signature": a.type_signature or "",
                        "description": a.brief_description or "",
                    }
                    for a in cls_node.attributes.all()
                ]
            meths = []
            if hasattr(cls_node, 'methods'):
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
                    for m in cls_node.methods.all()
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
            if hasattr(iface_node, 'methods'):
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
                    for m in iface_node.methods.all()
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
                for a in cls_node.attributes.all():
                    lookup[a.qualified_name] = {
                        "qualified_name": a.qualified_name,
                        "kind": "attribute",
                        "description": a.brief_description or "",
                        "source": "draft",
                    }
            if hasattr(cls_node, 'methods'):
                for m in cls_node.methods.all():
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
                for m in iface_node.methods.all():
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
