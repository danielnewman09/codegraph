"""Color constants and Cytoscape stylesheet builder for graph visualization.

Adapted from ticketing_system frontend_migrated/theme.py.  Produces a
Cytoscape stylesheet array suitable for serialisation into a static
HTML file.  Drops NiceGUI-specific features and the deprecated
``background-blacken`` property (removed in Cytoscape 3.15+).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

KIND_COLORS: dict[str, str] = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
    "method": "#2ecc71",
    "attribute": "#d4a843",
    "module": "#1abc9c",
    "function": "#27ae60",
    "constant": "#7f8c8d",
    "primitive": "#95a5a6",
    "type_alias": "#e67e22",
    "variable": "#d4a843",
    "type_parameter": "#a0aec0",
    "namespace": "#1abc9c",
    "concept": "#9b59b6",
    "union": "#e67e22",
    "define": "#a0aec0",
    "test": "#e91e63",
    "assertion": "#ff9800",
    "test_step": "#00bcd4",
    "test_fixture": "#8e24aa",
}

EDGE_COLORS: dict[str, str] = {
    "INHERITS_FROM": "#9b59b6",
    "IMPLEMENTS": "#3b82f6",
    "REALIZES": "#3b82f6",
    "COMPOSES": "#7f8c8d",
    "DEPENDS_ON": "#e59866",
    "REFERENCES": "#f0b27a",
    "INVOKES": "#58d68d",
    "HAS_ARGUMENT": "#5dade2",
    "RETURNS": "#58d68d",
    "DEFINED_IN": "#7f8c8d",
    "ASSOCIATES": "#f0b27a",
    "AGGREGATES": "#af7ac5",
    "SPECIALIZES": "#9b59b6",
    "ENFORCES_CONCEPT": "#9b59b6",
    "TEMPLATE_PARAM": "#9b59b6",
    "VERIFIES": "#e91e63",
    "LEFT_OPERAND": "#ff9800",
    "RIGHT_OPERAND": "#ff9800",
    "CALLEE": "#00bcd4",
    "CALLER": "#00bcd4",
    "OF_TYPE": "#26a69a",
    "CHECKED_BY": "#ff9800",
    "default": "#555",
}

# Background colours for the graph canvas and UML box fills.
_BG_BASE = "#1a1a2e"
_BG_SURFACE = "#1e293b"

# Helper: darken a hex colour by a factor (0.0 = black, 1.0 = unchanged).
def _darken(hex_color: str, factor: float = 0.7) -> str:
    """Return a darkened version of *hex_color* (e.g. '#4a90d9').

    Args:
        hex_color: A 6-digit hex colour with leading ``#``.
        factor: Multiplier applied to each RGB channel (0.0–1.0).

    Returns:
        A 6-digit hex colour string.
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def cy_stylesheet(*, size: str = "large") -> list[dict]:
    """Return a Cytoscape stylesheet as a list of style dicts.

    Args:
        size: ``"large"`` (full-page graph) or ``"small"`` (compact).

    Returns:
        A list of Cytoscape style objects suitable for
        ``json.dumps()`` and embedding in a static HTML page.
    """
    if size == "large":
        node_w, node_h, font, txt_max, txt_margin = 40, 40, 10, 80, 4
        pad_members, member_font, member_txt_max = 2, 9, 280
        edge_font = 8
        ns_font, ns_pad = 11, 20
    else:
        node_w, node_h, font, txt_max, txt_margin = 30, 30, 9, 70, 3
        pad_members, member_font, member_txt_max = 2, 8, 220
        edge_font = 7
        ns_font, ns_pad = 10, 16

    ec = EDGE_COLORS

    # UML box defaults — actual dimensions set by post-render DOM
    # measurement in the template (see graph.html.j2 setTimeout block).
    _uml_default_w, _uml_default_h = 200, 60

    styles: list[dict] = []

    # -- Non-member nodes (circles) --
    for layer, border_style, border_color in [
        ("design", "dashed", "#aaa"),
        ("dependency", "dotted", "#009688"),
        ("as-built", "solid", "#3b82f6"),
    ]:
        styles.append({
            "selector": f'node[layer="{layer}"][!has_members]',
            "style": {
                "label": "data(label)",
                "background-color": "#666",
                "color": "#ddd" if layer == "design" else "#a0aec0",
                "text-valign": "bottom",
                "text-halign": "center",
                "font-size": f"{font}px",
                "width": node_w,
                "height": node_h,
                "border-width": 2,
                "border-style": border_style,
                "border-color": border_color,
                "text-wrap": "ellipsis",
                "text-max-width": f"{txt_max}px",
                "text-margin-y": txt_margin,
            },
        })

    # -- UML box nodes (compounds with members) --
    for layer, border_style, border_color, bg_color in [
        ("design", "dashed", "#4a5568", _BG_SURFACE),
        ("as-built", "solid", "#3b82f6", _BG_SURFACE),
        ("dependency", "double", "#009688", "#1a2332"),
    ]:
        styles.append({
            "selector": f'node[has_members="true"][layer="{layer}"]',
            "style": {
                "label": "",
                "shape": "roundrectangle",
                "text-valign": "center",
                "text-halign": "center",
                "text-wrap": "wrap",
                "text-max-width": f"{member_txt_max}px",
                "font-size": f"{member_font}px",
                "font-family": '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
                "text-justification": "left",
                "width": _uml_default_w,
                "height": _uml_default_h,
                "padding": "2px",
                "border-style": border_style,
                "border-width": 4 if layer == "design" else 3,
                "border-color": border_color,
                "background-color": bg_color,
                "color": "#e2e8f0" if layer == "design" else "#b0bec5",
                "text-margin-y": 0,
            },
        })

    # -- Namespace containers --
    styles.append({
        "selector": 'node[is_namespace="true"]',
        "style": {
            "shape": "roundrectangle",
            "background-color": _BG_BASE,
            "background-opacity": 0.6,
            "border-width": 2,
            "border-style": "dashed",
            "border-color": "#1abc9c",
            "label": "data(label)",
            "color": "#1abc9c",
            "text-valign": "top",
            "text-halign": "center",
            "font-size": f"{ns_font}px",
            "font-weight": "bold",
            "padding": f"{ns_pad}px",
            "text-margin-y": -4,
        },
    })

    # -- Kind-specific fills (overrides the default #666 background) --
    for kind, color in KIND_COLORS.items():
        for layer, darken_factor in [("design", 1.0), ("as-built", 0.7), ("dependency", 0.75)]:
            fill = color if darken_factor == 1.0 else _darken(color, darken_factor)
            styles.append({
                "selector": f'node[kind="{kind}"][layer="{layer}"][!has_members]',
                "style": {"background-color": fill},
            })

    # -- Selected node --
    styles.append({
        "selector": ":selected",
        "style": {
            "border-width": 4,
            "border-color": "#f1c40f",
            "overlay-padding": 5,
            "overlay-color": "#f1c40f",
            "overlay-opacity": 0.35,
        },
    })

    # -- Edges (base) --
    styles.append({
        "selector": "edge",
        "style": {
            "label": "data(label)",
            "width": 1.5,
            "line-color": ec["default"],
            "target-arrow-color": ec["default"],
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "font-size": f"{edge_font}px",
            "color": "#718096",
            "text-rotation": "autorotate",
            "text-outline-color": _BG_BASE,
            "text-outline-width": 2,
            "text-outline-opacity": 0.8,
        },
    })

    # -- Edge-type-specific styles --
    _EDGE_STYLE_OVERRIDES: dict[str, dict] = {
        "INHERITS_FROM": {"line-style": "solid", "line-color": ec["INHERITS_FROM"],
                          "target-arrow-color": ec["INHERITS_FROM"],
                          "target-arrow-shape": "triangle-tee", "width": 2},
        "IMPLEMENTS": {"line-style": "dotted", "line-color": ec["IMPLEMENTS"],
                       "target-arrow-color": ec["IMPLEMENTS"], "width": 1},
        "REALIZES": {"line-style": "dotted", "line-color": ec["REALIZES"],
                     "target-arrow-color": ec["REALIZES"], "width": 1},
        "HAS_ARGUMENT": {"line-style": "dashed", "line-color": ec["HAS_ARGUMENT"],
                         "target-arrow-color": ec["HAS_ARGUMENT"],
                         "target-arrow-shape": "diamond", "width": 1.5},
        "RETURNS": {"line-style": "dashed", "line-color": ec["RETURNS"],
                    "target-arrow-color": ec["RETURNS"],
                    "target-arrow-shape": "triangle-cross", "width": 1.5},
        "REFERENCES": {"line-style": "dashed", "line-color": ec["REFERENCES"],
                       "target-arrow-color": ec["REFERENCES"], "width": 1.5},
        "DEPENDS_ON": {"line-style": "dashed", "line-color": ec["DEPENDS_ON"],
                       "target-arrow-color": ec["DEPENDS_ON"], "width": 1.5},
        "INVOKES": {"line-style": "dashed", "line-color": ec["INVOKES"],
                    "target-arrow-color": ec["INVOKES"], "width": 1.5},
        "AGGREGATES": {"line-style": "solid", "line-color": ec["AGGREGATES"],
                       "target-arrow-color": ec["AGGREGATES"],
                       "target-arrow-shape": "diamond", "width": 2},
        "SPECIALIZES": {"line-style": "solid", "line-color": ec["SPECIALIZES"],
                        "target-arrow-color": ec["SPECIALIZES"],
                        "target-arrow-shape": "triangle-tee", "width": 2},
        "TEMPLATE_PARAM": {"line-style": "dashed", "line-color": ec["TEMPLATE_PARAM"],
                           "target-arrow-color": ec["TEMPLATE_PARAM"], "width": 1},
        "VERIFIES": {"line-style": "solid", "line-color": ec["VERIFIES"],
                      "target-arrow-color": ec["VERIFIES"],
                      "target-arrow-shape": "triangle", "width": 2},
        "LEFT_OPERAND": {"line-style": "dotted", "line-color": ec["LEFT_OPERAND"],
                         "target-arrow-color": ec["LEFT_OPERAND"], "width": 1},
        "RIGHT_OPERAND": {"line-style": "dotted", "line-color": ec["RIGHT_OPERAND"],
                          "target-arrow-color": ec["RIGHT_OPERAND"], "width": 1},
        "CALLEE": {"line-style": "dashed", "line-color": ec["CALLEE"],
                    "target-arrow-color": ec["CALLEE"], "width": 1.5},
        "CALLER": {"line-style": "dashed", "line-color": ec["CALLER"],
                    "target-arrow-color": ec["CALLER"],
                    "target-arrow-shape": "circle", "width": 1.5},
        "OF_TYPE": {"line-style": "dotted", "line-color": ec["OF_TYPE"],
                    "target-arrow-color": ec["OF_TYPE"],
                    "target-arrow-shape": "diamond", "width": 1},
        "CHECKED_BY": {"line-style": "dashed", "line-color": ec["CHECKED_BY"],
                      "target-arrow-color": ec["CHECKED_BY"], "width": 1},
    }

    for label, override in _EDGE_STYLE_OVERRIDES.items():
        styles.append({
            "selector": f'edge[label="{label}"]',
            "style": override,
        })

    return styles
