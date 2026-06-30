"""Pydantic schemas for requirement-mining LLM output.

Three schemas are defined:

1. :class:`MinedRequirements` — used by :class:`LLRMiner` to mine
   low-level requirements from test evidence for a single compound.

2. :class:`MinedCompositeHLR` — used by :class:`CompositeHLRMiner` to
   synthesize a composite technical requirement from a cluster of
   existing per-compound HLRs.

3. :class:`MinedComponents` — used by :class:`ComponentMiner` to cluster
   all HLRs into the minimal set of functional Components, where each
   Component represents a business-level requirement.

Schema structure::

    MinedRequirements
      ├─ hlr_description: str
      └─ llrs: list[MinedLLR]
            ├─ description: str
            └─ verified_by: list[str]   (TestNode qualified_names)

    MinedCompositeHLR
      ├─ description: str
      ├─ rationale: str
      └─ child_hlr_names: list[str]   (HLR name strings)

    MinedComponents
      └─ components: list[MinedComponent]
            ├─ name: str
            ├─ description: str
            ├─ namespace: str
            └─ hlr_names: list[str]   (HLR name strings)
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


class MinedCompositeHLR(BaseModel):
    """A composite/technical HLR mined from a cluster of per-compound HLRs.

    Produced by :class:`CompositeHLRMiner` when grouping multiple
    per-compound HLRs (typically within the same namespace) into a single
    abstract technical requirement.

    Attributes:
        description: The composite technical requirement text —
            describes what the subsystem (the cluster of classes) shall
            do, abstracting the individual per-compound HLRs.
        rationale: Why these HLRs were grouped under this composite
            requirement — the shared architectural concern.
        child_hlr_names: List of HLR ``name`` strings being composed.
            Each name must match an existing HLR node in Neo4j.
    """

    description: str = Field(
        ...,
        min_length=10,
        description="Composite technical requirement text — describes what the subsystem shall do.",
    )
    rationale: str = Field(
        default="",
        description="Why these HLRs were grouped under this composite requirement.",
    )
    child_hlr_names: list[str] = Field(
        default_factory=list,
        description="HLR name strings that this composite HLR composes.",
    )


class MinedComponent(BaseModel):
    """A single mined Component with its functional requirement and HLR assignments.

    Produced by :class:`ComponentMiner` when clustering all project HLRs
    into the minimal set of functional Components.  Each Component
    represents a business-level or functional requirement that the
    assigned HLRs technically implement.

    Attributes:
        name: Short name for the Component (e.g. "Data Model",
            "Graph Infrastructure").
        description: The functional/business-level requirement text —
            describes what the component shall do at a functional level,
            abstracting the technical HLRs.
        namespace: The primary code-level namespace this Component maps
            to (e.g. "codegraph.models").
        hlr_names: List of HLR ``name`` strings assigned to this
            Component.  Every HLR in the project must appear in exactly
            one Component's ``hlr_names``.
    """

    name: str = Field(
        ...,
        min_length=2,
        description="Short name for the Component.",
    )
    description: str = Field(
        ...,
        min_length=10,
        description="Functional/business-level requirement text for the Component.",
    )
    namespace: str = Field(
        default="",
        description="Primary code-level namespace this Component maps to.",
    )
    hlr_names: list[str] = Field(
        default_factory=list,
        description="HLR name strings assigned to this Component.",
    )


class MinedComponents(BaseModel):
    """Complete set of mined Components for the entire project.

    Produced by :class:`ComponentMiner` from a single global LLM call
    that sees all project HLRs and clusters them into the minimal set
    of functional Components.

    Attributes:
        components: List of :class:`MinedComponent` instances.  Every
            HLR in the project must appear in exactly one Component's
            ``hlr_names``.
    """

    components: list[MinedComponent] = Field(
        default_factory=list,
        description="Mined Components for the project.",
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
