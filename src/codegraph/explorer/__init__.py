"""Codegraph Explorer — interactive web visualization of a code graph.

Browse by namespace: a progressive tree of sub-namespaces, classes, and
the high-level requirements that map to them; select a class to view a
zoomable class-scoped diagram and its requirements/tests narration.

Deliberately independent of the retired Cytoscape HTML export — a clean start
per project direction.
"""

from codegraph.explorer.api import GraphSource, LayerGraphSource
from codegraph.explorer.server import load_source, main

__all__ = ["GraphSource", "LayerGraphSource", "load_source", "main"]
