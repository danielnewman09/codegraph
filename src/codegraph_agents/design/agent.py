"""DesignAgent — canonical OO design pipeline for codegraph.

Ports the design_oo agent from ``codegraph_design.agents.design_oo`` to the
new ``BaseAgent`` + LangGraph checkpointing architecture.

Usage::

    from codegraph_agents.design import DesignAgent
    from codegraph_agents.config import AgentConfig

    agent = DesignAgent(AgentConfig(
        hlr_uid="abc123def456",
        component_namespace="climate",
        log_dir="/path/to/logs",
    ))
    result = agent.run()  # → DesignResult(design=[...], verifications={...})
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from codegraph_agents.base import BaseAgent
from codegraph_agents.config import AgentConfig
from codegraph_agents.state import AgentState

log = logging.getLogger("codegraph_agents.design")


# ── Result dataclass ─────────────────────────────────────────────


@dataclass
class DesignResult:
    """Output of :meth:`DesignAgent.run`."""

    design: list[dict] = field(default_factory=list)
    """LayerGraph-format design nodes from produce_oo_design."""

    verifications: dict[str, list[dict]] = field(default_factory=dict)
    """LLR uid → verification method lists from commit_design_and_verifications."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal warnings or errors encountered during extraction."""


# ── Composite dispatcher — routes between design + verification ──


class _CompositeDispatcher:
    """Thin wrapper that routes between ``DesignToolDispatcher`` and
    ``VerificationDispatcher``.

    BaseAgent's ``_tools_node`` calls ``dispatch(tool_name, tool_input)``
    and reads ``all_tool_schemas``.  This composite hides the two-dispatcher
    split behind a single interface.
    """

    def __init__(self, design_disp, verif_disp):
        self._design = design_disp
        self._verif = verif_disp

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        if tool_name in self._verif._handlers:
            return self._verif.dispatch(tool_name, tool_input)
        return self._design.dispatch(tool_name, tool_input)

    @property
    def all_tool_schemas(self) -> list[dict]:
        return (
            self._design.all_tool_schemas
            + self._verif.all_tool_schemas
        )


# ── DesignAgent ──────────────────────────────────────────────────


def _import_system_prompt():
    """Import the canonical system prompt template.

    Lazy function to avoid circular imports at module load time.
    """
    from codegraph_agents.design.prompts import SYSTEM_PROMPT_TEMPLATE

    return SYSTEM_PROMPT_TEMPLATE


class DesignAgent(BaseAgent):
    """OO design agent with LangGraph checkpointing.

    Lifecycle::

        agent = DesignAgent(AgentConfig(hlr_uid="abc123"))
        result = agent.run()
        # → DesignResult(design=[...], verifications={...})

    If the HLR has existing scaffold nodes, call
    :meth:`run_with_reconciliation` to reconcile the design with
    scaffold after the agent loop.
    """

    name: ClassVar[str] = "design_oo"

    system_prompt = _import_system_prompt()

    context_needs: ClassVar[set[str]] = {
        "hlr_subtree",
        "component_namespace",
        "prior_design_compounds",
        "sibling_namespaces",
    }

    final_tool_name: ClassVar[str] = "finalize"

    # ── Dispatch construction ────────────────────────────────────

    def _create_dispatcher(self) -> _CompositeDispatcher:
        """Create the composite design + verification dispatcher."""
        from codegraph_design.tools.dispatcher import (
            DesignToolDispatcher,
            VerificationDispatcher,
        )

        self._design_disp = DesignToolDispatcher(
            context_classes=None,
            component_namespace="",
            sibling_namespaces=[],
        )
        self._verif_disp = VerificationDispatcher(
            design_dispatcher=self._design_disp,
        )
        return _CompositeDispatcher(
            self._design_disp, self._verif_disp,
        )

    # ── Context loading (seeds dispatcher) ───────────────────────

    def load_context(self) -> dict[str, Any]:
        """Load required context AND seed the design dispatcher.

        The ``DesignToolDispatcher`` needs ``context_classes``
        (prior-design compounds) and namespace info before the
        agent starts.  We resolve those from the context provider
        and set them on the dispatcher.  Also builds prompt section
        strings so ``system_prompt.format()`` has them ready.
        """
        ctx = super().load_context()

        # ── Seed dispatcher with context ──
        hlr_tree = ctx.get("hlr_subtree", {})
        prior_compounds: list[dict] = hlr_tree.get(
            "design_compounds", []
        )
        namespace: str = ctx.get("component_namespace", "")
        siblings: list[str] = ctx.get("sibling_namespaces", [])

        self._design_disp.component_namespace = namespace
        self._design_disp.sibling_namespaces = list(siblings)

        for cls_dict in prior_compounds:
            self._design_disp._add_to_context(cls_dict)

        seeded = sum(
            1 for _ in self._design_disp.context_graph._all_entries()
        )
        if seeded:
            log.info(
                "DesignAgent: seeded %d prior-design compounds "
                "into context_graph", seeded,
            )
        if namespace:
            log.info(
                "DesignAgent: namespace=%s, siblings=%s",
                namespace, siblings,
            )

        # ── Build prompt section variables ──
        from codegraph_design.agents.design_oo_prompt import (
            build_namespace_section,
            build_existing_classes_section,
            build_intercomponent_section,
        )

        ctx["specializations_section"] = ""
        ctx["as_built_section"] = ""
        ctx["namespace_section"] = (
            build_namespace_section(namespace, siblings)
            if namespace
            else ""
        )
        ctx["existing_classes_section"] = (
            build_existing_classes_section(prior_compounds)
            if prior_compounds
            else ""
        )
        ctx["intercomponent_section"] = (
            build_intercomponent_section(prior_compounds)
            if prior_compounds
            else ""
        )

        return ctx

    # ── Initial messages ─────────────────────────────────────────

    def build_initial_messages(
        self, context: dict[str, Any]
    ) -> list[BaseMessage]:
        """Build the initial HumanMessage from loaded HLR + LLR context.

        Formats notional verification stubs for each LLR so the
        LLM knows which references to resolve.
        """
        hlr_tree = context.get("hlr_subtree", {})
        hlr = hlr_tree.get("hlr")
        notional = hlr_tree.get("notional_verifications", [])

        # HLR description
        hlr_desc = ""
        hlr_uid_str = ""
        if hlr is not None:
            hlr_desc = (
                getattr(hlr, "description", "")
                or getattr(hlr, "name", "")
                or ""
            )
            hlr_uid_str = getattr(hlr, "uid", "") or ""

        # Format notional verifications
        verif_lines: list[str] = []
        for nv in notional:
            test_name = nv.get("test_name", "")
            test_desc = nv.get("description", "")
            verif_lines.append(
                f"  [{nv.get('test_uid', '')[:8]}] "
                f"{test_name}: {test_desc}"
            )
            steps = nv.get("steps", [])
            if steps:
                verif_lines.append("    Steps:")
                for s in steps:
                    callee = s.get("callee_qualified_name", "")
                    line = f"      {s.get('description', '')}"
                    if callee:
                        line += f" → {callee}"
                    verif_lines.append(line)
            assertions = nv.get("assertions", [])
            if assertions:
                verif_lines.append("    Assertions:")
                for a in assertions:
                    verif_lines.append(
                        f"      {a.get('subject_qualified_name', '')} "
                        f"{a.get('operator', '==')} "
                        f"{a.get('expected_value', '')}"
                    )

        content_parts = [
            "Design the object-oriented class structure and resolve "
            "verification stubs for the following requirements:\n",
        ]
        if hlr_uid_str:
            content_parts.append(
                f"HLR {hlr_uid_str[:8]}: {hlr_desc}\n"
            )
        else:
            content_parts.append(f"HLR: {hlr_desc}\n")

        if verif_lines:
            content_parts.append(
                "\nNotional verification stubs:\n"
                + "\n".join(verif_lines)
            )

        # Component hint
        namespace = context.get("component_namespace", "")
        if namespace:
            content_parts.append(
                f"\n\nThis requirement belongs to the architectural "
                f"component namespace: `{namespace}`.  Your class "
                f"design should be scoped to this namespace."
            )

        return [
            HumanMessage(content="".join(content_parts))
        ]

    # ── Result extraction ────────────────────────────────────────

    def build_result(self, state: AgentState) -> DesignResult:
        """Extract design + verifications from the commit tool output.

        Searches the message history for the ToolMessage from
        ``commit_design_and_verifications`` (a normal tool that
        executes in the tools node, not the termination signal).
        """
        result_data = self._extract_final_tool_output(
            state, "commit_design_and_verifications"
        )
        errors: list[str] = []

        if result_data is None:
            errors.append(
                "No commit_design_and_verifications output found "
                "in message history"
            )
            return DesignResult(errors=errors)

        design = result_data.get("design", [])
        verifications = result_data.get("verifications", {})

        if not design:
            errors.append("No design nodes in committed result")
        if not verifications:
            errors.append("No verifications in committed result")

        return DesignResult(
            design=design,
            verifications=verifications,
            errors=errors,
        )

    # ── Full pipeline with persistence ───────────────────────────

    def run_with_reconciliation(self) -> dict:
        """Run design agent + scaffold reconciliation + artifacts.

        This is the full ``design_and_persist_hlr`` equivalent
        ported to the new agent architecture.

        Returns:
            Dict with keys ``nodes_updated``, ``nodes_created``,
            ``edges_linked``, ``verifications_resolved``, etc.
            (same shape as the old ``design_and_persist_hlr``).
        """
        # ── Guard: HLR required for persistence ──
        if not self.config.hlr_uid:
            raise ValueError(
                "DesignAgent.run_with_reconciliation() requires "
                "hlr_uid in AgentConfig for persistence"
            )

        hlr_uid = self.config.hlr_uid

        # ── Run the agent loop ──
        design_result: DesignResult = self.run()

        if not design_result.design:
            log.warning(
                "DesignAgent: no design nodes produced for HLR %s "
                "— skipping reconciliation",
                hlr_uid[:8],
            )
            return {
                "status": "no_design",
                "nodes_updated": 0,
                "nodes_created": 0,
                "edges_linked": 0,
                "deps_edges": 0,
                "namespace_edges": 0,
                "namespaces_created": 0,
                "namespaces_reused": 0,
                "verifications_resolved": 0,
                "conditions_created": 0,
                "actions_created": 0,
                "links_applied": 0,
                "scaffold_retaged": 0,
                "scaffold_cleaned": 0,
                "errors": design_result.errors,
            }

        # ── Reconcile design with scaffold ──
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )

        recon: dict = {}
        try:
            recon = _reconcile_design_with_scaffold(
                hlr_uid, design_result.design,
            )
        except Exception as exc:
            log.warning(
                "Design reconciliation failed for HLR %s: %s",
                hlr_uid[:8], exc, exc_info=True,
            )

        # ── Count verifications ──
        verifications_resolved = len(design_result.verifications)
        conditions_created = 0
        actions_created = 0
        for verif_list in design_result.verifications.values():
            for v in verif_list:
                conditions_created += len(
                    v.get("preconditions", [])
                )
                conditions_created += len(
                    v.get("postconditions", [])
                )
                actions_created += len(
                    v.get("actions", [])
                )

        # ── Persist VERIFIES & update CALLEE edges ──
        from codegraph_design.agents.design_oo import _persist_verifications

        verifies_persisted = 0
        callees_updated = 0
        if design_result.verifications:
            try:
                verifies_persisted, callees_updated = _persist_verifications(
                    hlr_uid, design_result.verifications
                )
            except Exception as exc:
                log.warning(
                    "Verification persistence failed for HLR %s: %s",
                    hlr_uid[:8], exc, exc_info=True,
                )

        # ── Link HLR → top-level design compounds ──
        from codegraph_requirements.models import HLR
        from codegraph.models.compound import CompoundNode

        links_applied = 0
        hlr = HLR.nodes.get_or_none(uid=hlr_uid)
        if hlr:
            for node_dict in design_result.design:
                qn = node_dict.get("qualified_name", "")
                if not qn:
                    continue
                kind = node_dict.get("kind", "")
                if kind not in (
                    "class", "struct", "interface", "enum",
                ):
                    continue
                target_node = CompoundNode.nodes.get_or_none(
                    qualified_name=qn,
                )
                if not target_node:
                    continue
                try:
                    hlr.design_compounds.connect(target_node)
                    links_applied += 1
                except Exception as exc:
                    log.warning(
                        "Failed to COMPOSES link HLR %s -> %s: %s",
                        hlr_uid[:8], qn, exc,
                    )

        # ── Generate artifacts ──
        from codegraph_design.agents.design_oo import (
            _generate_design_artifacts,
            _generate_feedback_file,
        )

        artifacts = _generate_design_artifacts(
            hlr, design_result.design,
        )
        feedback_path = _generate_feedback_file(hlr)

        return {
            "nodes_updated": recon.get("nodes_updated", 0),
            "nodes_created": recon.get("nodes_created", 0),
            "edges_linked": recon.get("edges_linked", 0),
            "deps_edges": recon.get("deps_edges", 0),
            "namespace_edges": recon.get("namespace_edges", 0),
            "namespaces_created": recon.get("namespaces_created", 0),
            "namespaces_reused": recon.get("namespaces_reused", 0),
            "verifications_resolved": verifications_resolved,
            "verifies_persisted": verifies_persisted,
            "callees_updated": callees_updated,
            "conditions_created": conditions_created,
            "actions_created": actions_created,
            "links_applied": links_applied,
            "scaffold_retaged": recon.get("scaffold_retaged", 0),
            "scaffold_cleaned": recon.get("scaffold_cleaned", 0),
            "artifacts": artifacts,
            "feedback_file": str(feedback_path),
            "status": "designed",
            "errors": design_result.errors,
        }
