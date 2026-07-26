"""TradeoffNode — a tradeoff accepted for a component.

Answers: "What did we sacrifice?"

Links to code nodes via TRADES_OFF.  Captures the cost side of
architecture decisions: what was given up to achieve a benefit elsewhere.
"""

from __future__ import annotations

from neomodel import RelationshipTo

from codegraph.models.tags import CodeGraphNode  # noqa: F401
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class TradeoffNode(MemoryNode):
    """A tradeoff accepted for a component."""

    __abstract__ = False

    _markdown_keyword = "Tradeoff"

    _llm_fields = MemoryNode._llm_fields | {"decided_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    trades_off_compound = RelationshipTo(CompoundNode, "TRADES_OFF")
    trades_off_member = RelationshipTo(MemberNode, "TRADES_OFF")