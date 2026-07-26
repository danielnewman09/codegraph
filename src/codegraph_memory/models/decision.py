"""DecisionNode — a design decision that motivated code structure.

Answers: "Why did we choose X over Y?"

Links to code nodes via MOTIVATES: the code whose existence was driven
by this decision.  Decisions can SUPERSEDE older decisions.
"""

from __future__ import annotations

from neomodel import RelationshipTo, RelationshipFrom

from codegraph.models.tags import CodeGraphNode  # noqa: F401 — needed for neomodel class resolution
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
    # Separate descriptors for CompoundNode / MemberNode targets
    # so that neomodel resolves the correct label (ClassNode,
    # MethodNode, etc. are subclasses of these).
    motivates_compound = RelationshipTo(CompoundNode, "MOTIVATES")
    motivates_member = RelationshipTo(MemberNode, "MOTIVATES")

    # ── Memory → Memory ────────────────────────────────────────────
    supersedes = RelationshipTo("DecisionNode", "SUPERSEDES")
    superseded_by = RelationshipFrom("DecisionNode", "SUPERSEDES")