"""Edge definitions for the Neo4j codebase graph.

CodebaseEdge represents a directed relationship between two codebase
nodes. Stored in Neo4j as a typed relationship with the predicate name
uppercased (e.g. 'composes' → COMPOSES).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel

from codegraph.constants import PREDICATES
from codegraph.designs.tags import FieldTags


class CodebaseEdge(BaseModel):
    """A directed relationship between two codebase nodes.

    Stored in Neo4j as a typed relationship with the predicate name
    uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
    predicate + object.
    """

    subject_qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    predicate: Annotated[str, FieldTags("llm", "neo4j", "read")]  # Must be one of PREDICATES
    object_qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    mechanism: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""  # Container type (e.g. "std::vector" for aggregates)
    position: Annotated[int | None, FieldTags("neo4j")] = None  # Position for type_argument edges (0-based)
    name: Annotated[str, FieldTags("neo4j")] = ""  # Parameter name for template_param edges
    display_name: Annotated[str, FieldTags("neo4j", "read")] = ""  # Alias display name
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""  # Human-readable description

    model_config = {"from_attributes": True}
