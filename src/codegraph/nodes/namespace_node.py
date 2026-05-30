"""Namespace node for the Neo4j codebase graph (:Namespace label)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. ``std`` COMPOSES ``std::chrono``).
    """

    #: Fully-qualified name (e.g. ``"std::chrono"``). Required — every
    #: namespace must have a unique identity within the graph.
    qualified_name: str

    #: Short, unqualified name (e.g. ``"chrono"``). Defaults to ``""``
    #: when only the qualified form is known.
    name: str = ""

    #: Semantic category of the namespace container. One of
    #: ``"namespace"``, ``"package"``, or ``"module"``.
    kind: Literal["namespace", "package", "module"] = "namespace"

    #: Provenance layer — where this node came from.
    #:
    #: * ``"design"`` — agent-created / planned
    #: * ``"as-built"`` — parsed from real source code
    #: * ``"dependency"`` — external library / third-party
    layer: Literal["design", "as-built", "dependency"] = "design"

    #: Doxygen reference-id for as-built/dependency nodes. Empty string
    #: for design-layer nodes (which may not have a source counterpart).
    refid: str = ""

    #: Human-readable description (plain text or Markdown). Set by
    #: agents during design or extracted from doc comments.
    description: str = ""

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``). Useful for filtering and auditing.
    source: str = ""

    model_config = {"from_attributes": True}
