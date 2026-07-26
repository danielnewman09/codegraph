"""AssumptionNode — an assumption that underpins code.

Answers: "What did we assume that might change?"

Links to code nodes via ASSUMES.  Assumptions can CONTRADICT other
assumptions — flagging tensions that need resolution.  Low-confidence
assumptions signal speculative foundations that should be revalidated.
"""

from __future__ import annotations

from neomodel import RelationshipTo, RelationshipFrom

from codegraph.models.tags import CodeGraphNode  # noqa: F401
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class AssumptionNode(MemoryNode):
    """An assumption underlying the code."""

    __abstract__ = False

    _markdown_keyword = "Assumption"

    _llm_fields = MemoryNode._llm_fields | {"decided_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    assumes_compound = RelationshipTo(CompoundNode, "ASSUMES")
    assumes_member = RelationshipTo(MemberNode, "ASSUMES")

    # ── Memory → Memory ────────────────────────────────────────────
    contradicts = RelationshipTo("AssumptionNode", "CONTRADICTS")
    contradicted_by = RelationshipFrom("AssumptionNode", "CONTRADICTS")