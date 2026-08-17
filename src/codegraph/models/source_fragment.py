"""Residual source-fragment model for as-built round-trip fidelity."""

from __future__ import annotations

from codegraph.models.descriptors import Property
from codegraph.models.tags import CodeGraphNode


class SourceFragmentNode(CodeGraphNode):
    """Exact source span not owned by a more structured graph node.

    A fragment is the explicit remainder of a source file after indexing has
    assigned spans to files, includes, namespaces, compounds, and members.
    It is not an error or a macro special case: it is the lossless fallback
    for syntax outside the current semantic data model.
    """
    qualified_name = Property(str, default="", index=True)
    kind = Property(str, default="unassigned_source_fragment")
    file_path = Property(str, default="")
    start_line = Property(int, default=0)
    end_line = Property(int, default=0)
    placement = Property(str, default="")
    text = Property(str, default="")
    source = Property(str, default="")
    tags = Property(list, default=[])

    _identity_fields = ("file_path", "start_line", "end_line")
    _llm_fields = {
        "qualified_name", "kind", "file_path", "start_line", "end_line",
        "placement", "text", "source",
    }
