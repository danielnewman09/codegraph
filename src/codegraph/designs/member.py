"""Member-level design models — AttributeNode, MethodNode, EnumValueNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from codegraph.designs.tags import FieldTags, get_fields_by_tags


class AttributeNode(BaseModel):
    """Class/interface attribute in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[Literal["attribute"], FieldTags("llm", "neo4j", "read")] = "attribute"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # LLM sees "type_name"; internally stored as type_signature
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="type_name"),
    ] = ""

    # Neo4j/read only — not exposed to LLM
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


class MethodNode(BaseModel):
    """Class/interface method in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[Literal["method"], FieldTags("llm", "neo4j", "read")] = "method"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # LLM sees "return_type"; internally stored as type_signature
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="return_type"),
    ] = ""

    argsstring: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # Neo4j/read only — not exposed to LLM
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


class EnumValueNode(BaseModel):
    """Enum value in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[Literal["enum_value"], FieldTags("llm", "neo4j", "read")] = "enum_value"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


def _tagged_model_dump(model: BaseModel, tags: set[str] | None, **kwargs) -> dict:
    """Filter model_dump output based on FieldTags annotations.

    Uses the parent class's model_dump to avoid infinite recursion.
    When ``"llm"`` is in *tags*, serialization aliases are used so that
    ``type_signature`` appears as ``type_name`` (AttributeNode) or
    ``return_type`` (MethodNode).
    """
    if tags is None:
        return BaseModel.model_dump(model, **kwargs)

    allowed_names = get_fields_by_tags(type(model), tags)
    use_alias = "llm" in tags
    data = BaseModel.model_dump(model, by_alias=use_alias, **kwargs)

    if use_alias:
        # Map Python field names to their serialization-alias keys
        alias_map: dict[str, str] = {
            name: (field.serialization_alias or name)
            for name, field in type(model).model_fields.items()
        }
        allowed_keys = {alias_map.get(n, n) for n in allowed_names}
        return {k: v for k, v in data.items() if k in allowed_keys}
    else:
        return {k: v for k, v in data.items() if k in allowed_names}
