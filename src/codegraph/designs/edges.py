"""Edge-level design model — Association."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class Association(BaseModel):
    """A relationship between two top-level design entities."""

    subject: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="from_class"),
    ] = ""
    predicate: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="kind"),
    ] = ""
    object: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="to_class"),
    ] = ""
    mechanism: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    requirement_ids: Annotated[list[str], FieldTags("ticketing")] = []  # tagged: "hlr:3", "llr:7"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
