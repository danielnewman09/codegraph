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
from codegraph.backends import get_backend

log = logging.getLogger("codegraph_agents.context.builtins")


class _LazyGraphRepo:
    """Deferred access to ``get_backend().graph``.

    Resolves the backend on first attribute access rather than at
    import time, so importing this module never touches the database
    (no stray backend files / connections) and works regardless of how
    the backend is configured afterwards.
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(get_backend().graph, name)


repo = _LazyGraphRepo()

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
    from codegraph_requirements.models import HLR, LLR
    from codegraph.models.test import TestNode, TestStepNode, AssertionNode
    from codegraph.models.compound import CompoundNode

    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        raise ValueError(
            f"HLR with uid={config.hlr_uid} not found in Neo4j"
        )

    llrs = repo.composed_children(hlr, LLR)

    notional = []
    for llr in llrs:
        tests = repo.composed_children(llr, TestNode)
        for test in tests:
            steps = repo.composed_children(test, TestStepNode)
            assertions = repo.composed_children(test, AssertionNode)
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

    design_compounds = [
        {
            "qualified_name": (
                getattr(node, "qualified_name", "") or ""
            ),
            "name": getattr(node, "name", "") or "",
            "kind": getattr(node, "kind", "class"),
        }
        for node in repo.composed_children(hlr, CompoundNode)
    ]

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
        from codegraph_project.models.component import Component
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no component namespace"
        )
        return ""

    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        return ""
    comps = repo.incoming_composers(hlr, Component)
    return getattr(comps[0], "namespace", "") if comps else ""


def _resolve_prior_design_compounds(
    config: AgentConfig,
) -> list[dict[str, str]]:
    """Return design compounds from *other* HLRs for cross-HLR awareness."""
    try:
        from codegraph_requirements.models import HLR
        from codegraph.models.compound import CompoundNode
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no prior design compounds"
        )
        return []

    results: list[dict[str, str]] = []
    for other_hlr in repo.find_all_by_kind("hlr"):
        if other_hlr.uid == config.hlr_uid:
            continue
        for target in repo.composed_children(other_hlr, CompoundNode):
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
        from codegraph_project.models.component import Component
    except ImportError:
        log.debug(
            "codegraph_requirements not available — "
            "no sibling namespaces"
        )
        return []

    namespaces: list[str] = []
    seen: set[str] = set()
    for other_hlr in repo.find_all_by_kind("hlr"):
        if other_hlr.uid == config.hlr_uid:
            continue
        for comp in repo.incoming_composers(other_hlr, Component):
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
