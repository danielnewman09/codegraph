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


def _ensure_list(parent, attr_name: str) -> list:
    """Return the list stored at *attr_name* on *parent*, creating it if needed.

    Works with both neomodel relationship descriptors (when connected to Neo4j)
    and plain Python lists (for in-memory / fixture-driven construction).

    For unsaved nodes (no element_id), the neomodel RelationshipManager is
    replaced with a plain Python list so that members can be attached without
    a database connection.

    Args:
        parent: The neomodel node or plain object to access.
        attr_name: The attribute name holding a list or RelationshipManager.

    Returns:
        A list of items stored at that attribute.
    """
    raw = getattr(parent, attr_name, None)
    if raw is None:
        result: list = []
        setattr(parent, attr_name, result)
        return result
    if hasattr(raw, "all"):
        # neomodel RelationshipManager — only query DB if the node is saved
        if parent.element_id is None:
            # Node not yet saved: replace manager with plain list
            result: list = []
            setattr(parent, attr_name, result)
            return result
        result = list(raw.all())
        setattr(parent, attr_name, result)
        return result
    if isinstance(raw, list):
        return raw
    result = []
    setattr(parent, attr_name, result)
    return result


def _is_relationship_property(prop) -> bool:
    """Return True if *prop* is a neomodel relationship descriptor.

    RelationshipTo and RelationshipFrom are NOT subclasses of
    neomodel.properties.Property; they extend RelationshipDefinition.
    This helper distinguishes them from scalar properties.

    Args:
        prop: The attribute to check.

    Returns:
        True if prop is a relationship descriptor, False if it is a scalar
        property.
    """
    from neomodel.properties import Property
    return not isinstance(prop, Property)


@dataclass
class Association:
    """A relationship between two named entities in a ClassDiagram.

    This is the LLM-facing shape — not a neomodel node. The mapper
    and repository translate these into neomodel relationships.

    Attributes:
        subject: Qualified name of the source entity.
        predicate: Relationship type (e.g. "inherits_from", "realizes").
        object: Qualified name of the target entity.
        requirement_ids: Associated requirement IDs.
        mechanism: How the relationship is implemented (e.g. "std::unique_ptr").
        position: Positional order, if applicable.
        name: Short name for the association.
        display_name: Human-readable display name.
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
        """Initialize a ClassDiagram.

        Args:
            module_names: List of module/namespace names in the design.
            classes: List of ClassNode instances.
            interfaces: List of InterfaceNode instances.
            enums: List of EnumNode instances.
            associations: List of Association instances.
        """
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

        Args:
            data: A dict with keys like ``module_names``, ``classes``,
                ``interfaces``, ``enums``, ``associations``.

        Returns:
            A populated ClassDiagram instance.
        """
        def _map_llm_fields(d: dict) -> dict:
            """Map LLM field names to neomodel property names."""
            out = dict(d)
            if "description" in out:
                out.setdefault("brief_description", out.pop("description"))
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

        Returns:
            A JSON Schema dict describing the ClassDiagram tool input shape.
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
        """Build a ClassDiagram from all design entities in a given layer.

        Args:
            layer: The layer to query (e.g. ``"design"``).

        Returns:
            A ClassDiagram populated with classes, interfaces, and enums
            from the specified layer.
        """
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
        """Look up any entity by fully-qualified name. O(1).

        Args:
            qualified_name: The fully-qualified name of the entity.

        Returns:
            The matching entity, or None if not found.
        """
        return self._entity_index.get(qualified_name)

    def classes_in_module(self, module: str) -> list[ClassNode]:
        """Return all classes belonging to the given module.

        Args:
            module: The module/namespace name to filter by.

        Returns:
            A list of ClassNode instances in that module.
        """
        return [c for c in self.classes if c.module == module]

    # -- Transformations --

    def to_summary(self) -> dict:
        """Return a high-level summary of the diagram's contents.

        Returns:
            A dict with counts of classes, interfaces, enums, attributes,
            methods, and associations.
        """
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
        """Convert the diagram into a list of dicts suitable for verification.

        Returns:
            A list of dicts, each representing a class or interface with
            its attributes, methods, and relationships.
        """
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
                        "visibility": a.visibility or "",
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
                        "visibility": m.visibility or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in meth_list
                ]
            results.append({
                "qualified_name": cls_node.qualified_name,
                "kind": cls_node.kind,
                "visibility": cls_node.visibility or "",
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
                        "visibility": m.visibility or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in meth_list
                ]
            results.append({
                "qualified_name": iface_node.qualified_name,
                "kind": iface_node.kind,
                "visibility": iface_node.visibility or "",
                "description": iface_node.brief_description or "",
                "attributes": [],
                "methods": sorted(meths, key=lambda x: x["name"]),
                "relationships": [],
            })

        return sorted(results, key=lambda x: x["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        """Build a flat lookup table of all entities in the diagram.

        Returns:
            A dict mapping qualified names to entity summary dicts.
        """
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
        """Build a simple name to qualified_name lookup.

        Returns:
            A dict mapping short names to fully-qualified names.
        """
        lookup: dict[str, str] = {}
        for cls_node in self.classes:
            lookup[cls_node.name] = cls_node.qualified_name
        for iface_node in self.interfaces:
            lookup[iface_node.name] = iface_node.qualified_name
        for enum_node in self.enums:
            lookup[enum_node.name] = enum_node.qualified_name
        return lookup

    # -- Graph serialization (round-trip JSON) --

    def to_graph_dict(self) -> dict[str, list[dict]]:
        """Serialize the complete diagram to a graph dict with nodes and edges.

        Returns ``{"nodes": [...], "edges": [...]}`` where each node is a
        flat dict of properties and each edge has ``source``, ``target``, and
        ``predicate`` keys.

        Member nodes (methods, attributes, enum values) attached via COMPOSES
        are included, as well as module-to-compound COMPOSES, inter-compound
        associations, and INHERITS_FROM / REALIZES / DEPENDS_ON / AGGREGATES
        edges.

        Returns:
            A dict with ``nodes`` and ``edges`` lists.
        """
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qnames: set[str] = set()

        def _add_node(model) -> None:
            # Emit only scalar neomodel properties. Relationship descriptors
            # (RelationshipTo, RelationshipFrom) are excluded — those are
            # handled separately as edges in the graph output.
            valid_keys = {
                k for k, prop in model.defined_properties().items()
                if not _is_relationship_property(prop)
            }
            d = {k: v for k, v in dict(model.__properties__).items() if k in valid_keys}
            qn = d.get("qualified_name", "")
            if qn and qn not in seen_qnames:
                seen_qnames.add(qn)
                nodes.append(d)

        def _add_edge(source: str, target: str, predicate: str) -> None:
            edges.append({"source": source, "target": target, "predicate": predicate})

        def _get_member_list(parent, attr_name: str) -> list:
            """Return members from *parent* using the module-level _ensure_list."""
            return _ensure_list(parent, attr_name)

        def _walk_compound(compound, *, emit_module_edge: bool = True) -> None:
            _add_node(compound)
            if emit_module_edge and compound.module:
                _add_edge(compound.module, compound.qualified_name, "COMPOSES")
            for m in _get_member_list(compound, "methods"):
                _add_node(m)
                _add_edge(compound.qualified_name, m.qualified_name, "COMPOSES")
            for a in _get_member_list(compound, "attributes"):
                _add_node(a)
                _add_edge(compound.qualified_name, a.qualified_name, "COMPOSES")
            for v in _get_member_list(compound, "values"):
                _add_node(v)
                _add_edge(compound.qualified_name, v.qualified_name, "COMPOSES")

        for cls_node in self.classes:
            _walk_compound(cls_node)
        for iface_node in self.interfaces:
            _walk_compound(iface_node)
        for enum_node in self.enums:
            _walk_compound(enum_node)

        # Module nodes
        for mod_name in self.module_names:
            qn = mod_name
            if qn not in seen_qnames:
                seen_qnames.add(qn)
                nodes.append({
                    "qualified_name": mod_name,
                    "name": mod_name,
                    "kind": "module",
                    "layer": "design",
                    "brief_description": "",
                    "visibility": "",
                })

        # Associations → edges
        for assoc in self.associations:
            _add_edge(assoc.subject, assoc.object, assoc.predicate)

        return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_graph_dict(cls, data: dict[str, Any]) -> "ClassDiagram":
        """Build a ClassDiagram from a graph dict with nodes and edges.

        Accepts ``{"nodes": [...], "edges": [...]}``. Each node must have
        at least ``qualified_name`` and ``kind``. Edges have ``source``,
        ``target``, and ``predicate``.

        COMPOSES edges where the target is a member node (method, attribute,
        enumvalue) result in the member being attached to its parent compound
        via a plain Python list stored on the parent. Other edges become
        ``Association`` objects.

        Args:
            data: A graph dict with ``nodes`` and ``edges`` lists.

        Returns:
            A ClassDiagram with nodes reconstructed and members attached.
        """
        from codegraph.models.compound import ModuleNode
        from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode

        nodes_by_qname: dict[str, Any] = {}
        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        seen_modules: set[str] = set()

        # Phase 1: create all nodes from the flat node list
        for node_data in data.get("nodes", []):
            kind = node_data.get("kind", "")
            qname = node_data.get("qualified_name", "")
            if not qname:
                continue
            # Extract only properties known to the target node type
            node_props = dict(node_data)
            node_props.pop("kind", None)  # kind is set via defaults on the class

            if kind == "class":
                c = ClassNode(**node_props)
                classes.append(c)
                nodes_by_qname[qname] = c
            elif kind == "interface":
                i = InterfaceNode(**node_props)
                interfaces.append(i)
                nodes_by_qname[qname] = i
            elif kind == "enum":
                e = EnumNode(**node_props)
                enums.append(e)
                nodes_by_qname[qname] = e
            elif kind == "module":
                m = ModuleNode(**node_props)
                seen_modules.add(m.name)
                nodes_by_qname[qname] = m
            elif kind == "method":
                m = MethodNode(**node_props)
                nodes_by_qname[qname] = m
            elif kind == "attribute":
                a = AttributeNode(**node_props)
                nodes_by_qname[qname] = a
            elif kind == "enumvalue":
                ev = EnumValueNode(**node_props)
                nodes_by_qname[qname] = ev

        # Phase 2: process edges — attach members to parents, create associations
        associations: list[Association] = []

        for edge in data.get("edges", []):
            src_qname = edge.get("source", "")
            tgt_qname = edge.get("target", "")
            predicate = edge.get("predicate", "")

            src_node = nodes_by_qname.get(src_qname)
            tgt_node = nodes_by_qname.get(tgt_qname)

            if predicate == "COMPOSES" and src_node is not None and tgt_node is not None:
                # Attach member to parent compound/module
                if isinstance(tgt_node, MethodNode):
                    _ensure_list(src_node, "methods").append(tgt_node)
                elif isinstance(tgt_node, AttributeNode):
                    _ensure_list(src_node, "attributes").append(tgt_node)
                elif isinstance(tgt_node, EnumValueNode):
                    _ensure_list(src_node, "values").append(tgt_node)
                # Module→compound COMPOSES: the module field on compound
                # already captures this; no extra storage needed.
            else:
                # Non-COMPOSES edge → Association
                associations.append(Association(
                    subject=src_qname,
                    predicate=predicate,
                    object=tgt_qname,
                ))

        # Derive module_names from module nodes plus compound module fields
        module_names = sorted(seen_modules)
        for node in (*classes, *interfaces, *enums):
            mod = getattr(node, "module", "")
            if mod and mod not in seen_modules:
                seen_modules.add(mod)
                module_names.append(mod)

        return cls(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
            associations=associations,
        )
