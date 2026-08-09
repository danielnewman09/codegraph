"""Context builder for NamespaceNode (mirrors models/namespace.py).

Namespace context: ``name``, ``qualified_name``, ``blocks`` (the nested
compound/namespace contexts this namespace composes).  Rendered via
``namespace_open.j2`` / ``namespace_close.j2``.
"""

from __future__ import annotations

NODE_TYPES = ("NamespaceNode",)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the namespace context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"namespace.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
