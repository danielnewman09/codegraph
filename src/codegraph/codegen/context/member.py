"""Context builders for member node types (mirrors models/member.py).

Addresses: ``MemberNode`` (abstract base — dispatch by kind),
``MethodNode``, ``FunctionNode``, ``AttributeNode`` (kinds: attribute /
typedef), ``EnumValueNode``, ``DefineNode``.

Member context contract (spec's render-context section): ``type``,
``kind``, ``name``, ``qualified_name``, ``role`` (constructor / destructor
/ operator / method), ``declaration`` (signature reconciliation, R3),
``params``, ``const``/``static``/``virtual``/``explicit``/``constexpr``/
``inline``, ``body``, ``visibility``, ``brief``/``detailed``.
Attribute adds ``is_static``/``is_const``; enumvalue adds ``initializer``.
"""

from __future__ import annotations

NODE_TYPES = (
    "MemberNode",  # abstract base — dispatch by kind
    "MethodNode",
    "FunctionNode",
    "AttributeNode",
    "EnumValueNode",
    "DefineNode",
)


def build_context(entry, ctx=None):  # noqa: ANN001 — Phase 1 render slice
    """Build the member context dict for *entry*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        f"member.build_context({entry.node.__class__.__name__}): "
        "Phase 1 render slice"
    )
