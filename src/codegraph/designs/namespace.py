"""Namespace-level design model — ModuleNode."""

from __future__ import annotations

from typing import Annotated, Literal

from codegraph.designs.compound import DiagramNode
from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class ModuleNode(DiagramNode):
    """Module / namespace in the class diagram."""
    kind: Literal["module"] = "module"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
