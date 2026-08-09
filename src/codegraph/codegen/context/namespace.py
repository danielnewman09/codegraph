"""Context builder for NamespaceNode (mirrors models/namespace.py).

Namespace context: ``name``, ``qualified_name``, ``kind``,
``description``, ``blocks`` (the composed compound / member / nested
namespace contexts, in declaration order).  Rendered via
``namespace_open.j2`` / ``namespace_close.j2``.
"""

from __future__ import annotations

from codegraph.codegen.context import base, compound, member

#: Node types this module addresses (mirrors models/namespace.py).
NODE_TYPES: tuple[str, ...] = ("NamespaceNode",)


def build_context(entry, state) -> dict | None:
    """Build the namespace context dict for *entry*."""
    node = entry.node
    blocks: list[dict] = []
    for child_type, _key, child in base.ordered_children(entry):
        if child_type in base.COMPOUND_TYPES:
            ctx = compound.build_context(child, state)
        elif child_type in base.MEMBER_TYPES:
            ctx = member.build_context(child, state)
        elif child_type == "NamespaceNode":
            ctx = build_context(child, state)
        else:
            ctx = None
        if ctx is not None:
            blocks.append(ctx)
    return {
        "type": "NamespaceNode",
        "kind": node.kind or "namespace",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "description": node.description or "",
        "blocks": blocks,
    }
