"""Canonical OO design models for the codebase graph.

ClassDiagram is the single OO design representation. It handles:
  - LLM serialization (via model_dump(tags={"llm"}))
  - Neo4j round-tripping (to_neo4j / from_neo4j)
  - Query and transformation methods
"""

from __future__ import annotations

from pydantic import BaseModel, PrivateAttr

from codegraph.designs.compound import (
    ClassNode, DiagramNode, EnumNode, InterfaceNode,
)
from codegraph.designs.edges import Association
from codegraph.designs.member import (
    AttributeNode, EnumValueNode, MethodNode, _tagged_model_dump,
)
from codegraph.designs.namespace import ModuleNode
from codegraph.designs.tags import FieldTags, get_fields_by_tags
from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode
from codegraph.edges import CodebaseEdge

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "FieldTags",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
]


class ClassDiagram(BaseModel):
    """Complete class diagram for a query scope."""

    module_names: list[str] = []
    classes: list[ClassNode] = []
    interfaces: list[InterfaceNode] = []
    enums: list[EnumNode] = []
    associations: list[Association] = []

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode | ModuleNode] = (
        PrivateAttr(default_factory=dict)
    )

    def model_post_init(self, __context) -> None:
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    # -- Query methods --

    def get_entity(self, qualified_name: str) -> ClassNode | InterfaceNode | EnumNode | ModuleNode | None:
        return self._entity_index.get(qualified_name)

    def associations_for(self, qualified_name: str) -> list[Association]:
        return [a for a in self.associations if a.subject == qualified_name]

    def associations_involving(self, qualified_name: str) -> list[Association]:
        return [a for a in self.associations if a.subject == qualified_name or a.object == qualified_name]

    def classes_in_module(self, module: str) -> list[ClassNode]:
        return [c for c in self.classes if c.module == module]

    # -- Serialization --

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = super().model_dump(**kwargs)

        if "classes" in data:
            data["classes"] = [c.model_dump(tags=tags, **kwargs) for c in self.classes]
        if "interfaces" in data:
            data["interfaces"] = [i.model_dump(tags=tags, **kwargs) for i in self.interfaces]
        if "enums" in data:
            data["enums"] = [e.model_dump(tags=tags, **kwargs) for e in self.enums]
        if "associations" in data:
            data["associations"] = [a.model_dump(tags=tags, **kwargs) for a in self.associations]
        return data

    # -- Neo4j round-trip --

    def to_neo4j(self) -> tuple[list[CompoundNode], list[MemberNode], list[CodebaseEdge]]:
        compounds: list[CompoundNode] = []
        members: list[MemberNode] = []

        for cls in self.classes:
            compound = CompoundNode(
                qualified_name=cls.qualified_name,
                name=cls.name,
                kind=cls.kind,  # type: ignore[arg-type]
                layer=cls.layer or "design",  # type: ignore[arg-type]
                component_id=cls.component_id,
                brief_description=cls.description,
                file_path=cls.file_path,
                line_number=cls.line_number,
                is_final=cls.is_final,
                is_abstract=cls.is_abstract,
            )
            compounds.append(compound)
            for attr in cls.attributes:
                members.append(MemberNode(
                    qualified_name=attr.qualified_name, name=attr.name,
                    kind="variable", layer="design",
                    component_id=attr.component_id,
                    brief_description=attr.description,
                    type_signature=attr.type_signature,
                ))
            for method in cls.methods:
                members.append(MemberNode(
                    qualified_name=method.qualified_name, name=method.name,
                    kind="method", layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature,
                    argsstring=method.argsstring,
                    protection=method.visibility or "",  # type: ignore[arg-type]
                    is_virtual=method.is_virtual,
                    is_static=method.is_static,
                    is_const=method.is_const,
                ))

        for iface in self.interfaces:
            compound = CompoundNode(
                qualified_name=iface.qualified_name, name=iface.name,
                kind=iface.kind, layer="design",  # type: ignore[arg-type]
                component_id=iface.component_id,
                brief_description=iface.description,
                is_abstract=iface.is_abstract,
            )
            compounds.append(compound)
            for method in iface.methods:
                members.append(MemberNode(
                    qualified_name=method.qualified_name, name=method.name,
                    kind="method", layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature,
                    argsstring=method.argsstring,
                    protection=method.visibility or "", is_virtual=True,  # type: ignore[arg-type]
                ))

        for enum in self.enums:
            compound = CompoundNode(
                qualified_name=enum.qualified_name, name=enum.name,
                kind=enum.kind, layer="design",  # type: ignore[arg-type]
                component_id=enum.component_id,
                brief_description=enum.description,
            )
            compounds.append(compound)
            for val in enum.values:
                members.append(MemberNode(
                    qualified_name=val.qualified_name, name=val.name,
                    kind="enumvalue", layer="design",
                ))

        edges: list[CodebaseEdge] = []
        for assoc in self.associations:
            edges.append(CodebaseEdge(
                subject_qualified_name=assoc.subject,
                predicate=assoc.predicate,
                object_qualified_name=assoc.object,
                mechanism=assoc.mechanism,
                description=assoc.description,
            ))
        return compounds, members, edges

    @classmethod
    def from_neo4j(cls, compounds: list[CompoundNode], members: list[MemberNode],
                   edges: list[CodebaseEdge]) -> ClassDiagram:
        _CLASS_KINDS = {"class", "struct", "template_class"}
        _INTERFACE_KINDS = {"interface", "abstract_class"}
        _ENUM_KINDS = {"enum", "enum_class"}

        member_index: dict[str, list[MemberNode]] = {}
        for m in members:
            parent = _extract_parent_qn(m.qualified_name)
            member_index.setdefault(parent, []).append(m)

        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        module_names: list[str] = []

        for c in compounds:
            owned = member_index.get(c.qualified_name, [])
            module = _extract_module(c.qualified_name)

            if c.kind in _CLASS_KINDS:
                attrs = []; meths = []
                for m in owned:
                    if m.kind == "variable":
                        attrs.append(AttributeNode(name=m.name, qualified_name=m.qualified_name,
                            kind="attribute", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            owner=c.qualified_name, component_id=m.component_id, layer=m.layer))
                    elif m.kind == "method":
                        meths.append(MethodNode(name=m.name, qualified_name=m.qualified_name,
                            kind="method", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            argsstring=m.argsstring or "", owner=c.qualified_name,
                            component_id=m.component_id, layer=m.layer,
                            is_virtual=m.is_virtual, is_static=m.is_static, is_const=m.is_const))
                classes.append(ClassNode(name=c.name, qualified_name=c.qualified_name,
                    kind="class", layer=c.layer, description=c.brief_description,
                    module=module, component_id=c.component_id, file_path=c.file_path,
                    line_number=c.line_number, is_abstract=c.is_abstract, is_final=c.is_final,
                    attributes=attrs, methods=meths))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _INTERFACE_KINDS:
                meths = []
                for m in owned:
                    if m.kind == "method":
                        meths.append(MethodNode(name=m.name, qualified_name=m.qualified_name,
                            kind="method", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            argsstring=m.argsstring or "", owner=c.qualified_name,
                            component_id=m.component_id, layer=m.layer, is_virtual=True))
                interfaces.append(InterfaceNode(name=c.name, qualified_name=c.qualified_name,
                    kind="interface", layer=c.layer, description=c.brief_description,
                    is_abstract=c.is_abstract, module=module, component_id=c.component_id,
                    methods=meths))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _ENUM_KINDS:
                vals = []
                for m in owned:
                    if m.kind == "enumvalue":
                        vals.append(EnumValueNode(name=m.name, qualified_name=m.qualified_name,
                            kind="enum_value", owner=c.qualified_name))
                enums.append(EnumNode(name=c.name, qualified_name=c.qualified_name,
                    kind="enum", layer=c.layer, description=c.brief_description,
                    module=module, component_id=c.component_id, values=vals))
                if module and module not in module_names:
                    module_names.append(module)

        associations = [
            Association(subject=e.subject_qualified_name, predicate=e.predicate,
                        object=e.object_qualified_name, mechanism=e.mechanism,
                        description=e.description)
            for e in edges
        ]
        return cls(module_names=module_names, classes=classes, interfaces=interfaces,
                   enums=enums, associations=associations)

    # -- Transformation methods --

    def to_verification_dicts(self) -> list[dict]:
        results = []
        for cls in self.classes:
            attrs = [{"name": a.name, "qualified_name": a.qualified_name, "kind": "attribute",
                       "visibility": a.visibility, "type_signature": a.type_signature,
                       "description": a.description} for a in cls.attributes]
            meths = [{"name": m.name, "qualified_name": m.qualified_name, "kind": "method",
                       "visibility": m.visibility, "type_signature": m.type_signature,
                       "argsstring": m.argsstring, "description": m.description} for m in cls.methods]
            rels = [{"predicate": a.predicate, "target": a.object,
                      "target_name": a.object.rsplit("::", 1)[-1]}
                    for a in self.associations if a.subject == cls.qualified_name]
            results.append({"qualified_name": cls.qualified_name,
                            "kind": cls.specialization or cls.kind,
                            "description": cls.description,
                            "attributes": sorted(attrs, key=lambda x: x["name"]),
                            "methods": sorted(meths, key=lambda x: x["name"]),
                            "relationships": rels})
        for iface in self.interfaces:
            meths = [{"name": m.name, "qualified_name": m.qualified_name, "kind": "method",
                       "visibility": m.visibility, "type_signature": m.type_signature,
                       "argsstring": m.argsstring, "description": m.description} for m in iface.methods]
            results.append({"qualified_name": iface.qualified_name, "kind": iface.kind,
                            "description": iface.description, "attributes": [],
                            "methods": sorted(meths, key=lambda x: x["name"]),
                            "relationships": []})
        return sorted(results, key=lambda c: c["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        for cls in self.classes:
            lookup[cls.qualified_name] = {"qualified_name": cls.qualified_name,
                "kind": "class", "description": cls.description, "source": "draft"}
            for attr in cls.attributes:
                lookup[attr.qualified_name] = {"qualified_name": attr.qualified_name,
                    "kind": "attribute", "description": attr.description, "source": "draft"}
            for m in cls.methods:
                lookup[m.qualified_name] = {"qualified_name": m.qualified_name,
                    "kind": "method", "description": m.description, "source": "draft"}
        for iface in self.interfaces:
            lookup[iface.qualified_name] = {"qualified_name": iface.qualified_name,
                "kind": "interface", "description": iface.description, "source": "draft"}
            for m in iface.methods:
                lookup[m.qualified_name] = {"qualified_name": m.qualified_name,
                    "kind": "method", "description": m.description, "source": "draft"}
        for enum in self.enums:
            lookup[enum.qualified_name] = {"qualified_name": enum.qualified_name,
                "kind": "enum", "description": enum.description, "source": "draft"}
        return lookup

    def to_summary(self) -> dict:
        return {"classes": len(self.classes), "interfaces": len(self.interfaces),
                "enums": len(self.enums), "associations": len(self.associations),
                "attributes": sum(len(c.attributes) for c in self.classes),
                "methods": sum(len(c.methods) for c in self.classes)}

    def to_class_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for cls in self.classes:
            lookup[cls.name] = cls.qualified_name
        for iface in self.interfaces:
            lookup[iface.name] = iface.qualified_name
        for enum in self.enums:
            lookup[enum.name] = enum.qualified_name
        return lookup


def _extract_parent_qn(qualified_name: str) -> str:
    if "::" in qualified_name:
        return qualified_name.rsplit("::", 1)[0]
    return ""


def _extract_module(qualified_name: str) -> str:
    if "::" in qualified_name:
        parts = qualified_name.rsplit("::", 1)
        return parts[0]
    return ""
