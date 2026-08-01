"""DecisionNode — a design decision that motivated code structure.

Answers: "Why did we choose X over Y?"

Links to code nodes via MOTIVATES: the code whose existence was driven
by this decision.  Decisions can SUPERSEDE older decisions.
"""

from __future__ import annotations

from codegraph.models.descriptors import Relationship

from codegraph.models.tags import CodeGraphNode  # noqa: F401 — kept for registry side-effects
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class DecisionNode(MemoryNode):
    """A design decision that shaped the codebase."""

    __abstract__ = False

    _markdown_keyword = "Decision"

    _llm_fields = MemoryNode._llm_fields | {"decided_at", "updated_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    # Separate descriptors for CompoundNode / MemberNode targets.
    motivates_compound = Relationship("MOTIVATES", direction="OUTGOING", target_class="CompoundNode")
    motivates_member = Relationship("MOTIVATES", direction="OUTGOING", target_class="MemberNode")

    # ── Memory → Memory ────────────────────────────────────────────
    supersedes = Relationship("SUPERSEDES", direction="OUTGOING", target_class="DecisionNode")
    superseded_by = Relationship("SUPERSEDES", direction="INCOMING", target_class="DecisionNode")