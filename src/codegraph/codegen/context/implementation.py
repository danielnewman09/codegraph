"""Context builder for ImplementationNode (mirrors models/implementation.py).

Implementation context: ``implementation`` (raw body text) + the parent
member/compound qname.  Rendered via the ``cg_body``-style macro in the
``ImplementationNode/implementation.j2`` template.  Design graphs carry
no ImplementationNodes (D8) — only as-built graphs and Phase 3 stub
bodies do.
"""

from __future__ import annotations

NODE_TYPES = ("ImplementationNode",)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the implementation context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"implementation.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
