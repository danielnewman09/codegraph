"""FieldTags annotation for marking field relevance by use case."""

from __future__ import annotations

from typing import Any, get_type_hints


class FieldTags:
    """Marker annotation for model fields indicating which use cases they apply to.

    Usage:
        name: Annotated[str, FieldTags("llm", "neo4j")]
    """

    def __init__(self, *tags: str) -> None:
        self.tags: frozenset[str] = frozenset(tags)

    def __repr__(self) -> str:
        return f"FieldTags({', '.join(sorted(self.tags))})"


def get_fields_by_tags(model_cls: type, requested_tags: set[str]) -> set[str]:
    """Return the set of field names whose FieldTags intersect requested_tags.

    Fields with no FieldTags annotation are excluded.
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
