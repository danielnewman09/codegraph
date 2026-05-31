"""Compound-level design models — DiagramNode, ClassNode, InterfaceNode, EnumNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.member import (
    AttributeNode, MethodNode, EnumValueNode, _tagged_model_dump,
)
from codegraph.designs.tags import FieldTags


class DiagramNode(BaseModel):
    """Common fields for every diagram node."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # LLM-visible
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # Neo4j / read only
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    type_signature: Annotated[str, FieldTags("neo4j", "read")] = ""
    argsstring: Annotated[str, FieldTags("neo4j", "read")] = ""
    definition: Annotated[str, FieldTags("neo4j", "read")] = ""
    source_type: Annotated[str, FieldTags("neo4j", "read")] = ""
    source: Annotated[str, FieldTags("neo4j", "read")] = ""
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_abstract: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_final: Annotated[bool, FieldTags("neo4j", "read")] = False

    # Ticketing extensions — tagged separately
    specialization: Annotated[str, FieldTags("ticketing")] = ""
    is_intercomponent: Annotated[bool, FieldTags("ticketing")] = False
    implementation_status: Annotated[str, FieldTags("ticketing")] = "designed"
    test_file: Annotated[str, FieldTags("ticketing")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)


class ClassNode(DiagramNode):
    """Class or struct in the class diagram."""

    kind: Annotated[Literal["class"], FieldTags("llm", "neo4j", "read")] = "class"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    inherits_from: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []
    realizes: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []
    attributes: Annotated[list[AttributeNode], FieldTags("llm", "neo4j", "read")] = []
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "attributes" in data:
            data["attributes"] = [
                a.model_dump(tags=tags, **kwargs) for a in self.attributes
            ]
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) for m in self.methods
            ]
        return data


class InterfaceNode(DiagramNode):
    """Interface / abstract class in the class diagram."""

    kind: Annotated[Literal["interface"], FieldTags("llm", "neo4j", "read")] = "interface"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) for m in self.methods
            ]
        return data


class EnumNode(DiagramNode):
    """Enum in the class diagram."""

    kind: Annotated[Literal["enum"], FieldTags("llm", "neo4j", "read")] = "enum"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    values: Annotated[list[EnumValueNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "values" in data:
            data["values"] = [
                v.model_dump(tags=tags, **kwargs) for v in self.values
            ]
        return data
