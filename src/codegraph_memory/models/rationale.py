"""RationaleNode — explains why a piece of code exists.

Answers: "Why does this method/class/attribute exist?"

Links to code nodes via EXPLAINS.  Rationale can REFINE a higher-level
decision, elaborating on the "why" behind a design choice.
"""

from __future__ import annotations

from neomodel import RelationshipTo

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
    explains_compound = RelationshipTo(CompoundNode, "EXPLAINS")
    explains_member = RelationshipTo(MemberNode, "EXPLAINS")

    # ── Memory → Memory ────────────────────────────────────────────
    refines = RelationshipTo("DecisionNode", "REFINES")