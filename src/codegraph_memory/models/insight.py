"""InsightNode — a lesson learned from building/maintaining code.

Answers: "What did we learn after building it?"

Links to code nodes via INSIGHT_INTO.  Differs from RationaleNode:
Rationale explains intent (before/at design time), Insight captures
what was discovered after implementation, testing, or production use.
"""

from __future__ import annotations

from neomodel import RelationshipTo

from codegraph.models.tags import CodeGraphNode  # noqa: F401
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class InsightNode(MemoryNode):
    """A lesson learned from building or maintaining code."""

    __abstract__ = False

    _markdown_keyword = "Insight"

    _llm_fields = MemoryNode._llm_fields | {"decided_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    insight_into_compound = RelationshipTo(CompoundNode, "INSIGHT_INTO")
    insight_into_member = RelationshipTo(MemberNode, "INSIGHT_INTO")