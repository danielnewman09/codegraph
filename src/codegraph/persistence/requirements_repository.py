"""RequirementsRepository — abstract interface for requirements operations.

Consolidates HLR/LLR/test tree traversal, scaffold lifecycle, and
verification edge management — patterns currently scattered across
design_oo, workflow_tools, and requirements/persistence with raw Cypher.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.graph import LayerGraph


class RequirementsRepository(ABC):
    """Abstract interface for requirements data access."""

    # ── HLR/LLR/Test tree traversal ────────────────────────────────

    @abstractmethod
    def get_hlr_tree(self, hlr_uid: str) -> dict:
        """Return the full HLR→LLRs→TestNodes tree with VERIFIES and
        CALLEE targets resolved.

        Returns a dict with ``hlr``, ``llrs`` (list of {llr, tests}),
        where each test has ``verifies_targets`` and ``step_callees``.
        """
        ...

    # ── Scaffold lifecycle ─────────────────────────────────────────

    @abstractmethod
    def find_scaffold_uids(
        self,
        *,
        with_edges: list[str] | None = None,
        without_edges: bool = False,
        parent_is_not_scaffold: bool = False,
        directly_referenced: bool = False,
    ) -> list[str]:
        """Find scaffold node uids matching criteria.

        Args:
            with_edges: Scaffolds that have incoming edges of these types.
            without_edges: Scaffolds with zero relationships (orphans).
            parent_is_not_scaffold: Scaffold children of non-scaffold parents.
            directly_referenced: Scaffolds referenced by AssertionNode or
                TestStepNode via LEFT_OPERAND/RIGHT_OPERAND/CALLEE.
        """
        ...

    @abstractmethod
    def find_scaffold_parents_of_referenced(
        self, referenced_uids: list[str]
    ) -> list[str]:
        """Return uids of scaffold ClassNode parents whose COMPOSES
        children include any of *referenced_uids*."""
        ...

    @abstractmethod
    def retag_scaffold_to_design(self, uid: str) -> None:
        """Change a scaffold node's tags to ``['design']``."""
        ...

    @abstractmethod
    def delete_scaffold(self, uid: str) -> None:
        """DETACH DELETE a scaffold node by uid."""
        ...

    # ── Verification edge management ───────────────────────────────

    @abstractmethod
    def merge_verification(
        self, test_qname: str, target_qname: str
    ) -> None:
        """MERGE a VERIFIES edge from a TestNode to a target."""
        ...

    @abstractmethod
    def replace_callee(
        self, step_qname: str, new_target_qname: str
    ) -> None:
        """Delete old CALLEE edges from a TestStep and MERGE a new
        one to *new_target_qname*."""
        ...

    # ── HLR dependencies ──────────────────────────────────────────

    @abstractmethod
    def merge_depends_on(
        self,
        source_uid: str,
        target_name: str,
        *,
        description: str = "",
    ) -> dict | None:
        """MERGE a DEPENDS_ON edge between HLRs and set the
        relationship description.  Returns the edge info or None."""
        ...

    # ── Unresolved verification queries ────────────────────────────

    @abstractmethod
    def find_unresolved_verifications(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestNodes under *hlr_uid* whose VERIFIES targets
        still have 'scaffold' tags — meaning verification is not
        yet resolved to real design methods."""
        ...

    @abstractmethod
    def find_unresolved_callee_steps(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestStepNodes under *hlr_uid* whose CALLEE targets
        still have 'scaffold' tags."""
        ...
