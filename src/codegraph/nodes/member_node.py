"""Member node for the Neo4j codebase graph (:Member label)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and variables on classes,
    values inside enums, defines inside namespaces. Each member is
    connected to its owning compound via a COMPOSES edge.
    """

    #: Fully-qualified name (e.g. ``"calc::Calculator::add"``). Required.
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]

    #: Short, unqualified name (e.g. ``"add"``). Defaults to ``""``
    #: when only the qualified form is known.
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category. One of ``"method"``, ``"variable"``,
    #: ``"define"``, ``"enumvalue"``, or ``"function"``.
    kind: Annotated[
        Literal["method", "variable", "define", "enumvalue", "function"],
        FieldTags("llm", "neo4j", "read"),
    ]

    #: Provenance layer — where this node came from.
    #:
    #: * ``"design"`` — agent-created / planned
    #: * ``"as-built"`` — parsed from real source code
    #: * ``"dependency"`` — external library / third-party
    layer: Annotated[
        Literal["design", "as-built", "dependency"],
        FieldTags("neo4j", "read"),
    ] = "design"

    #: Foreign key to the owning ticketing-system component. ``None``
    #: when not yet assigned.
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Doxygen reference-id for as-built/dependency nodes. Empty string
    #: for design-layer members.
    refid: Annotated[str, FieldTags("neo4j")] = ""

    #: Doxygen reference-id of the owning compound. Used to link back to
    #: the parent CompoundNode via a COMPOSES edge.
    compound_refid: Annotated[str, FieldTags("neo4j")] = ""

    #: One-line summary description.
    brief_description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Extended description body after the brief line.
    detailed_description: Annotated[str, FieldTags("neo4j")] = ""

    #: Return type or declared type (e.g. ``"int"``, ``"void"``,
    #: ``"std::string"``).
    type_signature: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Full definition string (e.g.
    #: ``"int Calculator::add(int a, int b)"``).
    definition: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Argument string including parentheses (e.g. ``"(int a, int b)"``).
    #: Empty for non-function members.
    argsstring: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Filesystem path to the source file declaring this member.
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: One-based line number where this member is declared in
    #: ``file_path``. ``None`` when unknown.
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``).
    source: Annotated[str, FieldTags("neo4j")] = ""

    #: Access specifier / visibility. One of ``"public"``,
    #: ``"private"``, ``"protected"``, or ``""`` (unknown / default).
    protection: Annotated[
        Literal["public", "private", "protected", ""],
        FieldTags("llm", "neo4j", "read"),
    ] = ""

    #: ``True`` if the method/variable is declared ``static``.
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the member is ``const``-qualified (C++).
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the member is declared ``constexpr`` (C++).
    is_constexpr: Annotated[bool, FieldTags("neo4j")] = False

    #: ``True`` if the method is declared ``virtual`` (C++).
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the method is declared ``inline`` (C++).
    is_inline: Annotated[bool, FieldTags("neo4j")] = False

    #: ``True`` if the constructor or conversion operator is declared
    #: ``explicit`` (C++).
    is_explicit: Annotated[bool, FieldTags("neo4j")] = False

    model_config = {"from_attributes": True}
