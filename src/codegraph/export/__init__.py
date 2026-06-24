"""Export and import for codegraph LayerGraphs.

Provides format converters for serializing and deserializing
:class:`~codegraph.graph.LayerGraph` instances:

- **Markdown** — human-readable document with text-based descriptions.
- **PlantUML** — UML class-diagram syntax.
- **JSON** — machine-readable nested serialization.
- **HTML** — interactive Cytoscape.js visualisation.

The unified entry points :func:`export_graph` and :func:`import_graph`
dispatch to the appropriate backend based on the *format* argument.
"""

from codegraph.export.format import export_graph, import_graph
from codegraph.export.markdown import (
    export_markdown,
    import_markdown,
    MarkdownExporter,
    MarkdownImporter,
)
from codegraph.export.plantuml import (
    export_plantuml,
    import_plantuml,
    PlantUMLExporter,
    PlantUMLImporter,
    PlantUMLParseError,
    ParseDiagnostic,
)
from codegraph.export.viz import export_html

__all__ = [
    # Unified format
    "export_graph",
    "import_graph",
    # Markdown
    "export_markdown",
    "import_markdown",
    "MarkdownExporter",
    "MarkdownImporter",
    # PlantUML
    "export_plantuml",
    "import_plantuml",
    "PlantUMLExporter",
    "PlantUMLImporter",
    "PlantUMLParseError",
    "ParseDiagnostic",
    # HTML visualisation
    "export_html",
]