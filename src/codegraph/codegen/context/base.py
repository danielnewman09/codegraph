"""Shared helpers for the per-node-type context builders.

Common behaviors every real builder relies on: doc comments from
brief/detailed descriptions, visibility normalization + section
bucketing, deterministic child iteration, display-name resolution for
edge targets, and the node-type sets that mirror ``models/``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

#: Node types handled by context/member.py (incl. abstract MemberNode base).
MEMBER_TYPES: frozenset[str] = frozenset({
    "MemberNode", "MethodNode", "FunctionNode", "AttributeNode",
    "EnumValueNode", "DefineNode",
})

#: Node types handled by context/compound.py (incl. abstract CompoundNode base).
COMPOUND_TYPES: frozenset[str] = frozenset({
    "CompoundNode", "ClassNode", "InterfaceNode", "EnumNode",
    "UnionNode", "ConceptNode", "ModuleNode",
})


def skip_builder(reason: str) -> Callable:
    """Build a declared no-op builder that returns ``None``.

    The returned function is registered in ``BUILDERS`` so the skip is
    explicit and testable — the node type renders nothing and is
    counted in ``CodegenResult.skipped``.
    """

    def _skip(entry, state=None):  # noqa: ANN001 — contract with callers
        return None

    _skip.skip_reason = reason  # type: ignore[attr-defined]
    return _skip


def doc_comment(brief: str, detailed: str = "") -> str:
    """Render brief/detailed descriptions as a ``///`` doc comment block.

    Blank line separates brief from detailed; empty input yields ``""``.
    Exact framing is pinned by the snapshot goldens (render slice).
    """
    brief = (brief or "").strip()
    detailed = (detailed or "").strip()
    lines: list[str] = []
    if brief:
        lines.append(brief)
    if detailed:
        if lines:
            lines.append("")
        lines.append(detailed)
    if not lines:
        return ""
    return "\n".join(f"/// {line}" if line else "///" for line in lines)


def normalize_visibility(visibility: str | None) -> str:
    """Map a stored visibility to the C++ access label ('' → public)."""
    return (visibility or "").strip() or "public"


def ordered_children(entry) -> Iterator[tuple[str, str, object]]:
    """Iterate a CompositeEntry's composed children deterministically.

    Yields ``(node_type, key, child_entry)`` triples in declaration order.
    ``CompositeEntry.children`` is type-bucketed, so iterating the buckets
    directly would move (for example) attributes ahead of methods whenever
    the backend returns those relationship types in a different order.  The
    source spans are the semantic order for indexed code; insertion order is
    preserved for nodes without source locations (such as enum values from
    Doxygen XML and design-layer requirements).
    """
    children = [
        (node_type, key, child_entry)
        for node_type, type_children in entry.children.items()
        for key, child_entry in type_children.items()
    ]

    def source_order(
        indexed_item: tuple[int, tuple[str, str, object]],
    ) -> tuple[int, int, int]:
        index, (_node_type, _key, child_entry) = indexed_item
        node = child_entry.node
        start_line = int(getattr(node, "start_line", 0) or 0)
        line_number = int(getattr(node, "line_number", 0) or 0)
        return (
            0 if start_line or line_number else 1,
            start_line or line_number,
            index,
        )

    for _index, item in sorted(enumerate(children), key=source_order):
        yield item


def bucket_by_visibility(
    items: Iterable[tuple[str, str, object]],
) -> list[tuple[str, list]]:
    """Group ordered child triples by access label.

    Returns ``[(visibility, [items]), ...]`` preserving first-seen
    access order; declaration order is preserved within each bucket.
    Empty visibility is treated as ``public``.
    """
    buckets: dict[str, list] = {}
    order: list[str] = []
    for item in items:
        visibility = normalize_visibility(getattr(item[2].node, "visibility", ""))
        if visibility not in buckets:
            buckets[visibility] = []
            order.append(visibility)
        buckets[visibility].append(item)
    return [(visibility, buckets[visibility]) for visibility in order]


def resolve_display_name(state, key: str) -> str:
    """Resolve a reference target key to a human-readable name.

    Uses the flat index's qualified_name (fallback: name), then the raw
    key.  ``state`` may be None (isolated builder tests).
    """
    if state is not None:
        entry = state.flat.get(key)
        if entry is not None:
            qn = getattr(entry.node, "qualified_name", "") or ""
            if qn:
                return qn
            name = getattr(entry.node, "name", "") or ""
            if name:
                return name
    return key
