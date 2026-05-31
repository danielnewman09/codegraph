"""Namespace-level design model — ModuleNode."""

from __future__ import annotations

from typing import Annotated, Literal

from codegraph.designs.compound import DiagramNode
from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class ModuleNode(DiagramNode):
    """Module or namespace in the class diagram.

    Represents a logical grouping of related classes, interfaces, and
    enums — typically corresponding to a directory or package (e.g.
    ``"calc"`` for ``"calc::Calculator"``). Modules participate in
    the class diagram as container nodes but do not carry methods or
    attributes of their own.

    Maps to :class:`~codegraph.models.namespace.NamespaceNode` with
    ``kind="module"`` in the Neo4j graph.
    """

    #: Semantic category. Always ``"module"`` for this node type.
    kind: Annotated[Literal["module"], FieldTags("llm", "neo4j", "read")] = "module"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
