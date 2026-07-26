"""ConstraintNode — a non-functional constraint that governs code.

Answers: "What must this code satisfy?"

Links to code nodes via CONSTRAINS.  Constraints may be performance
requirements, security boundaries, compatibility requirements, etc.
"""

from __future__ import annotations

from neomodel import RelationshipTo

from codegraph.models.tags import CodeGraphNode  # noqa: F401
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph_memory.models.base import MemoryNode


class ConstraintNode(MemoryNode):
    """A non-functional constraint governing code."""

    __abstract__ = False

    _markdown_keyword = "Constraint"

    _llm_fields = MemoryNode._llm_fields | {"decided_at"}

    # ── Identity ──────────────────────────────────────────────────
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── Memory → Code ─────────────────────────────────────────────
    constrains_compound = RelationshipTo(CompoundNode, "CONSTRAINS")
    constrains_member = RelationshipTo(MemberNode, "CONSTRAINS")