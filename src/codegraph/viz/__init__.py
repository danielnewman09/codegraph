"""Cytoscape.js visualization for codegraph LayerGraphs.

Provides LayerGraph → Cytoscape element transform, UML HTML label
builders, Cytoscape stylesheet generation, and the ``export_html()``
public API for writing self-contained HTML graph visualisations.
"""

from codegraph.viz.api import export_html, main

__all__ = [
    "layer_graph_to_cytoscape",
    "KIND_COLORS",
    "EDGE_COLORS",
    "cy_stylesheet",
    "export_html",
    "main",
]


def __getattr__(name: str):
    """Lazy-import submodules so intermediate tasks don't fail on missing siblings."""
    if name == "layer_graph_to_cytoscape":
        from codegraph.viz.transform import layer_graph_to_cytoscape as _fn
        return _fn
    if name == "KIND_COLORS":
        from codegraph.viz.styles import KIND_COLORS as _kc
        return _kc
    if name == "EDGE_COLORS":
        from codegraph.viz.styles import EDGE_COLORS as _ec
        return _ec
    if name == "cy_stylesheet":
        from codegraph.viz.styles import cy_stylesheet as _cs
        return _cs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
