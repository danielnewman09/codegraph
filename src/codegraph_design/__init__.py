"""Codegraph design package — agents, tools, and prompts for HLR decomposition
and object-oriented design.

Provides:

* :mod:`codegraph_design.agents.decompose_hlr` — decompose HLRs into LLRs
  with verification stubs.
* :mod:`codegraph_design.agents.design_oo` — produce OO class designs and
  resolve notional verification stubs to qualified design names.
* :mod:`codegraph_design.agents.design_oo_prompt` — prompt-section builders
  for the design agent (as-built, namespace, intercomponent, existing).
* :mod:`codegraph_design.tools.dispatcher` — dispatchers that combine
  codegraph query tools with design-validation and verification-resolution
  tools.
* :mod:`codegraph_design.tools.design_tools` — validate_design,
  check_class_name, produce_oo_design.
* :mod:`codegraph_design.tools.verification_tools` — draft_verifications,
  commit_design_and_verifications.
"""
