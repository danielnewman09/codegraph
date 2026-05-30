"""Node models for the Neo4j codebase graph.

Each class corresponds to a Neo4j node label and uses Pydantic for
validation and serialization. All fields have sensible defaults
unless marked as required.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FileNode(BaseModel):
    """A source file in the codebase (:File in Neo4j).

    Unique by `refid` (Doxygen refid).
    """

    refid: str
    name: str = ""
    path: str = ""
    language: str = ""
    source: str = ""

    model_config = {"from_attributes": True}


class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
    """

    qualified_name: str
    name: str = ""
    kind: Literal["namespace", "package", "module"] = "namespace"
    layer: Literal["design", "as-built", "dependency"] = "design"
    refid: str = ""
    description: str = ""
    source: str = ""

    model_config = {"from_attributes": True}
