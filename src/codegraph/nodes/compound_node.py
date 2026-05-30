"""Compound node for the Neo4j codebase graph (:Compound label)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs,
    interfaces, enums — that own members and participate in
    associations (generalization, aggregation, etc.).
    """

    #: Fully-qualified name (e.g. ``"calc::Calculator"``). Required.
    qualified_name: str

    #: Short, unqualified name (e.g. ``"Calculator"``). Defaults to
    #: ``""`` when only the qualified form is known.
    name: str = ""

    #: Semantic category. One of ``"class"``, ``"struct"``,
    #: ``"template_class"``, ``"interface"``, ``"abstract_class"``,
    #: ``"enum"``, ``"enum_class"``, or ``"union"``.
    kind: Literal[
        "class",
        "struct",
        "template_class",
        "interface",
        "abstract_class",
        "enum",
        "enum_class",
        "union",
    ]

    #: Provenance layer — where this node came from.
    #:
    #: * ``"design"`` — agent-created / planned
    #: * ``"as-built"`` — parsed from real source code
    #: * ``"dependency"`` — external library / third-party
    layer: Literal["design", "as-built", "dependency"] = "design"

    #: Doxygen reference-id for as-built/dependency nodes. Empty string
    #: for design-layer compounds.
    refid: str = ""

    #: Full description (plain text or Markdown).
    description: str = ""

    #: One-line summary description. Typically extracted from the first
    #: sentence of a Doxygen ``@brief`` tag.
    brief_description: str = ""

    #: Extended description body. Carries the remainder of the doc
    #: comment after the brief line, including ``@details`` content.
    detailed_description: str = ""

    #: Immediate base classes / parent types that this compound inherits
    #: from (e.g. ``["BaseCalc", "IPrintable"]``). Each entry is a
    #: qualified name. Used to build GENERALIZES edges.
    base_classes: list[str] = []

    #: Filesystem path to the primary source file declaring this
    #: compound (e.g. ``"/src/calculator.h"``).
    file_path: str = ""

    #: One-based line number where this compound is declared in
    #: ``file_path``. ``None`` when unknown.
    line_number: int | None = None

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``).
    source: str = ""

    #: Access specifier / visibility for the compound's top-level
    #: declaration context. One of ``"public"``, ``"private"``,
    #: ``"protected"``, or ``""`` (unknown / default).
    protection: Literal["public", "private", "protected", ""] = ""

    #: ``True`` if the class/struct is declared ``final`` (cannot be
    #: inherited from).
    is_final: bool = False

    #: ``True`` if the class/struct has pure virtual methods (C++),
    #: making it abstract.
    is_abstract: bool = False

    model_config = {"from_attributes": True}
