"""LlmSerializable ABC — contract for LLM-facing serialization on neomodel nodes.

Uses a combined metaclass (ABCMeta + NodeMeta) so that subclasses can
inherit from both StructuredNode and LlmSerializable without metaclass
conflicts.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from neomodel.sync_.node import NodeMeta


class _LlmSerializableMeta(NodeMeta, ABCMeta):
    """Combined metaclass: NodeMeta for neomodel properties, ABCMeta for @abstractmethod.

    NodeMeta.__new__ is only invoked for subclasses that inherit from
    ``StructuredNode``. For plain ABC subclasses (including LlmSerializable
    itself), the pure ABCMeta path is used.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        from neomodel import StructuredNode

        is_neomodel = any(
            issubclass(b, StructuredNode)
            for b in bases
            if isinstance(b, type) and b is not object
        )
        if not is_neomodel:
            # Pure ABC path — skip NodeMeta initialization
            return ABCMeta.__new__(mcs, name, bases, namespace, **kwargs)
        return super().__new__(mcs, name, bases, namespace, **kwargs)


class LlmSerializable(metaclass=_LlmSerializableMeta):
    """Abstract base for neomodel nodes that can serialize for LLM consumption.

    Subclasses must:
    - Declare ``_llm_fields`` as a class-level ``set[str]`` of field names
    - Implement ``serialize()`` to return only those fields
    - Implement ``deserialize()`` to hydrate from LLM-provided dicts
    """

    _llm_fields: set[str] = set()

    @abstractmethod
    def serialize(self) -> dict:
        """Return a dict of only LLM-visible fields."""
        ...

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict) -> "LlmSerializable":
        """Instantiate a node from LLM-provided dict data."""
        ...
