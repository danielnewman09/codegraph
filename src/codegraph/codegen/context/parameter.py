"""Context builder for ParameterNode (mirrors models/parameter.py).

Parameter context: ``name``, ``type`` (the C++ type string — survives
serialization via the ``node_type`` discriminator fix), ``default_value``,
``position``.  Phase 1 renders params by parsing the member's argsstring
(R6); HAS_PARAMETER-backed params are the Phase 2 source of truth.
"""

from __future__ import annotations

#: Node types this module addresses (mirrors models/parameter.py).
NODE_TYPES: tuple[str, ...] = ("ParameterNode",)


def build_context(entry, state) -> dict | None:
    """Build the parameter context dict for *entry*."""
    node = entry.node
    return {
        "type": "ParameterNode",
        "kind": node.kind or "parameter",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "type": node.type or "",
        "default_value": node.default_value or "",
        "position": node.position or 0,
    }
