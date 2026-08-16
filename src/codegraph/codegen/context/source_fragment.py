"""Context builder for verbatim as-built residual source spans."""

from __future__ import annotations

NODE_TYPES = ("SourceFragmentNode",)


def build_context(entry, state) -> dict:
    node = entry.node
    return {
        "type": "SourceFragmentNode",
        "kind": node.kind or "unassigned_source_fragment",
        "qualified_name": (
            f"{getattr(node, 'placement', '')}::{node.qualified_name}"
            if getattr(node, "placement", "") else node.qualified_name or ""
        ),
        "placement": getattr(node, "placement", "") or "",
        "text": getattr(node, "text", "") or "",
        "start_line": getattr(node, "start_line", 0) or 0,
        "end_line": getattr(node, "end_line", 0) or 0,
    }
