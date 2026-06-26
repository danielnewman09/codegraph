"""Pydantic schemas for requirements models.

The decompose agent produces a flat list of codegraph node dicts —
the same format that ``LayerGraph.deserialize()`` consumes.  No
intermediate nested transformation is needed; the LLM output goes
directly to ``LayerGraph.deserialize()`` with only scaffold node
materialization as a post-step.

Schema structure::

    DecomposedRequirementSchema
      ├─ description: str   (HLR description, for context)
      └─ nodes: list[dict]   (flat list of codegraph node dicts)

Each node dict has ``type``, node-specific properties, and an
``edges`` array with standard codegraph edge refs::

    {"relation_type": "LEFT_OPERAND", "target_uid": "Engine.result",
     "target_type": "AttributeNode"}

The LLM generates ``qualified_name`` for test nodes (TestNode,
AssertionNode, TestStepNode) and uses them as ``target_uid``
in COMPOSES edges.  Typed edges (LEFT_OPERAND, RIGHT_OPERAND,
CALLEE, CALLER) use notional references (e.g. ``"Engine.result"``,
``"30"``) as ``target_uid`` — scaffold nodes for these targets
are materialized during persistence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

VERIFICATION_METHODS = ["automated", "review", "inspection"]

VerificationMethodType = Literal["automated", "review", "inspection"]

# Runtime check
_literal_methods = set(VerificationMethodType.__args__)
_model_methods = set(VERIFICATION_METHODS)
if _literal_methods != _model_methods:
    raise RuntimeError(
        f"VerificationMethodType Literal {_literal_methods} is out of sync "
        f"with VERIFICATION_METHODS {_model_methods}. Update schemas.py."
    )


class DecomposedRequirementSchema(BaseModel):
    """Structured output of the HLR decomposition agent.

    A flat list of codegraph node dicts (``nodes``) that can be passed
    directly to ``LayerGraph.deserialize()`` after scaffold
    materialization.  Each node dict has ``type``, properties, and
    an ``edges`` array in the standard codegraph format.

    The ``description`` field echoes the HLR description for context
    and is not persisted as a node.
    """
    description: str
    nodes: list[dict] = []
