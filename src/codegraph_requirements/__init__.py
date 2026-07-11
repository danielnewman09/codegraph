"""Requirements subpackage — HLR/LLR models, schemas, persistence, and formatting.

Migrated from the ticketing system's ``backend_migrated`` package into
codegraph as a first-class citizen.  Provides:

- **Models**: :class:`HLR` and :class:`LLR` neomodel nodes that extend
  ``CodeGraphNode`` and participate in the ``LayerGraph`` composition
  hierarchy via ``COMPOSES`` edges.
- **Schemas**: :class:`DecomposedRequirementSchema` — Pydantic model for
  the LLM decomposition output.
- **Persistence**: :func:`persist_decomposition` — persists LLM output
  into Neo4j via ``LayerGraph.deserialize(create_missing=True)``, with
  scaffold node auto-creation, orphan cleanup, and upsert semantics.
- **Formatting**: :func:`format_hlrs_for_prompt` and
  :func:`format_llrs_with_verifications_for_prompt` for building agent
  prompt blocks from requirement dicts.

Usage::

    from codegraph.persistence.connection import init_neo4j
    from codegraph_requirements import HLR, LLR
    from codegraph_requirements import persist_decomposition
    from codegraph_requirements import DecomposedRequirementSchema

    init_neo4j()

    # Create an HLR
    hlr = HLR.save_new(name="Error handling", description="The system shall...")
    # ... after decomposition:
    result = persist_decomposition(hlr_uid=hlr.uid, decomposition=schema_output)
    print(f"Created {result.llrs_created} LLRs, {result.tests_created} tests")

Graph structure::

    Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
                                       LLR -[:COMPOSES]-> CompoundNode (design)
                                       TestNode -[:COMPOSES]-> AssertionNode
                                       TestNode -[:COMPOSES]-> TestStepNode
                                       TestNode -[:COMPOSES]-> TestFixtureNode
                                       TestNode -[:VERIFIES]-> MethodNode | ...
"""

from codegraph_requirements.models.requirement import HLR, LLR
from codegraph_requirements.schemas import (
    DecomposedRequirementSchema,
    VERIFICATION_METHODS,
    VerificationMethodType,
)
from codegraph_requirements.persistence import (
    DecompositionResult,
    persist_decomposition,
)
from codegraph_requirements.formatting import (
    format_hlr_dict,
    format_llr_dict,
    format_hlrs_for_prompt,
    format_llrs_with_verifications_for_prompt,
)

__all__ = [
    # Models
    "HLR",
    "LLR",
    # Schemas
    "DecomposedRequirementSchema",
    "VERIFICATION_METHODS",
    "VerificationMethodType",
    # Persistence
    "DecompositionResult",
    "persist_decomposition",
    # Formatting
    "format_hlr_dict",
    "format_llr_dict",
    "format_hlrs_for_prompt",
    "format_llrs_with_verifications_for_prompt",
]
