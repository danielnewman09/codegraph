"""Context builders for compound node types (mirrors models/compound.py).

Addresses: ``CompoundNode`` (abstract base — dispatch by kind),
``ClassNode`` (kinds: class / struct / type_parameter), ``InterfaceNode``,
``EnumNode``, ``UnionNode``, ``ConceptNode``, ``ModuleNode``.

Compound context contract (from the spec's render-context section):
``type``, ``kind``, ``name``, ``qualified_name``, ``visibility``,
``brief``/``detailed``, ``is_final``, ``is_abstract``, ``template_params``,
``bases`` (INHERITS_FROM), ``interfaces`` (REALIZES), ``sections``
(COMPOSES children grouped by visibility), ``file_path``/``line_number``.
"""

from __future__ import annotations

NODE_TYPES = (
    "CompoundNode",  # abstract base — dispatch by kind
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ConceptNode",
    "ModuleNode",
)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the compound context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"compound.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
