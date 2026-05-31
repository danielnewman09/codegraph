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
    """Complete class diagram for a query scope.

    ClassDiagram is the top-level container for all design-layer
    entities within a single query or analysis scope. It aggregates
    classes, interfaces, enums, and their associations into a
    self-contained, serializable document that can be:

    * Serialized for LLM consumption via ``model_dump(tags={"llm"})``
    * Round-tripped to/from Neo4j via :meth:`to_neo4j` /
      :meth:`from_neo4j`
    * Transformed into verification dicts via
      :meth:`to_verification_dicts`
    * Summarized via :meth:`to_summary`

    An internal ``_entity_index`` provides O(1) lookup by
    ``qualified_name`` across all entity types.
    """

    #: List of module/namespace names present in this diagram
    #: (e.g. ``["calc", "io"]``). Populated during deserialization
    #: or Neo4j round-tripping.
    module_names: list[str] = []

    #: All classes (:class:`ClassNode`) in the diagram, including
    #: structs and template classes.
    classes: list[ClassNode] = []

    #: All interfaces (:class:`InterfaceNode`) in the diagram,
    #: including abstract classes that serve as contracts.
    interfaces: list[InterfaceNode] = []

    #: All enums (:class:`EnumNode`) in the diagram, including
    #: both plain enums and C++ scoped enum classes.
    enums: list[EnumNode] = []

    #: All associations (:class:`Association`) between entities
    #: in this diagram. Associations are directed: subject → object.
    associations: list[Association] = []

    #: Internal lookup cache mapping ``qualified_name`` to entity.
    #: Built in :meth:`model_post_init` from all entity lists.
    #: Provides O(1) access via :meth:`get_entity`.
    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode | ModuleNode] = (
        PrivateAttr(default_factory=dict)
    )

    def model_post_init(self, __context) -> None:
        """Build the internal ``_entity_index`` after model initialization.

        Called automatically by Pydantic after ``__init__`` completes.
        Populates a dict mapping ``qualified_name`` → entity for O(1)
        lookups.
        """
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    # -- Query methods --

    def get_entity(self, qualified_name: str) -> ClassNode | InterfaceNode | EnumNode | ModuleNode | None:
        """Look up any entity by its fully-qualified name.

        Args:
            qualified_name: Fully-qualified name of the entity
                (e.g. ``"calc::Calculator"``).

        Returns:
            The matching entity node, or ``None`` if not found.
        """
        return self._entity_index.get(qualified_name)

    def associations_for(self, qualified_name: str) -> list[Association]:
        """Return all associations where the given entity is the subject.

        Args:
            qualified_name: Fully-qualified name of the subject entity.

        Returns:
            List of associations originating from this entity.
        """
        return [a for a in self.associations if a.subject == qualified_name]

    def associations_involving(self, qualified_name: str) -> list[Association]:
        """Return all associations involving the given entity (subject or object).

        Args:
            qualified_name: Fully-qualified name of the entity.

        Returns:
            List of associations where this entity is either the
            subject or the object.
        """
        return [a for a in self.associations if a.subject == qualified_name or a.object == qualified_name]

    def classes_in_module(self, module: str) -> list[ClassNode]:
        """Return all classes belonging to the given module.

        Args:
            module: Module name to filter by (e.g. ``"calc"``).

        Returns:
            List of :class:`ClassNode` instances with matching
            ``module`` field.
        """
        return [c for c in self.classes if c.module == module]

    # -- Serialization --

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize the entire diagram, optionally filtering by field tags.

        Overrides the default Pydantic ``model_dump`` to propagate the
        *tags* filter to all nested entities (classes, interfaces,
        enums, associations). Each child's own ``model_dump(tags=...)``
        is called so that only fields matching the requested tags
        appear in the output.

        Args:
            tags: Set of :class:`FieldTags` tags to filter by
                (e.g. ``{"llm"}``). When ``None``, all fields are
                included unfiltered.
            **kwargs: Forwarded to ``BaseModel.model_dump``
                (e.g. ``exclude_none=True``).

        Returns:
            A nested dict representing the filtered class diagram.
        """
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

    def to_neo4j(self) -> None:
        """Persist the entire diagram to Neo4j via the repository layer.

        Creates neomodel :class:`~codegraph.models.compound.CompoundNode`
        and :class:`~codegraph.models.member.MemberNode` instances,
        saves them, and wires up COMPOSES relationships. Associations
        are persisted as GENERALIZES edges via the repository's
        ``connect_base`` method.

        This replaces the old pattern of returning ``(compounds,
        members, edges)`` lists for the caller to insert manually.
        """
        from codegraph.models.compound import CompoundNode as NeoCompound
        from codegraph.models.member import MemberNode as NeoMember
        from codegraph.repositories.compound import CompoundRepository
        from codegraph.repositories.member import MemberRepository

        compound_repo = CompoundRepository()
        member_repo = MemberRepository()

        for cls in self.classes:
            compound = NeoCompound(
                qualified_name=cls.qualified_name,
                name=cls.name,
                kind=cls.kind,
                layer=cls.layer or "design",
                component_id=cls.component_id,
                brief_description=cls.description,
                file_path=cls.file_path or "",
                line_number=cls.line_number,
                is_final=cls.is_final,
                is_abstract=cls.is_abstract,
            )
            compound_repo.save(compound)

            for attr in cls.attributes:
                member = NeoMember(
                    qualified_name=attr.qualified_name,
                    name=attr.name,
                    kind="variable",
                    layer=attr.layer or "design",
                    component_id=attr.component_id,
                    brief_description=attr.description,
                    type_signature=attr.type_signature or "",
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

            for method in cls.methods:
                member = NeoMember(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer=method.layer or "design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature or "",
                    argsstring=method.argsstring or "",
                    protection=method.visibility or "",
                    is_virtual=method.is_virtual,
                    is_static=method.is_static,
                    is_const=method.is_const,
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        for iface in self.interfaces:
            compound = NeoCompound(
                qualified_name=iface.qualified_name,
                name=iface.name,
                kind=iface.kind,
                layer="design",
                component_id=iface.component_id,
                brief_description=iface.description,
                is_abstract=iface.is_abstract,
            )
            compound_repo.save(compound)

            for method in iface.methods:
                member = NeoMember(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature or "",
                    argsstring=method.argsstring or "",
                    protection=method.visibility or "",
                    is_virtual=True,
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        for enum in self.enums:
            compound = NeoCompound(
                qualified_name=enum.qualified_name,
                name=enum.name,
                kind=enum.kind,
                layer="design",
                component_id=enum.component_id,
                brief_description=enum.description,
            )
            compound_repo.save(compound)

            for val in enum.values:
                member = NeoMember(
                    qualified_name=val.qualified_name,
                    name=val.name,
                    kind="enumvalue",
                    layer="design",
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        # Associations: create relationship edges
        for assoc in self.associations:
            predicate = assoc.predicate.upper()
            if predicate == "GENERALIZES":
                try:
                    compound_repo.connect_base(assoc.subject, assoc.object)
                except Exception:
                    pass  # target may not exist yet

    @classmethod
    def from_neo4j(cls, compounds: list | None = None,
                   members: list | None = None,
                   edges: list | None = None) -> ClassDiagram:
        """Reconstruct a class diagram from Neo4j node/edge lists.

        When called with explicit lists, uses those directly (backward
        compatible). When called with no arguments, reads all
        design-layer entities from Neo4j via the repository layer.

        Args:
            compounds: Optional list of compound node instances.
            members: Optional list of member node instances.
            edges: Optional list of edge instances.

        Returns:
            A fully reconstructed :class:`ClassDiagram`.
        """
        from codegraph.edges import CodebaseEdge  # noqa: F811  # lazy import to avoid circular dependency

        if compounds is None:
            from codegraph.repositories.compound import CompoundRepository
            compounds = CompoundRepository().find_by_layer("design")
        if members is None:
            from codegraph.repositories.member import MemberRepository
            members = MemberRepository().find_by_layer("design")
        if edges is None:
            edges = []

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
        """Convert the diagram into a list of dicts suitable for verification.

        Each dict represents one entity (class or interface) with its
        attributes, methods, and outgoing relationships flattened into
        simple dict structures. Used by the verification pipeline to
        compare design output against as-built source code.

        Returns:
            A list of entity dicts sorted by ``qualified_name``, each
            containing ``qualified_name``, ``kind``, ``description``,
            ``attributes``, ``methods``, and ``relationships`` keys.
            Interfaces have empty ``attributes`` lists.
        """
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
        """Build a flat lookup table of all entities in the diagram.

        Each entry maps ``qualified_name`` to a dict with keys
        ``qualified_name``, ``kind``, ``description``, and
        ``source`` (always ``"draft"``). Includes classes, interfaces,
        enums, attributes, and methods — any entity with a qualified
        name.

        Returns:
            A ``{qualified_name: entity_info}`` dict for all entities
            in the diagram.
        """
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
        """Return a high-level summary of the diagram's contents.

        Returns:
            A dict with counts for ``classes``, ``interfaces``,
            ``enums``, ``associations``, ``attributes``, and
            ``methods``.
        """
        return {"classes": len(self.classes), "interfaces": len(self.interfaces),
                "enums": len(self.enums), "associations": len(self.associations),
                "attributes": sum(len(c.attributes) for c in self.classes),
                "methods": sum(len(c.methods) for c in self.classes)}

    def to_class_lookup(self) -> dict[str, str]:
        """Build a simple name → qualified_name lookup for top-level entities.

        Maps unqualified names (e.g. ``"Calculator"``) to their
        fully-qualified form (e.g. ``"calc::Calculator"``). In case of
        name collisions, later entities in the iteration order
        overwrite earlier ones.

        Returns:
            A ``{name: qualified_name}`` dict for all classes,
            interfaces, and enums in the diagram.
        """
        lookup: dict[str, str] = {}
        for cls in self.classes:
            lookup[cls.name] = cls.qualified_name
        for iface in self.interfaces:
            lookup[iface.name] = iface.qualified_name
        for enum in self.enums:
            lookup[enum.name] = enum.qualified_name
        return lookup


def _extract_parent_qn(qualified_name: str) -> str:
    """Extract the parent qualified name by stripping the last component.

    For example, ``"calc::Calculator::add"`` returns
    ``"calc::Calculator"``. Used to group members under their owning
    compound during Neo4j round-tripping.

    Args:
        qualified_name: A fully-qualified name with ``::`` separators.

    Returns:
        The parent qualified name, or ``""`` if there is no ``::``
        separator (i.e. the name is already at the top level).
    """
    if "::" in qualified_name:
        return qualified_name.rsplit("::", 1)[0]
    return ""


def _extract_module(qualified_name: str) -> str:
    """Extract the module/namespace portion of a qualified name.

    For example, ``"calc::Calculator"`` returns ``"calc"``. Used to
    populate the ``module`` field during Neo4j → design model
    reconstruction.

    Args:
        qualified_name: A fully-qualified name with ``::`` separators.

    Returns:
        The module portion (everything before the last ``::``), or
        ``""`` if there is no ``::`` separator.
    """
    if "::" in qualified_name:
        parts = qualified_name.rsplit("::", 1)
        return parts[0]
    return ""
