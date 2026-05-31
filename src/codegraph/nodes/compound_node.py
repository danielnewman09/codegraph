"""Compound node for the Neo4j codebase graph (:Compound label)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs,
    interfaces, enums — that own members and participate in
    associations (generalization, aggregation, etc.).
    """

    #: Fully-qualified name (e.g. ``"calc::Calculator"``). Required.
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]

    #: Short, unqualified name (e.g. ``"Calculator"``). Defaults to
    #: ``""`` when only the qualified form is known.
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category. One of ``"class"``, ``"struct"``,
    #: ``"template_class"``, ``"interface"``, ``"abstract_class"``,
    #: ``"enum"``, ``"enum_class"``, or ``"union"``.
    kind: Annotated[
        Literal[
            "class",
            "struct",
            "template_class",
            "interface",
            "abstract_class",
            "enum",
            "enum_class",
            "union",
        ],
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

    #: Foreign key to the owning ticketing-system component (set by
    #: external consumers such as the ticketing agent). ``None`` when
    #: not yet assigned.
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Doxygen reference-id for as-built/dependency nodes. Empty string
    #: for design-layer compounds.
    refid: Annotated[str, FieldTags("neo4j")] = ""

    #: One-line summary description. Typically extracted from the first
    #: sentence of a Doxygen ``@brief`` tag.
    brief_description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Extended description body. Carries the remainder of the doc
    #: comment after the brief line, including ``@details`` content.
    detailed_description: Annotated[str, FieldTags("neo4j")] = ""

    #: Immediate base classes / parent types that this compound inherits
    #: from (e.g. ``["BaseCalc", "IPrintable"]``). Each entry is a
    #: qualified name. Used to build GENERALIZES edges.
    base_classes: Annotated[list[str], FieldTags("neo4j", "read")] = []

    #: Filesystem path to the primary source file declaring this
    #: compound (e.g. ``"/src/calculator.h"``).
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: One-based line number where this compound is declared in
    #: ``file_path``. ``None`` when unknown.
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``).
    source: Annotated[str, FieldTags("neo4j")] = ""

    #: ``True`` if the class/struct is declared ``final`` (cannot be
    #: inherited from).
    is_final: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the class/struct has pure virtual methods (C++),
    #: making it abstract.
    is_abstract: Annotated[bool, FieldTags("neo4j", "read")] = False

    model_config = {"from_attributes": True}
