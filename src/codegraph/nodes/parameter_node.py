"""Parameter node for the Neo4j codebase graph (:Parameter label)."""

from __future__ import annotations

from pydantic import BaseModel


class ParameterNode(BaseModel):
    """A function/method parameter (:Parameter in Neo4j).

    Connected to its owning member via a HAS_ARGUMENT edge. Each
    parameter carries its positional index, name, type, and optional
    default value.
    """

    #: Zero-based position in the parameter list. Required.
    position: int

    #: Parameter name as it appears in source (e.g. ``"x"``, ``"epsilon"``).
    #: Required.
    name: str

    #: Declared type of the parameter (e.g. ``"int"``, ``"double"``,
    #: ``"const std::string&"``). Defaults to ``""`` for untyped or
    #: unknown parameters.
    type: str = ""

    #: Default value expression as a string (e.g. ``"0"``, ``"1e-6"``,
    #: ``"{}"``). Empty string if no default value is specified.
    default_value: str = ""

    #: Doxygen reference-id of the owning Member. Used to link back to
    #: the parent MemberNode via a HAS_ARGUMENT edge.
    member_refid: str = ""

    model_config = {"from_attributes": True}
