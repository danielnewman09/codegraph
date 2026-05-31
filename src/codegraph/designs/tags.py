"""FieldTags annotation for marking field relevance by use case.

This module provides the :class:`FieldTags` marker annotation and the
:func:`get_fields_by_tags` lookup function. Together they power the
tag-based serialization system used by all design models — fields are
annotated with one or more use-case tags, and :func:`model_dump` filters
output to only the fields relevant for a given consumer.

Tags
----
* ``"llm"`` — Fields visible when serializing for LLM prompts. These
  are the "conversational" fields: names, descriptions, types,
  relationships.
* ``"neo4j"`` — Fields persisted in the Neo4j graph database for
  round-trip fidelity (to_neo4j → from_neo4j).
* ``"read"`` — Fields needed by internal consumers (display, search,
  analysis) but not by LLMs.
* ``"ticketing"`` — Fields consumed by external ticketing-system
  integrations (requirement_ids, implementation_status, etc.).
"""

from __future__ import annotations

from typing import Any, get_type_hints


class FieldTags:
    """Marker annotation for model fields indicating which use cases they apply to.

    Used as a metadata annotation inside :class:`typing.Annotated` to
    tag Pydantic model fields. Multiple tags can be specified; a field
    is included in output when its tag set intersects the tags requested
    by the caller.

    Usage::

        name: Annotated[str, FieldTags("llm", "neo4j")]

    The canonical tags are:

    * ``"llm"`` — Visible in LLM serialization
    * ``"neo4j"`` — Persisted in the Neo4j graph
    * ``"read"`` — Visible to internal consumers (display, search)
    * ``"ticketing"`` — Consumed by ticketing-system integrations

    Fields without any :class:`FieldTags` annotation are excluded from
    all tag-filtered output (they behave as private / internal-only).
    """

    def __init__(self, *tags: str) -> None:
        #: Immutable set of tags assigned to the annotated field.
        self.tags: frozenset[str] = frozenset(tags)

    def __repr__(self) -> str:
        return f"FieldTags({', '.join(sorted(self.tags))})"


def get_fields_by_tags(model_cls: type, requested_tags: set[str]) -> set[str]:
    """Return the set of field names whose :class:`FieldTags` intersect *requested_tags*.

    Uses :func:`typing.get_type_hints` with ``include_extras=True`` to
    inspect :class:`Annotated` metadata at runtime. Only fields with at
    least one matching tag are returned — untagged fields are excluded.

    This is the core lookup used by :func:`_tagged_model_dump` in
    :mod:`codegraph.designs.member` to filter serialization output.

    Args:
        model_cls: The Pydantic model class to inspect.
        requested_tags: Set of tags to match against (e.g. ``{"llm"}``).

    Returns:
        A set of field names (strings) whose :class:`FieldTags` have at
        least one tag in common with *requested_tags*.
    """
    hints = get_type_hints(model_cls, include_extras=True)
    result: set[str] = set()
    for field_name, hint in hints.items():
        metadata = getattr(hint, "__metadata__", ())
        for item in metadata:
            if isinstance(item, FieldTags) and (item.tags & requested_tags):
                result.add(field_name)
                break
    return result
