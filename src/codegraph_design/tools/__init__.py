"""Tools package for codegraph_design.

Dispatchers:
- :class:`DesignDiscoveryDispatcher` — codegraph tools + requirements discovery
  + workflow tools.
- :class:`DesignToolDispatcher` — codegraph tools + design validation tools
  (validate_design, check_class_name, produce_oo_design).
- :class:`VerificationDispatcher` — verification-resolution tools
  (draft_verifications, commit_design_and_verifications).

Tool modules:
- :mod:`codegraph_design.tools.discovery_tools` — search_requirements,
  get_hlr_dependencies, list_requirements, get_requirement_traces,
  build_design_context.
- :mod:`codegraph_design.tools.workflow_tools` — ingest_design,
  generate_hlr_docs, generate_feedback_docs, evaluate_coverage,
  verify_callee_granularity.
- :mod:`codegraph_design.tools.design_tools` — validate_design,
  check_class_name, produce_oo_design.
- :mod:`codegraph_design.tools.verification_tools` — draft_verifications,
  commit_design_and_verifications.
- :mod:`codegraph_design.tools.design_smells` — check_design_smells
  (structural design-smell detection with severity levels).
"""

from codegraph_design.tools.dispatcher import (
    DesignDiscoveryDispatcher,
    DesignToolDispatcher,
    VerificationDispatcher,
)

__all__ = [
    "DesignDiscoveryDispatcher",
    "DesignToolDispatcher",
    "VerificationDispatcher",
]
