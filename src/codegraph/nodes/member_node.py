"""Member node for the Neo4j codebase graph (:Member label)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and variables on classes,
    values inside enums, defines inside namespaces. Each member is
    connected to its owning compound via a COMPOSES edge.
    """

    #: Fully-qualified name (e.g. ``"calc::Calculator::add"``). Required.
    qualified_name: str

    #: Short, unqualified name (e.g. ``"add"``). Defaults to ``""``
    #: when only the qualified form is known.
    name: str = ""

    #: Semantic category. One of ``"method"``, ``"variable"``,
    #: ``"define"``, ``"enumvalue"``, or ``"function"``.
    kind: Literal["method", "variable", "define", "enumvalue", "function"]

    #: Provenance layer — where this node came from.
    #:
    #: * ``"design"`` — agent-created / planned
    #: * ``"as-built"`` — parsed from real source code
    #: * ``"dependency"`` — external library / third-party
    layer: Literal["design", "as-built", "dependency"] = "design"

    #: Doxygen reference-id for as-built/dependency nodes. Empty string
    #: for design-layer members.
    refid: str = ""

    #: Doxygen reference-id of the owning compound. Used to link back to
    #: the parent CompoundNode via a COMPOSES edge.
    compound_refid: str = ""

    #: One-line summary description.
    brief_description: str = ""

    #: Extended description body after the brief line.
    detailed_description: str = ""

    #: Return type or declared type (e.g. ``"int"``, ``"void"``,
    #: ``"std::string"``).
    type_signature: str = ""

    #: Full definition string (e.g.
    #: ``"int Calculator::add(int a, int b)"``).
    definition: str = ""

    #: Argument string including parentheses (e.g. ``"(int a, int b)"``).
    #: Empty for non-function members.
    argsstring: str = ""

    #: Filesystem path to the source file declaring this member.
    file_path: str = ""

    #: One-based line number where this member is declared in
    #: ``file_path``. ``None`` when unknown.
    line_number: int | None = None

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``).
    source: str = ""

    #: Access specifier / visibility. One of ``"public"``,
    #: ``"private"``, ``"protected"``, or ``""`` (unknown / default).
    protection: Literal["public", "private", "protected", ""] = ""

    #: ``True`` if the method/variable is declared ``static``.
    is_static: bool = False

    #: ``True`` if the member is ``const``-qualified (C++).
    is_const: bool = False

    #: ``True`` if the member is declared ``constexpr`` (C++).
    is_constexpr: bool = False

    #: ``True`` if the method is declared ``virtual`` (C++).
    is_virtual: bool = False

    #: ``True`` if the method is declared ``inline`` (C++).
    is_inline: bool = False

    #: ``True`` if the constructor or conversion operator is declared
    #: ``explicit`` (C++).
    is_explicit: bool = False

    model_config = {"from_attributes": True}
