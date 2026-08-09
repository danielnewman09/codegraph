"""Context builder for FileNode (mirrors models/file.py).

File context contract (spec's render-context section): ``type``, ``path``,
``guard``, ``language`` (normalized lowercase, ``normalize_language``),
``includes`` (INCLUDES edges), ``forward_decls`` (Phase 2: DEPENDS_ON),
``namespaces`` (nesting blocks), and the document-level ``brief``/``detailed``.
"""

from __future__ import annotations

NODE_TYPES = ("FileNode",)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the file context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"file.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
