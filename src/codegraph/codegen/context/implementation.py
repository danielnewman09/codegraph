"""Context builder for ImplementationNode (mirrors models/implementation.py).

Implementation context: ``implementation`` (raw body text) + the parent
member/compound qname.  Rendered via the ``ImplementationNode/
implementation.j2`` template.  Design graphs carry no ImplementationNodes
(D8) — only as-built graphs and Phase 3 stub bodies do.
"""

from __future__ import annotations

#: Node types this module addresses (mirrors models/implementation.py).
NODE_TYPES: tuple[str, ...] = ("ImplementationNode",)


def build_context(entry, state) -> dict | None:
    """Build the implementation context dict for *entry*."""
    node = entry.node
    return {
        "type": "ImplementationNode",
        "kind": node.kind or "implementation",
        "qualified_name": node.qualified_name or "",
        "implementation": node.implementation or "",
    }
