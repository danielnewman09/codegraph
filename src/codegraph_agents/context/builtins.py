"""Built-in context resolvers for codegraph agents.

Each resolver is a module-level function that takes an
:class:`~codegraph_agents.config.AgentConfig` and returns a
context value.  They self-register with
:class:`~codegraph_agents.context.ContextProvider` at import time.
"""

from __future__ import annotations

import logging
from typing import Any

from codegraph_agents.config import AgentConfig
from codegraph_agents.context import ContextProvider

log = logging.getLogger("codegraph_agents.context.builtins")


# ── Mandatory resolvers ────────────────────────────────────────


def _resolve_hlr_subtree(config: AgentConfig) -> dict[str, Any]:
    """Load the full HLR subtree from Neo4j.

    Returns a dict with keys:

    * ``hlr`` — the HLR neomodel node
    * ``llrs`` — list of LLR neomodel nodes
    * ``notional_verifications`` — list of dicts with test steps
      and assertions extracted from LLRs
    * ``design_compounds`` — existing design nodes already linked
      to this HLR
    """
    from codegraph_requirements.models import HLR

    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        raise ValueError(
            f"HLR with uid={config.hlr_uid} not found in Neo4j"
        )

    llrs = list(hlr.llrs.all()) if hasattr(hlr, "llrs") else []

    notional = []
    for llr in llrs:
        tests = (
            list(llr.verification_methods.all())
            if hasattr(llr, "verification_methods")
            else []
        )
        for test in tests:
            steps = (
                list(test.steps.all())
                if hasattr(test, "steps")
                else []
            )
            assertions = (
                list(test.assertions.all())
                if hasattr(test, "assertions")
                else []
            )
            notional.append({
                "test_uid": test.uid,
                "test_name": test.name or "",
                "description": test.description or "",
                "steps": [
                    {
                        "description": (
                            getattr(s, "description", "") or ""
                        ),
                        "callee_qualified_name": (
                            getattr(
                                s, "callee_qualified_name", ""
                            )
                            or ""
                        ),
                    }
                    for s in steps
                ],
                "assertions": [
                    {
                        "subject_qualified_name": (
                            getattr(
                                a, "subject_qualified_name", ""
                            )
                            or ""
                        ),
                        "operator": (
                            getattr(a, "operator", "") or ""
                        ),
                        "expected_value": (
                            getattr(a, "expected_value", "") or ""
                        ),
                    }
                    for a in assertions
                ],
            })

    design_compounds = []
    if hasattr(hlr, "design_compounds"):
        for node in hlr.design_compounds.all():
            design_compounds.append({
                "qualified_name": (
                    getattr(node, "qualified_name", "") or ""
                ),
                "name": getattr(node, "name", "") or "",
                "kind": getattr(node, "kind", "class"),
            })

    return {
        "hlr": hlr,
        "llrs": llrs,
        "notional_verifications": notional,
        "design_compounds": design_compounds,
    }


# ── Optional enrichment resolvers ──────────────────────────────


def _resolve_component_namespace(config: AgentConfig) -> str:
    """Return the namespace of the component this HLR belongs to."""
    if config.component_namespace:
        return config.component_namespace

    try:
        from codegraph_requirements.models import HLR
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no component namespace"
        )
        return ""

    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        return ""
    comps = (
        hlr.component.all()
        if hasattr(hlr, "component")
        else []
    )
    return getattr(comps[0], "namespace", "") if comps else ""


def _resolve_prior_design_compounds(
    config: AgentConfig,
) -> list[dict[str, str]]:
    """Return design compounds from *other* HLRs for cross-HLR awareness."""
    try:
        from codegraph_requirements.models import HLR
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no prior design compounds"
        )
        return []

    results: list[dict[str, str]] = []
    for other_hlr in HLR.nodes.all():
        if other_hlr.uid == config.hlr_uid:
            continue
        if not hasattr(other_hlr, "design_compounds"):
            continue
        for target in other_hlr.design_compounds.all():
            results.append({
                "qualified_name": (
                    getattr(target, "qualified_name", "") or ""
                ),
                "name": getattr(target, "name", "") or "",
                "kind": getattr(target, "kind", "class"),
            })
    return results


def _resolve_sibling_namespaces(
    config: AgentConfig,
) -> list[str]:
    """Return namespaces of sibling components for disambiguation."""
    try:
        from codegraph_requirements.models import HLR
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no sibling namespaces"
        )
        return []

    namespaces: list[str] = []
    seen: set[str] = set()
    for other_hlr in HLR.nodes.all():
        if other_hlr.uid == config.hlr_uid:
            continue
        if not hasattr(other_hlr, "component"):
            continue
        for comp in other_hlr.component.all():
            ns = getattr(comp, "namespace", "")
            if ns and ns not in seen:
                seen.add(ns)
                namespaces.append(ns)
    return namespaces


# ── Self-register at import time ───────────────────────────────

ContextProvider.register("hlr_subtree", _resolve_hlr_subtree)
ContextProvider.register(
    "component_namespace", _resolve_component_namespace
)
ContextProvider.register(
    "prior_design_compounds", _resolve_prior_design_compounds
)
ContextProvider.register(
    "sibling_namespaces", _resolve_sibling_namespaces
)
