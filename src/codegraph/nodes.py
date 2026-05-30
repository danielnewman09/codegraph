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


class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs, interfaces,
    enums — that own members and participate in associations.

    The `kind` field refines the specific type. The `layer` field indicates
    origin: 'design' (agent-created), 'as-built' (parsed from code), or
    'dependency' (external library).
    """

    qualified_name: str
    name: str = ""
    kind: Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    refid: str = ""
    description: str = ""
    brief_description: str = ""
    detailed_description: str = ""
    base_classes: list[str] = []
    file_path: str = ""
    line_number: int | None = None
    source: str = ""
    protection: Literal["public", "private", "protected", ""] = ""
    is_final: bool = False
    is_abstract: bool = False

    model_config = {"from_attributes": True}
