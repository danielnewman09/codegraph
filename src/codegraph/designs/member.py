"""Member-level design models — AttributeNode, MethodNode, EnumValueNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from codegraph.designs.tags import FieldTags, get_fields_by_tags


class AttributeNode(BaseModel):
    """Class/interface attribute in the class diagram.

    Represents a member variable or data field on a class or interface.
    When serialized for LLM consumption (``tags={"llm"}``), the
    ``type_signature`` field is aliased as ``type_name`` for clarity.
    """

    #: Short, unqualified name (e.g. ``"count"``, ``"buffer"``).
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name including the owning class
    #: (e.g. ``"calc::Calculator::count"``).
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category. Always ``"attribute"`` for this node type.
    kind: Annotated[Literal["attribute"], FieldTags("llm", "neo4j", "read")] = "attribute"

    #: One-line summary description of what this attribute represents.
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Access specifier / visibility level. One of ``"public"``,
    #: ``"private"``, ``"protected"``, or ``""`` (unknown / default).
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Declared type of this attribute (e.g. ``"int"``, ``"std::vector<int>"``).
    #: When serializing for LLMs this field appears as ``type_name``
    #: via its ``serialization_alias``.
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="type_name"),
    ] = ""

    #: Fully-qualified name of the owning class or interface
    #: (e.g. ``"calc::Calculator"``). Not visible to LLMs — used
    #: internally for parent-child linking.
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Foreign key to the owning ticketing-system component. ``None``
    #: when not yet assigned.
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Provenance layer — ``"design"``, ``"as-built"``, or
    #: ``"dependency"``. Defaults to ``"design"`` since this model
    #: lives in the design layer.
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


class MethodNode(BaseModel):
    """Class/interface method in the class diagram.

    Represents a member function or method on a class or interface.
    Carries the full signature (return type, arguments) and behavioral
    modifiers (virtual, static, const). When serialized for LLM
    consumption (``tags={"llm"}``), the ``type_signature`` field is
    aliased as ``return_type`` for clarity.
    """

    #: Short, unqualified name (e.g. ``"add"``, ``"compute"``).
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name including the owning class
    #: (e.g. ``"calc::Calculator::add"``).
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category. Always ``"method"`` for this node type.
    kind: Annotated[Literal["method"], FieldTags("llm", "neo4j", "read")] = "method"

    #: One-line summary description of what this method does.
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Access specifier / visibility level. One of ``"public"``,
    #: ``"private"``, ``"protected"``, or ``""`` (unknown / default).
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Return type of this method (e.g. ``"int"``, ``"void"``,
    #: ``"std::string"``). When serializing for LLMs this field appears
    #: as ``return_type`` via its ``serialization_alias``.
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="return_type"),
    ] = ""

    #: Argument string including parentheses (e.g. ``"(int a, int b)"``).
    #: Empty string for methods with no parameters.
    argsstring: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name of the owning class or interface
    #: (e.g. ``"calc::Calculator"``). Not visible to LLMs — used
    #: internally for parent-child linking.
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""

    #: Foreign key to the owning ticketing-system component. ``None``
    #: when not yet assigned.
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None

    #: Provenance layer — ``"design"``, ``"as-built"``, or
    #: ``"dependency"``. Defaults to ``"design"`` since this model
    #: lives in the design layer.
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    #: ``True`` if the method is declared ``virtual`` (C++). Virtual
    #: methods can be overridden by derived classes.
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the method is declared ``static``. Static methods
    #: belong to the class rather than any instance.
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False

    #: ``True`` if the method is ``const``-qualified (C++). Indicates
    #: the method does not mutate instance state.
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


class EnumValueNode(BaseModel):
    """Enum value in the class diagram.

    Represents a single named constant within an enumeration type
    (e.g. ``"RED"`` in ``enum Color { RED, GREEN, BLUE }``).
    """

    #: Short, unqualified name of this enum value (e.g. ``"RED"``).
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name including the owning enum
    #: (e.g. ``"color::Color::RED"``).
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Semantic category. Always ``"enum_value"`` for this node type.
    kind: Annotated[Literal["enum_value"], FieldTags("llm", "neo4j", "read")] = "enum_value"

    #: One-line summary description of what this enum constant
    #: represents (e.g. ``"Primary red color channel"``).
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    #: Fully-qualified name of the owning enum
    #: (e.g. ``"color::Color"``). Not visible to LLMs — used
    #: internally for parent-child linking.
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


def _tagged_model_dump(model: BaseModel, tags: set[str] | None, **kwargs) -> dict:
    """Filter model_dump output based on :class:`FieldTags` annotations.

    This is the core serialization mechanism shared by all design
    models. It uses :func:`get_fields_by_tags` to determine which
    fields belong to the requested tags, then filters the dict.

    Uses the parent ``BaseModel.model_dump`` to avoid infinite
    recursion (since subclasses override ``model_dump`` to call this
    function).

    When ``"llm"`` is in *tags*, serialization aliases are used so that
    ``type_signature`` appears as ``type_name`` (:class:`AttributeNode`)
    or ``return_type`` (:class:`MethodNode`). This gives LLMs
    friendlier field names while keeping internal field names consistent
    across the codebase.

    Args:
        model: The Pydantic model instance to dump.
        tags: Set of field tags to include (e.g. ``{"llm", "neo4j"}``).
              When ``None``, all fields are returned unfiltered.
        **kwargs: Forwarded to ``BaseModel.model_dump``.

    Returns:
        A dict with only the fields whose :class:`FieldTags` intersect
        the requested *tags* set.
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
