"""Node models for the Neo4j codebase graph.

Each class corresponds to a Neo4j node label and uses Pydantic for
validation and serialization. All fields have sensible defaults
unless marked as required.
"""

from __future__ import annotations

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
