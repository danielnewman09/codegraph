"""UML HTML label builders for Cytoscape node rendering.

Adapted from ticketing_system frontend_migrated/graph/labels.py.
Produces rich HTML labels for compound nodes (class/interface/enum
with members) that are rendered via the cytoscape-node-html-label
extension.

Kind sets are derived from codegraph.constants to avoid duplicating
the canonical kind vocabulary.
"""

from __future__ import annotations

from codegraph.constants import (
    COMPOUND_KINDS as CG_COMPOUND_KINDS_TUPLES,
    MEMBER_KINDS as CG_MEMBER_KINDS_TUPLES,
    TYPE_KINDS as CG_TYPE_KINDS,
)

# ---------------------------------------------------------------------------
# Constants derived from codegraph
# ---------------------------------------------------------------------------

_MEMBER_KIND_KEYS: frozenset[str] = frozenset(k for k, _ in CG_MEMBER_KINDS_TUPLES)

# Kinds that own collapsible members — compounds that render as UML boxes.
_OWNER_KINDS: frozenset[str] = frozenset(k for k, _ in CG_COMPOUND_KINDS_TUPLES)

# Kinds that represent entities — skipped in member compartments.
_ENTITY_KINDS: frozenset[str] = frozenset(
    CG_TYPE_KINDS
    - {"template_class", "abstract_class", "concept", "enum_class", "union", "type_alias"}
)

# Visibility prefix mapping.
_VISIBILITY_PREFIX: dict[str, str] = {"private": "-", "protected": "#", "public": "+"}

# Canonical order for visibility groups in UML labels.
_VISIBILITY_ORDER: list[str] = ["public", "protected", "private"]

# Canonical order for member kinds within a visibility group.
_KIND_ORDER: dict[str, int] = {"attribute": 0, "method": 1, "enum_value": 2}

# Map codegraph kind → canonical UML compartment group.
_CODEGRAPH_KIND_GROUP: dict[str, str] = {
    "variable": "attribute",
    "function": "method",
    "method": "method",
    "enumvalue": "enum_value",
    "define": "attribute",
}

# Map codegraph CompoundNode.kind → stereotype key for _build_uml_html.
_CODEGRAPH_STEREOTYPE_MAP: dict[str, str] = {
    "class": "class",
    "struct": "class",
    "template_class": "class_template",
    "interface": "interface",
    "abstract_class": "class",
    "enum": "enum",
    "enum_class": "enum",
    "union": "class",
}

# HTML label colour scheme.
_MEMBER_COLORS: dict[str, str] = {
    "stereotype": "#a0aec0",
    "classname": "#f7fafc",
    "separator": "#4a5568",
    "vis_public": "#68d391",
    "vis_protected": "#fbd38d",
    "vis_private": "#fc8181",
    "builtin_marker": "#63b3ed",
    "linked_marker": "#d69e2e",
    "dep_marker": "#4fd1c5",
    "type_sig": "#a0aec0",
    "method_name": "#9ae6b4",
    "attr_name": "#fbd38d",
    "enum_val": "#a0aec0",
    "args": "#718096",
}

# Kind-coloured inner border colours for UML boxes.
KIND_BORDER_COLORS: dict[str, str] = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
    "class_template": "#9b59b6",
}

# Builtin / primitive types for type-origin markers.
_BUILTIN_TYPES: frozenset[str] = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t",
    "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
    "str", "int", "float", "bool", "bytes", "list", "dict", "set",
    "tuple", "Optional", "List", "Dict", "Set", "Any", "None",
})

_TEMPLATE_PREFIXES: tuple[str, ...] = ("std::", "boost::", "absl::")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_builtin_type(type_sig: str) -> bool:
    """Check if a type signature refers to a builtin / primitive type."""
    if not type_sig:
        return False
    base = type_sig.strip().rstrip("&*").strip()
    if "<" in base:
        base = base[:base.index("<")].strip()
    return base in _BUILTIN_TYPES or any(base.startswith(p) for p in _TEMPLATE_PREFIXES)


def _type_origin_marker(type_sig: str, member_layer: str) -> str:
    """Return an inline marker indicating where a type originates.

    ●  builtin / primitive (e.g. bool, int, std::string)
    ◆  linked design type (same-project class/interface/enum)
    ▸  dependency / external library type
    """
    if not type_sig:
        return ""
    if _is_builtin_type(type_sig):
        return "\u25cf "   # filled circle
    if member_layer == "dependency":
        return "\u25b8 "   # right-pointing triangle
    return "\u25c6 "   # diamond for design-linked types


def _dedup_by_name(members: list[dict]) -> list[dict]:
    """Deduplicate a list of member dicts by name, keeping first occurrence."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in members:
        if m["name"] not in seen:
            seen.add(m["name"])
            out.append(m)
    return out


def _format_member_html(m: dict, suffix: str = "") -> str:
    """Format a single member as an HTML span with coloured elements.

    Args:
        m: Member dict with at least ``name``, ``visibility``, and
           optionally ``type_signature``, ``argsstring``, ``_kind``, ``layer``.
        suffix: Suffix after the name (e.g. ``'()'`` for methods).

    Returns:
        An HTML string with inline styles for the member line.
    """
    import html as html_mod

    mc = _MEMBER_COLORS
    vis = _VISIBILITY_PREFIX.get(m.get("visibility", ""), " ")
    vis_color = mc.get(f'vis_{m.get("visibility", "public")}', mc["vis_public"])
    vis_html = f'<span style="color:{vis_color}">{html_mod.escape(vis)}</span>'

    kind = m.get("_kind", "")
    name = html_mod.escape(m["name"])
    name_color = (
        mc["method_name"] if kind == "method"
        else mc["attr_name"] if kind == "attribute"
        else mc["enum_val"]
    )
    name_html = f'<span style="color:{name_color}">{name}</span>'

    args = m.get("argsstring", "")
    if args and suffix == "()":
        suffix = html_mod.escape(args)
    else:
        suffix = html_mod.escape(suffix) if suffix else ""
    args_html = f'<span style="color:{mc["args"]}">{suffix}</span>' if suffix else ""

    type_sig = m.get("type_signature", "")
    marker = _type_origin_marker(type_sig, m.get("layer", ""))
    if type_sig:
        if marker == "\u25cf ":
            marker_color = mc["builtin_marker"]
        elif marker == "\u25b8 ":
            marker_color = mc["dep_marker"]
        else:
            marker_color = mc["linked_marker"]
        marker_html = f'<span style="color:{marker_color}">{html_mod.escape(marker)}</span>'
        type_html = f'<span style="color:{mc["type_sig"]}">{html_mod.escape(type_sig)}</span>'
        type_part = f": {marker_html}{type_html}"
    else:
        type_part = ""

    return f"{vis_html} {name_html}{args_html}{type_part}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_uml_html(
    class_name: str,
    by_kind: dict[str, list[dict]],
    *,
    owner_kind: str = "",
    is_dependency: bool = False,
) -> str:
    """Build a coloured HTML label for the cytoscape-node-html-label extension.

    Produces a UML-style box with stereotype, class name, visibility-grouped
    members, and type-origin markers.  Designed to be set as the ``html_label``
    data property on Cytoscape nodes.

    Args:
        class_name: The compound's short name (e.g. ``"CalculatorEngine"``).
        by_kind: Members grouped by canonical UML kind
            (``"attribute"``, ``"method"``, ``"enum_value"``).
        owner_kind: The compound's kind for stereotype selection
            (``"class"``, ``"struct"``, ``"interface"``, ``"enum"``).
        is_dependency: If True, duplicate member names are collapsed.

    Returns:
        An HTML string suitable for use as a Cytoscape node label.
    """
    import html as html_mod

    mc = _MEMBER_COLORS
    lines: list[str] = []

    # Stereotype
    _STEREOTYPES: dict[str, str] = {
        "enum": "\u00ABenumeration\u00BB",
        "interface": "\u00ABinterface\u00BB",
        "class": "\u00ABclass\u00BB",
        "class_template": "\u00ABclass template\u00BB",
    }
    stereotype = _STEREOTYPES.get(owner_kind, "")
    if stereotype:
        lines.append(
            f'<div style="color:{mc["stereotype"]};font-size:9px;text-align:center">'
            f'{html_mod.escape(stereotype)}</div>'
        )

    # Class name
    lines.append(
        f'<div style="color:{mc["classname"]};font-weight:bold;text-align:center">'
        f'{html_mod.escape(class_name)}</div>'
    )

    # Collect all members
    all_members: list[dict] = []
    for kind, members in by_kind.items():
        suf = "()" if kind == "method" else ""
        for m in members:
            all_members.append({**m, "_kind": kind, "_suffix": suf})

    if is_dependency:
        all_members = _dedup_by_name(all_members)

    # Group by visibility
    visibility_groups: dict[str, list[dict]] = {}
    for m in all_members:
        vis = m.get("visibility", "") or "public"
        if vis not in _VISIBILITY_ORDER:
            vis = "public"
        visibility_groups.setdefault(vis, []).append(m)

    separator_html = (
        f'<hr style="border:none;border-top:1px solid {mc["separator"]};margin:2px 0">'
    )
    thin_sep_html = (
        f'<hr style="border:none;border-top:1px dashed {mc["separator"]};margin:1px 0">'
    )

    for vis in _VISIBILITY_ORDER:
        group = visibility_groups.get(vis, [])
        if not group:
            continue
        enum_vals = [m for m in group if m.get("_kind") == "enum_value"]
        attrs = [m for m in group if m.get("_kind") == "attribute"]
        methods = [m for m in group if m.get("_kind") == "method"]
        enum_vals.sort(key=lambda m: m["name"])
        attrs.sort(key=lambda m: m["name"])
        methods.sort(key=lambda m: m["name"])

        lines.append(separator_html)
        if enum_vals:
            for m in enum_vals:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
        if attrs:
            for m in attrs:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
        if methods and (attrs or enum_vals):
            lines.append(thin_sep_html)
        if methods:
            for m in methods:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')

    # Fallback: no visibility grouping
    if not any(visibility_groups.get(v) for v in _VISIBILITY_ORDER) and all_members:
        lines.append(separator_html)
        m_sorted = sorted(
            all_members,
            key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]),
        )
        for m in m_sorted:
            lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')

    kind_border = KIND_BORDER_COLORS.get(owner_kind, "transparent")
    wrapper = (
        '<div style="'
        "font-family:JetBrains Mono,monospace;"
        "font-size:9px;"
        "line-height:1.3;"
        "padding:2px;"
        "white-space:nowrap;"
        "border-radius:5px;"
        f"outline:3px solid {kind_border};"
        'outline-offset:-2px;'
        '">'
    )
    return wrapper + "\n".join(lines) + "</div>"
