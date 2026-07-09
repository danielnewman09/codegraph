"""Design agents — HLR decomposition and object-oriented design.

Provides:

* :func:`decompose` — decompose a high-level requirement into LLRs with
  verification stubs.
* :func:`decompose_and_persist_hlr` — full end-to-end: load HLR from Neo4j →
  decompose → persist.
* :func:`validate_decomposition` — structural validation of decomposition
  output (8 hard rules).
* :class:`DecompositionViolation` / :class:`DecompositionValidationError` —
  validation result types.
* :func:`design_hlr` — design OO class structure and resolve notional
  verification stubs to qualified design names.
* :func:`design_and_persist_hlr` — full end-to-end: load HLR + LLRs from
  Neo4j → design + verify → persist.
* :class:`DesignHLRResult` — result of the design_hlr pipeline.

For programmatic use, call the agents directly::

    from codegraph_design.agents.decompose_hlr import decompose
    from codegraph_design.agents.design_oo import design_hlr

For use as Pi subagents, the system prompts, tool schemas, and dispatch
logic are exposed via the codegraph-mcp bridge (``codegraph_bridge.py``).
"""

from codegraph_design.agents.decompose_hlr import (
    decompose,
    decompose_and_persist_hlr,
    validate_decomposition,
    DecompositionViolation,
    DecompositionValidationError,
)
from codegraph_design.agents.design_oo import (
    design_hlr,
    design_and_persist_hlr,
    DesignHLRResult,
)

__all__ = [
    "decompose",
    "decompose_and_persist_hlr",
    "validate_decomposition",
    "DecompositionViolation",
    "DecompositionValidationError",
    "design_hlr",
    "design_and_persist_hlr",
    "DesignHLRResult",
]
