"""Edge definitions for the Neo4j codebase graph.

CodebaseEdge represents a directed relationship between two codebase
nodes. Stored in Neo4j as a typed relationship with the predicate name
uppercased (e.g. 'composes' → COMPOSES).
"""

from __future__ import annotations

from pydantic import BaseModel

from codegraph.constants import PREDICATES


class CodebaseEdge(BaseModel):
    """A directed relationship between two codebase nodes.

    Stored in Neo4j as a typed relationship with the predicate name
    uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
    predicate + object.
    """

    subject_qualified_name: str
    predicate: str  # Must be one of PREDICATES
    object_qualified_name: str
    mechanism: str = ""           # Container type (e.g. "std::vector" for aggregates)
    position: int | None = None   # Position for type_argument edges (0-based)
    name: str = ""                # Parameter name for template_param edges
    display_name: str = ""        # Alias display name (e.g. "std::string" for std::basic_string)
    description: str = ""          # Human-readable description of the relationship

    model_config = {"from_attributes": True}
