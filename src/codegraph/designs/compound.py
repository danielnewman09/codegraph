"""Compound-level design models — DiagramNode, ClassNode, InterfaceNode, EnumNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.member import (
    AttributeNode, MethodNode, EnumValueNode, _tagged_model_dump,
)
from codegraph.designs.tags import FieldTags


class DiagramNode(BaseModel):
    """Common fields for every diagram node.

    DiagramNode is the base class for all entity-level design models
    (:class:`ClassNode`, :class:`InterfaceNode`, :class:`EnumNode`,
    :class:`ModuleNode`). Its fields track provenance (layer, source,
    component_id), structural metadata (kind, visibility, file location),
    and ticketing-system extensions (requirement_ids, implementation_status).

    Fields are annotated with :class:`FieldTags` to control which use
    cases see them —``"llm"`` for serialization to LLMs, ``"neo4j"`` for
    graph round-tripping, ``"read"`` for internal consumers, and
    ``"ticketing"`` for external ticketing integrations.
    """

    #: Short, unqualified name (e.g. ``"Calculator"``). Defaults to
    #: ``""`` when only the qualified form is known.
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name (e.g. ``"calc::Calculator"``). Used as the
    #: primary identity key across all layers. Required for Neo4j uniqueness.
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category of the node. Set by subclasses (e.g. ``"class"``,
    #: ``"interface"``, ``"enum"``, ``"module"``).
    kind: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: One-line summary description of this entity. Typically extracted
    #: from the first sentence of a doc comment or provided by an agent
    #: during design. Visible to LLMs for context-aware reasoning.
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Access specifier / visibility level. One of ``"public"``,
    #: ``"private"``, ``"protected"``, or ``""`` (unknown / default).
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Provenance layer — where this node came from.
    #:
    #: * ``"design"`` — agent-created / planned
    #: * ``"as-built"`` — parsed from real source code
    #: * ``"dependency"`` — external library / third-party
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    #: Foreign key to the owning ticketing-system component. Set by
    #: external consumers such as the ticketing agent. ``None`` when
    #: not yet assigned.
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Return type or declared type (e.g. ``"int"``, ``"void"``,
    #: ``"std::string"``). For methods this is the return type; for
    #: attributes it is the declared type.
    type_signature: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Argument string including parentheses (e.g. ``"(int a, int b)"``).
    #: Empty for non-function entities.
    argsstring: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Full definition string (e.g.
    #: ``"int Calculator::add(int a, int b)"``). Used for display and
    #: signature matching.
    definition: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Classification of the source type (e.g. ``"header"``,
    #: ``"source"``, ``"generated"``). Used to distinguish declarations
    #: from definitions.
    source_type: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``). Useful for filtering and auditing.
    source: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Filesystem path to the primary source file declaring this entity
    #: (e.g. ``"/src/calculator.h"``).
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: One-based line number where this entity is declared in
    #: ``file_path``. ``None`` when unknown.
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: ``True`` if the entity is declared ``static`` (C++ class-level
    #: method or variable, or file-level function). Binds the member to
    #: the type rather than an instance.
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the entity is ``const``-qualified (C++). Indicates
    #: the member does not mutate instance state.
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the method is declared ``virtual`` (C++). Allows
    #: derived classes to override the implementation.
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the class/struct has pure virtual methods (C++),
    #: making it abstract. Abstract types cannot be instantiated directly.
    is_abstract: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the class/struct is declared ``final`` (C++). Final
    #: types cannot be inherited from.
    is_final: Annotated[bool, FieldTags("neo4j", "read")] = False

    # -- Ticketing extensions --

    #: Specialization label (e.g. ``"interface"``, ``"utility"``,
    #: ``"data-transfer"``). Used by ticketing agents to classify the
    #: role of this entity within the component's architecture.
    specialization: Annotated[str, FieldTags("ticketing")] = ""

    #: ``True`` if this entity participates in a cross-component
    #: relationship (e.g. dependencies between different subsystems).
    #: Used by ticketing for dependency tracking.
    is_intercomponent: Annotated[bool, FieldTags("ticketing")] = False

    #: Ticketing implementation status. One of ``"designed"``,
    #: ``"in-progress"``, ``"implemented"``, ``"tested"``, or
    #: ``"verified"``. Defaults to ``"designed"`` for new entities.
    implementation_status: Annotated[str, FieldTags("ticketing")] = "designed"

    #: Filesystem path to the test file that exercises this entity
    #: (e.g. ``"/tests/test_calculator.cpp"``). Set by ticketing agents
    #: during test planning.
    test_file: Annotated[str, FieldTags("ticketing")] = ""

    #: Ticketing system requirement IDs associated with this entity.
    #: Each entry is a tagged string like ``"hlr:3"`` (high-level
    #: requirement 3) or ``"llr:7"`` (low-level requirement 7).
    requirement_ids: Annotated[list[str], FieldTags("ticketing")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)


class ClassNode(DiagramNode):
    """Class or struct in the class diagram.

    Represents a concrete (non-abstract) class or struct. Carries its
    own attributes and methods, inheritance relationships
    (``inherits_from``), and interface realizations (``realizes``).
    Maps to :class:`~codegraph.models.compound.CompoundNode` with
    ``kind`` in ``{"class", "struct", "template_class"}``.
    """

    #: Semantic category. Always ``"class"`` for this node type.
    kind: Annotated[Literal["class"], FieldTags("llm", "neo4j", "read")] = "class"

    #: Containing module or namespace (e.g. ``"calc"`` for
    #: ``"calc::Calculator"``). Used to group classes by package.
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Immediate base classes / parent types that this class inherits
    #: from (e.g. ``["BaseCalc", "IPrintable"]``). Each entry is a
    #: qualified name. Used to build ``GENERALIZES`` associations.
    inherits_from: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []

    #: Interfaces that this class implements (e.g.
    #: ``["IPrintable", "ISerializable"]``). Each entry is a qualified
    #: name. Used to build ``REALIZES`` associations.
    realizes: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []

    #: Member variables / data attributes of this class. Each element
    #: is an :class:`AttributeNode` with name, type, and visibility.
    attributes: Annotated[list[AttributeNode], FieldTags("llm", "neo4j", "read")] = []

    #: Member functions / methods of this class. Each element is a
    #: :class:`MethodNode` with signature, return type, and visibility.
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "attributes" in data:
            data["attributes"] = [
                a.model_dump(tags=tags, **kwargs) for a in self.attributes
            ]
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) for m in self.methods
            ]
        return data


class InterfaceNode(DiagramNode):
    """Interface or abstract class in the class diagram.

    Represents a pure interface or abstract base class — a contract
    that concrete classes implement. Contains only method signatures,
    no attributes. All methods are implicitly virtual.
    Maps to :class:`~codegraph.models.compound.CompoundNode` with
    ``kind`` in ``{"interface", "abstract_class"}``.
    """

    #: Semantic category. Always ``"interface"`` for this node type.
    kind: Annotated[Literal["interface"], FieldTags("llm", "neo4j", "read")] = "interface"

    #: Containing module or namespace (e.g. ``"io"`` for
    #: ``"io::IPrintable"``). Used to group interfaces by package.
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Method signatures declared by this interface. Each element is a
    #: :class:`MethodNode` with ``is_virtual`` set to ``True``. No
    #: implementation bodies are stored.
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) for m in self.methods
            ]
        return data


class EnumNode(DiagramNode):
    """Enum in the class diagram.

    Represents an enumeration type — a set of named constant values.
    Maps to :class:`~codegraph.models.compound.CompoundNode` with
    ``kind`` in ``{"enum", "enum_class"}`` (C++ scoped enums use
    ``"enum_class"``).
    """

    #: Semantic category. Always ``"enum"`` for this node type.
    kind: Annotated[Literal["enum"], FieldTags("llm", "neo4j", "read")] = "enum"

    #: Containing module or namespace (e.g. ``"color"`` for
    #: ``"color::RGB"``). Used to group enums by package.
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Ordered list of enum constants. Each element is an
    #: :class:`EnumValueNode` with name and optional description.
    values: Annotated[list[EnumValueNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "values" in data:
            data["values"] = [
                v.model_dump(tags=tags, **kwargs) for v in self.values
            ]
        return data
