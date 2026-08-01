"""AssumptionNode — an assumption that underpins code.

Answers: "What did we assume that might change?"

Links to code nodes via ASSUMES.  Assumptions can CONTRADICT other
assumptions — flagging tensions that need resolution.  Low-confidence
assumptions signal speculative foundations that should be revalidated.
"""

from __future__ import annotations

from codegraph.models.descriptors import Relationship

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
    assumes_compound = Relationship("ASSUMES", direction="OUTGOING", target_class="CompoundNode")
    assumes_member = Relationship("ASSUMES", direction="OUTGOING", target_class="MemberNode")

    # ── Memory → Memory ────────────────────────────────────────────
    contradicts = Relationship("CONTRADICTS", direction="OUTGOING", target_class="AssumptionNode")
    contradicted_by = Relationship("CONTRADICTS", direction="INCOMING", target_class="AssumptionNode")