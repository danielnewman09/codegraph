"""File node for the Neo4j codebase graph (:File label)."""

from __future__ import annotations

from pydantic import BaseModel


class FileNode(BaseModel):
    """A source file in the codebase (:File in Neo4j).

    Uniquely identified by ``refid`` (Doxygen reference-id). All other
    entity nodes (:Namespace, :Compound, :Member) reference their
    originating file through a CONTAINS relationship.
    """

    #: Doxygen reference-id that uniquely identifies this file
    #: (e.g. ``"main_8cpp"``). Required — this is the Neo4j uniqueness
    #: constraint key.
    refid: str

    #: Human-readable base filename (e.g. ``"main.cpp"``,
    #: ``"calculator.h"``). Used for display and full-text search.
    name: str = ""

    #: Absolute or project-relative path to the source file on disk
    #: (e.g. ``"/src/main.cpp"``, ``"include/calc/calculator.h"``).
    path: str = ""

    #: Programming language of the file as a lowercase string
    #: (e.g. ``"c++"``, ``"python"``, ``"java"``). Used for
    #: syntax-aware rendering and filtering.
    language: str = ""

    #: Provenance label identifying the source of truth (e.g. ``"msd"``,
    #: ``"stdlib"``, ``"agent"``). Useful for filtering and auditing.
    source: str = ""

    model_config = {"from_attributes": True}
