"""Shared helpers for the per-node-type context builders.

Common behaviors that every real builder relies on: doc comments from
brief/detailed descriptions, visibility grouping of a compound's
composed children, guard computation (delegates to
``codegraph.codegen.signature``), and the ``declaration`` assembly for
members (delegates to the signature reconciliation rule).
"""

from __future__ import annotations

from collections.abc import Callable


def skip_builder(reason: str) -> Callable:
    """Build a declared no-op builder that returns ``None``.

    The returned function is registered in ``BUILDERS`` so the skip is
    explicit and testable — the node type renders nothing and is
    counted in ``CodegenResult.skipped``.
    """

    def _skip(entry, ctx=None):  # noqa: ANN001, ANN002 — contract with callers
        return None

    _skip.skip_reason = reason  # type: ignore[attr-defined]
    return _skip


def doc_comment(brief: str, detailed: str = "") -> str:
    """Render brief/detailed descriptions as a ``///`` doc comment block.

    Phase 1 render slice: exact comment framing (line-wrapping, blank
    lines between brief and detailed) is pinned by the snapshot goldens.
    """
    raise NotImplementedError("doc_comment: Phase 1 render slice")


def group_by_visibility(children) -> list[dict]:
    """Group a compound's composed children into access sections.

    Returns ``[{"access": "public", "members": [...]}, ...]`` preserving
    declaration order within each access group (R4).  Empty visibility
    is treated as ``public``.
    """
    raise NotImplementedError("group_by_visibility: Phase 1 render slice")
