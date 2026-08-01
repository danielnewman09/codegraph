"""RationaleNode — explains why a piece of code exists.

Answers: "Why does this method/class/attribute exist?"

Links to code nodes via EXPLAINS.  Rationale can REFINE a higher-level
decision, elaborating on the "why" behind a design choice.
"""

from __future__ import annotations

from codegraph.models.descriptors import Relationship

from codegraph.models.tags import CodeGraphNode  # noqa: F401
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class RationaleNode(MemoryNode):
    """Explains why a piece of code exists."""

    __abstract__ = False

    _markdown_keyword = "Rationale"

    _llm_fields = MemoryNode._llm_fields | {"decided_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    explains_compound = Relationship("EXPLAINS", direction="OUTGOING", target_class="CompoundNode")
    explains_member = Relationship("EXPLAINS", direction="OUTGOING", target_class="MemberNode")

    # ── Memory → Memory ────────────────────────────────────────────
    refines = Relationship("REFINES", direction="OUTGOING", target_class="DecisionNode")