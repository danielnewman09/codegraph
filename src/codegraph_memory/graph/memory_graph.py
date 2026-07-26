"""MemoryGraph — container for querying and persisting memory nodes.

Provides scope-based read methods for memory nodes linked to code nodes,
plus serialization/deserialization and Neo4j persistence.

Analogous to codegraph's LayerGraph, but for the memory layer.  Memory
nodes are organized by the code nodes they link to, with tag-based
filtering following the same design/as-built lifecycle as code nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from codegraph.backends import get_backend
from codegraph.models.tags import CodeGraphNode

from codegraph_memory.models.base import MemoryNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.rationale import RationaleNode
from codegraph_memory.models.assumption import AssumptionNode
from codegraph_memory.models.tradeoff import TradeoffNode
from codegraph_memory.models.insight import InsightNode


# Map of relationship type → memory node class
_REL_TYPE_TO_CLASS: dict[str, type[MemoryNode]] = {
    "MOTIVATES": DecisionNode,
    "CONSTRAINS": ConstraintNode,
    "EXPLAINS": RationaleNode,
    "ASSUMES": AssumptionNode,
    "TRADES_OFF": TradeoffNode,
    "INSIGHT_INTO": InsightNode,
}

# Map of class name → memory node class
_MEMORY_CLASSES: dict[str, type[MemoryNode]] = {
    cls.__name__: cls for cls in _REL_TYPE_TO_CLASS.values()
}


@dataclass
class MemoryEntry:
    """A memory node and the code node it links to.

    Attributes:
        memory: The memory node instance.
        code_node_uid: The uid of the linked code node (or None if standalone).
        code_node_qualified_name: The qualified_name of the linked code node.
        relation_type: The relationship type linking memory to code.
    """

    memory: MemoryNode
    code_node_uid: str | None = None
    code_node_qualified_name: str | None = None
    relation_type: str | None = None


@dataclass
class MemoryGraph:
    """Container for memory nodes linked to code nodes.

    Holds memory nodes organized by the code nodes they link to.
    Analogous to codegraph's LayerGraph, but for the memory layer.

    Attributes:
        tags: The provenance tags this graph was constructed from
            (e.g. frozenset({"design"}), frozenset({"design", "as-built"})).
        entries: List of MemoryEntry instances.
    """

    tags: frozenset[str] = field(default_factory=frozenset)
    entries: list[MemoryEntry] = field(default_factory=list)

    # ── Factory methods ────────────────────────────────────────────

    @classmethod
    def for_code_node(cls, qualified_name: str) -> "MemoryGraph":
        """Fetch all memory nodes linked to a code node by qualified_name.

        Args:
            qualified_name: The qualified_name of the code node.

        Returns:
            A MemoryGraph with all memory nodes linked to the code node.
        """
        graph_repo = get_backend().graph
        code_uid = graph_repo.resolve_uid(qualified_name)

        results = get_backend().memory.find_for_code_node_by_qname(
            qualified_name
        )
        entries: list[MemoryEntry] = []
        for r in results:
            entries.append(MemoryEntry(
                memory=r["memory"],
                code_node_uid=code_uid,
                code_node_qualified_name=qualified_name,
                relation_type=r["rel_type"],
            ))
        return cls(tags=frozenset(), entries=entries)

    @classmethod
    def for_tag(cls, tag: str, include_code: bool = False) -> "MemoryGraph":
        """Fetch all memory nodes matching a provenance tag.

        Args:
            tag: The tag to filter by (e.g. "design", "as-built").
            include_code: If True, also fetch linked code nodes and
                populate the code_node fields on each entry.

        Returns:
            A MemoryGraph with all memory nodes matching the tag.
        """
        memory_repo = get_backend().memory
        nodes = memory_repo.find_by_tag(tag)
        entries: list[MemoryEntry] = []
        for memory in nodes:
            entry = MemoryEntry(memory=memory)
            if include_code and hasattr(memory, "uid"):
                linked = memory_repo.find_linked_code_node(memory.uid)
                if linked:
                    entry.code_node_uid = linked["uid"]
                    entry.code_node_qualified_name = linked["qualified_name"]
                    entry.relation_type = linked["rel_type"]
            entries.append(entry)
        return cls(tags=frozenset({tag}), entries=entries)

    # ── Convenience query methods ──────────────────────────────────

    @classmethod
    def _memories_by_type(
        cls,
        code_uid: str,
        rel_type: str,
        node_class: type,
    ) -> list:
        """Return memories of a specific type+relationship for a code node.

        Internal helper shared by constraints_for, decisions_for, etc.
        """
        results = get_backend().memory.find_for_code_node(code_uid)
        return [
            r["memory"] for r in results
            if isinstance(r["memory"], node_class) and r.get("rel_type") == rel_type
        ]

    @classmethod
    def constraints_for(cls, code_node: CodeGraphNode) -> list[ConstraintNode]:
        """Return all constraints governing a code node."""
        return cls._memories_by_type(
            code_node.uid, "CONSTRAINS", ConstraintNode
        )

    @classmethod
    def decisions_for(cls, code_node: CodeGraphNode) -> list[DecisionNode]:
        """Return all decisions motivating a code node."""
        return cls._memories_by_type(
            code_node.uid, "MOTIVATES", DecisionNode
        )

    @classmethod
    def insights_for(cls, code_node: CodeGraphNode) -> list[InsightNode]:
        """Return all insights learned from a code node."""
        return cls._memories_by_type(
            code_node.uid, "INSIGHT_INTO", InsightNode
        )

    @classmethod
    def rationales_for(cls, code_node: CodeGraphNode) -> list[RationaleNode]:
        """Return all rationales explaining a code node."""
        return cls._memories_by_type(
            code_node.uid, "EXPLAINS", RationaleNode
        )

    @classmethod
    def assumptions_for(cls, code_node: CodeGraphNode) -> list[AssumptionNode]:
        """Return all assumptions underpinning a code node."""
        return cls._memories_by_type(
            code_node.uid, "ASSUMES", AssumptionNode
        )

    @classmethod
    def tradeoffs_for(cls, code_node: CodeGraphNode) -> list[TradeoffNode]:
        """Return all tradeoffs applying to a code node."""
        return cls._memories_by_type(
            code_node.uid, "TRADES_OFF", TradeoffNode
        )

    @classmethod
    def affected_decisions(cls, code_node: CodeGraphNode) -> list[DecisionNode]:
        """Return all decisions/memories linked to this node or its children.

        Traverses COMPOSES edges to find memories linked to any
        descendant of the given code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of memory node instances.
        """
        return get_backend().memory.find_linked_to_descendants(
            code_node.uid
        )

    # ── Serialization ──────────────────────────────────────────────

    def serialize(self, fields: str = "llm") -> list[dict]:
        """Serialize the graph as a list of dicts.

        Each entry is a serialized memory node with optional linked
        code node information.

        Args:
            fields: Which property fields to include.
                ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every defined property.

        Returns:
            A list of serialized dicts, suitable for json.dumps().
        """
        result: list[dict] = []
        for entry in self.entries:
            data = entry.memory.serialize(fields=fields)
            if entry.code_node_uid:
                data["linked_code_uid"] = entry.code_node_uid
            if entry.code_node_qualified_name:
                data["linked_code_qualified_name"] = entry.code_node_qualified_name
            if entry.relation_type:
                data["relation_type"] = entry.relation_type
            result.append(data)
        return result

    @classmethod
    def deserialize(cls, data: list[dict]) -> "MemoryGraph":
        """Deserialize from a list of dicts (as produced by serialize()).

        Pure deserialization — no database interaction.  Infers tags
        from the first node that has a tags field.

        Args:
            data: A list of dicts, each a serialized memory node.

        Returns:
            A MemoryGraph containing the deserialized memory nodes.
        """
        entries: list[MemoryEntry] = []
        tags: frozenset[str] = frozenset()

        for item in data:
            memory = CodeGraphNode.deserialize(item)
            entry = MemoryEntry(
                memory=memory,
                code_node_uid=item.get("linked_code_uid"),
                code_node_qualified_name=item.get("linked_code_qualified_name"),
                relation_type=item.get("relation_type"),
            )
            entries.append(entry)

            if not tags and hasattr(memory, "tags") and memory.tags:
                tags = frozenset(memory.tags)

        return cls(tags=tags, entries=entries)

    # ── Persistence ────────────────────────────────────────────────

    def to_neo4j(self) -> None:
        """Persist all memory nodes and relationships to Neo4j.

        Saves every memory node.  For entries with linked code nodes,
        creates the relationship to the code node if it exists in the
        database.
        """
        backend = get_backend()
        for entry in self.entries:
            backend.save(entry.memory)

            if entry.code_node_uid and entry.relation_type:
                try:
                    backend.memory.link_to_code_node(
                        entry.memory.uid,
                        entry.code_node_uid,
                        entry.relation_type,
                    )
                except Exception:
                    pass  # best-effort linking

    # ── Iteration helpers ──────────────────────────────────────────

    def __iter__(self) -> Iterator[MemoryEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def memories(self) -> list[MemoryNode]:
        """Return just the memory node instances (without linking info)."""
        return [e.memory for e in self.entries]
