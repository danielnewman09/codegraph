"""Namespace node for the Neo4j codebase graph (:Namespace label)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. ``std`` COMPOSES ``std::chrono``).
    """

    #: Fully-qualified name (e.g. ``"std::chrono"``). Required — every
    #: namespace must have a unique identity within the graph.
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]

    #: Short, unqualified name (e.g. ``"chrono"``). Defaults to ``""``
    #: when only the qualified form is known.
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category of the namespace container. One of
    #: ``"namespace"``, ``"package"``, or ``"module"``.
    kind: Annotated[
        Literal["namespace", "package", "module"],
        FieldTags("llm", "neo4j", "read"),
    ] = "namespace"

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
    #: for design-layer nodes (which may not have a source counterpart).
    refid: Annotated[str, FieldTags("neo4j")] = ""

    #: Human-readable description (plain text or Markdown). Set by
    #: agents during design or extracted from doc comments.
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``). Useful for filtering and auditing.
    source: Annotated[str, FieldTags("neo4j")] = ""

    model_config = {"from_attributes": True}
