"""Edge-level design model — Association."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class Association(BaseModel):
    """A relationship between two top-level design entities.

    Associations represent directed relationships between classes,
    interfaces, and enums in the class diagram. Common predicates
    include ``"GENERALIZES"`` (inheritance), ``"REALIZES"`` (interface
    implementation), ``"AGGREGATES"`` (has-a with shared ownership),
    ``"COMPOSES"`` (has-a with exclusive ownership), and
    ``"ASSOCIATES"`` (generic dependency).

    When serialized for LLM consumption (``tags={"llm"}``), the
    internal field names are aliased to ``from_class``, ``kind``,
    and ``to_class`` for readability.
    """

    #: Fully-qualified name of the source entity (the "from" side).
    #: When serializing for LLMs this field appears as ``from_class``
    #: via its ``serialization_alias``.
    subject: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="from_class"),
    ] = ""

    #: Relationship type (e.g. ``"GENERALIZES"``, ``"AGGREGATES"``,
    #: ``"ASSOCIATES"``). When serializing for LLMs this field appears
    #: as ``kind`` via its ``serialization_alias``.
    predicate: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="kind"),
    ] = ""

    #: Fully-qualified name of the target entity (the "to" side).
    #: When serializing for LLMs this field appears as ``to_class``
    #: via its ``serialization_alias``.
    object: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="to_class"),
    ] = ""

    #: How the relationship is realized (e.g. ``"by-value"``,
    #: ``"by-reference"``, ``"by-pointer"``, ``"inherit"``). Describes
    #: the implementation mechanism behind the association.
    mechanism: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Human-readable description of what this relationship means
    #: (e.g. ``"Calculator delegates arithmetic operations to MathEngine"``).
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Ticketing system requirement IDs associated with this
    #: relationship. Each entry is a tagged string like ``"hlr:3"``
    #: (high-level requirement 3) or ``"llr:7"`` (low-level
    #: requirement 7).
    requirement_ids: Annotated[list[str], FieldTags("ticketing")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
