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

from neomodel import db

from codegraph.models.tags import CodeGraphNode

from codegraph_memory.models.base import MemoryNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.rationale import RationaleNode
from codegraph_memory.models.assumption import AssumptionNode
from codegraph_memory.models.tradeoff import TradeoffNode
from codegraph_memory.models.insight import InsightNode
from codegraph_memory.models.relationships import (
    _inflate_code_node,
    get_all_memory_for_code_node,
)


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
        rel_types = "|".join(_REL_TYPE_TO_CLASS)
        results, _ = db.cypher_query(
            f"MATCH (m)-[r:{rel_types}]->(c) "
            f"WHERE c.qualified_name = $qname "
            f"RETURN m, c.uid, c.qualified_name, type(r) AS rel_type",
            {"qname": qualified_name},
        )
        entries: list[MemoryEntry] = []
        for row in results:
            raw_memory = row[0]
            code_uid = row[1]
            code_qname = row[2]
            rel_type = row[3]
            memory = _inflate_code_node(raw_memory)
            if memory is not None:
                entries.append(MemoryEntry(
                    memory=memory,
                    code_node_uid=code_uid,
                    code_node_qualified_name=code_qname,
                    relation_type=rel_type,
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
        results, _ = db.cypher_query(
            "MATCH (m) "
            "WHERE $tag IN m.tags "
            "AND (m:DecisionNode OR m:ConstraintNode OR m:RationaleNode "
            "OR m:AssumptionNode OR m:TradeoffNode OR m:InsightNode) "
            "RETURN m",
            {"tag": tag},
        )
        entries: list[MemoryEntry] = []
        for row in results:
            memory = _inflate_code_node(row[0])
            if memory is not None:
                entry = MemoryEntry(memory=memory)
                if include_code:
                    # Fetch linked code nodes
                    code_results, _ = db.cypher_query(
                        f"MATCH (m)-[r]->(c) "
                        f"WHERE elementId(m) = $mid "
                        f"AND NOT type(r) IN ['SUPERSEDES', 'CONTRADICTS', 'REFINES'] "
                        f"RETURN c.uid, c.qualified_name, type(r) LIMIT 1",
                        {"mid": db.parse_element_id(memory.element_id)},
                    )
                    if code_results:
                        entry.code_node_uid = code_results[0][0]
                        entry.code_node_qualified_name = code_results[0][1]
                        entry.relation_type = code_results[0][2]
                entries.append(entry)
        return cls(tags=frozenset({tag}), entries=entries)

    # ── Convenience query methods ──────────────────────────────────

    @classmethod
    def constraints_for(cls, code_node: CodeGraphNode) -> list[ConstraintNode]:
        """Return all constraints governing a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of ConstraintNode instances linked via CONSTRAINS.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (c:ConstraintNode)-[:CONSTRAINS]->(target) "
            "WHERE elementId(target) = $tid RETURN c",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def decisions_for(cls, code_node: CodeGraphNode) -> list[DecisionNode]:
        """Return all decisions motivating a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of DecisionNode instances linked via MOTIVATES.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (d:DecisionNode)-[:MOTIVATES]->(target) "
            "WHERE elementId(target) = $tid RETURN d",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def insights_for(cls, code_node: CodeGraphNode) -> list[InsightNode]:
        """Return all insights learned from a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of InsightNode instances linked via INSIGHT_INTO.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (i:InsightNode)-[:INSIGHT_INTO]->(target) "
            "WHERE elementId(target) = $tid RETURN i",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def rationales_for(cls, code_node: CodeGraphNode) -> list[RationaleNode]:
        """Return all rationales explaining a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of RationaleNode instances linked via EXPLAINS.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (r:RationaleNode)-[:EXPLAINS]->(target) "
            "WHERE elementId(target) = $tid RETURN r",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def assumptions_for(cls, code_node: CodeGraphNode) -> list[AssumptionNode]:
        """Return all assumptions underpinning a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of AssumptionNode instances linked via ASSUMES.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (a:AssumptionNode)-[:ASSUMES]->(target) "
            "WHERE elementId(target) = $tid RETURN a",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def tradeoffs_for(cls, code_node: CodeGraphNode) -> list[TradeoffNode]:
        """Return all tradeoffs applying to a code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of TradeoffNode instances linked via TRADES_OFF.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        results, _ = db.cypher_query(
            "MATCH (t:TradeoffNode)-[:TRADES_OFF]->(target) "
            "WHERE elementId(target) = $tid RETURN t",
            {"tid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

    @classmethod
    def affected_decisions(cls, code_node: CodeGraphNode) -> list[DecisionNode]:
        """Return all decisions/memories linked to this node or its children.

        Traverses COMPOSES edges to find memories linked to any
        descendant of the given code node.

        Args:
            code_node: A CodeGraphNode instance.

        Returns:
            A list of DecisionNode (and other memory) instances.
        """
        if not hasattr(code_node, "element_id_property"):
            return []
        # Match the node and all its composed descendants
        results, _ = db.cypher_query(
            "MATCH (target)<-[:COMPOSES*0..10]-(parent) "
            "WHERE elementId(parent) = $pid "
            "MATCH (m)-[:MOTIVATES|CONSTRAINS|EXPLAINS|ASSUMES|TRADES_OFF|INSIGHT_INTO]->(target) "
            "RETURN DISTINCT m",
            {"pid": db.parse_element_id(code_node.element_id)},
        )
        return [n for n in (_inflate_code_node(r[0]) for r in results) if n is not None]

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
        for entry in self.entries:
            entry.memory.save()

            if entry.code_node_uid and entry.relation_type:
                # Connect to the code node via raw Cypher
                from codegraph.models.tags import CodeGraphNode
                uid_prop = type(entry.memory)._uid_prop()
                try:
                    db.cypher_query(
                        f"MATCH (m), (c) "
                        f"WHERE elementId(m) = $mid "
                        f"AND c.uid = $cid "
                        f"MERGE (m)-[:{entry.relation_type}]->(c)",
                        {
                            "mid": db.parse_element_id(entry.memory.element_id),
                            "cid": entry.code_node_uid,
                        },
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