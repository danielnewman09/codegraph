"""Context builder for ParameterNode (mirrors models/parameter.py).

Parameter context: ``name``, ``type`` (the C++ type string — survives
serialization via the ``node_type`` discriminator fix), ``default_value``,
``position``.  Phase 1 renders params by parsing the member's argsstring
(R6); HAS_PARAMETER-backed params are the Phase 2 source of truth.
"""

from __future__ import annotations

NODE_TYPES = ("ParameterNode",)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the parameter context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"parameter.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
