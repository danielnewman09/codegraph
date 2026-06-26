"""Pydantic schemas for requirement-mining LLM output.

The miner sends test context (descriptions, steps, assertions, fixtures)
to the LLM and receives back inferred low-level requirements, each mapped
to the test(s) that verify it.

Schema structure::

    MinedRequirements
      ├─ hlr_description: str
      └─ llrs: list[MinedLLR]
            ├─ description: str
            └─ verified_by: list[str]   (TestNode qualified_names)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MinedLLR(BaseModel):
    """A single low-level requirement mined from test evidence.

    Attributes:
        description: The requirement text (e.g. "The ClassNode shall
            support serialization of its composed methods so that
            roundtrip fidelity is maintained").
        verified_by: List of TestNode ``qualified_name`` strings that
            exercise this requirement.  Each name must match an actual
            TestNode in Neo4j.
    """

    description: str = Field(
        ...,
        min_length=10,
        description="Low-level requirement text — one or two sentences."
    )
    verified_by: list[str] = Field(
        default_factory=list,
        description="TestNode qualified_names that verify this LLR."
    )


class MinedRequirements(BaseModel):
    """Complete mined requirements for one code compound (class/interface/enum).

    Attributes:
        hlr_description: The high-level requirement for the compound —
            a summary of everything the class must do, inferred from its
            test suite.
        llrs: Individual low-level requirements, each traced to specific
            tests.
    """

    hlr_description: str = Field(
        ...,
        min_length=10,
        description="High-level requirement for the compound."
    )
    llrs: list[MinedLLR] = Field(
        default_factory=list,
        description="Low-level requirements mined from tests."
    )
