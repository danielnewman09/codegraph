"""Sphinx configuration for codegraph API metadata extraction."""

import sys
from pathlib import Path

# Make the source package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
# Make the custom builders importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = "codegraph"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "_builders.json_api",
]

# No theme needed — we only build JSON
html_theme = "basic"