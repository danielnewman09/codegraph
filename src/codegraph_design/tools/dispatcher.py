"""Design dispatchers — extend CodeGraphDispatcher with requirements-level
discovery tools AND design-agent tools (validate_design, produce_oo_design,
import_compound, check_class_name) plus verification-resolution tools.

Three dispatcher classes:

- :class:`DesignDiscoveryDispatcher` — extends CodeGraphDispatcher with
  requirements discovery tools (search_requirements, get_hlr_dependencies,
  list_requirements, get_requirement_traces, build_design_context) plus
  workflow tools (ingest_design, generate_hlr_docs, etc.).
- :class:`DesignToolDispatcher` — extends CodeGraphDispatcher with design
  tools (validate_design, import_compound, check_class_name,
  produce_oo_design).  Uses two mutable :class:`LayerGraph` instances:
  ``context_graph`` (discovered as-built / intercomponent / prior-design
  nodes) and ``design_draft_graph`` (the current design under construction).
- :class:`VerificationDispatcher` — extends ToolDispatcher with
  verification-resolution tools (draft_verifications,
  commit_design_and_verifications). Holds a reference to a
  :class:`DesignToolDispatcher` for access to the design draft and
  context graph.

Usage (design agent tool loop)::

    from codegraph_design.tools.dispatcher import (
        DesignToolDispatcher, VerificationDispatcher,
    )

    design_disp = DesignToolDispatcher(
        context_classes=[{"qualified_name": "climate::Thermostat", ...}],
        component_namespace="climate",
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    def dispatch(name, inp):
        if name in verif_disp._handlers:
            return verif_disp.dispatch(name, inp)
        return design_disp.dispatch(name, inp)

    tools = design_disp.all_tool_schemas + verif_disp.all_tool_schemas
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from codegraph.tools.dispatcher import CodeGraphDispatcher, ToolDispatcher
from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.connection import get_session
from codegraph.graph import LayerGraph, CompositeEntry

log = logging.getLogger(__name__)


class DesignDiscoveryDispatcher(CodeGraphDispatcher):
    """Dispatcher for design discovery tools.

    Inherits all codegraph tools from :class:`CodeGraphDispatcher` and
    adds requirements-level discovery tools on top.

    Holds mutable context dictionaries for prior designs, dependency
    APIs, and inter-component boundaries — similar to the ticketing-
    system's ``DesignToolDispatcher``.

    Usage::

        d = DesignDiscoveryDispatcher(
            prior_designs={"Thermostat": "climate::Thermostat"},
            dependency_apis={"std::vector": "std::vector"},
            intercomponent_classes=[
                {"qualified_name": "ui::Widget", "kind": "class", "name": "Widget"},
            ],
            component_namespace="climate",
        )
        schemas = d.all_tool_schemas
        result = d.dispatch("search_requirements", {"query": "temperature"})
    """

    def __init__(
        self,
        repo=None,
        *,
        prior_designs: dict[str, str] | None = None,
        dependency_apis: dict[str, str] | None = None,
        intercomponent_classes: list[dict] | None = None,
        component_namespace: str = "",
    ):
        super().__init__(repo=repo)

        # ── Mutable context dictionaries ──
        self.prior_designs: dict[str, str] = dict(prior_designs or {})
        self.dependency_apis: dict[str, str] = dict(dependency_apis or {})
        self.intercomponent_classes: list[dict] = list(intercomponent_classes or [])
        self.component_namespace: str = component_namespace

        # Register discovery tools on top of codegraph tools
        from codegraph_design.tools.discovery_tools import register_all as _reg
        _reg(self)

        # Register workflow tools (ported from scripts/)
        from codegraph_design.tools.workflow_tools import register_all as _reg_wf
        _reg_wf(self)

    # ── Convenience setters ──

    def add_prior_design(self, name: str, qualified_name: str) -> None:
        """Register a bare-name → qualified-name mapping for a newly
        designed class so that future lookups can resolve it."""
        self.prior_designs[name] = qualified_name

    def set_dependency_apis(self, lookup: dict[str, str]) -> None:
        """Replace the dependency API lookup (name → qualified_name)."""
        self.dependency_apis = dict(lookup)

    def set_intercomponent_classes(self, classes: list[dict]) -> None:
        """Replace the inter-component boundary class list."""
        self.intercomponent_classes = list(classes)


# ══════════════════════════════════════════════════════════════════════════
# DesignToolDispatcher — design-agent dispatcher with LayerGraph context
# ══════════════════════════════════════════════════════════════════════════


class DesignToolDispatcher(CodeGraphDispatcher):
    """Design-agent dispatcher — inherits all codegraph tools + adds
    design validation, compound import, name checking, and design
    storage.

    Holds two mutable :class:`LayerGraph` instances:

    - ``context_graph``: everything the agent has discovered — as-built
      imports, intercomponent classes, prior designs.  Read-only
      reference context.  Never persisted by the design pipeline.
    - ``design_draft_graph``: only what the agent is designing now.
      Set via ``produce_oo_design``; persisted to Neo4j and linked to
      the HLR.

    Resolution via ``has_qname()`` checks both graphs, then falls back
    to a full-codegraph query for undiscovered names.

    Usage::

        d = DesignToolDispatcher(
            context_classes=[
                {"qualified_name": "ui::Widget", "kind": "class", "name": "Widget"},
            ],
            component_namespace="climate",
        )
        schemas = d.all_tool_schemas
        result = d.dispatch("import_compound", {"qname": "std::vector"})
    """

    def __init__(
        self,
        repo: GraphRepository | None = None,
        *,
        context_classes: list[dict] | None = None,
        component_namespace: str = "",
        sibling_namespaces: list[str] | None = None,
    ):
        super().__init__(repo=repo)

        # ── Mutable LayerGraph context ──
        self.context_graph: LayerGraph = LayerGraph(tags=frozenset())
        self.design_draft_graph: LayerGraph = LayerGraph(
            tags=frozenset({"design"})
        )
        self.component_namespace: str = component_namespace
        self.sibling_namespaces: list[str] = list(sibling_namespaces or [])

        # Seed context_graph from context_classes
        all_context = list(context_classes or [])

        for cls_dict in all_context:
            self._add_to_context(cls_dict)

        seeded = sum(1 for _ in self.context_graph._all_entries())
        if seeded:
            log.info(
                "DesignToolDispatcher: seeded context_graph with %d entries",
                seeded,
            )

        # Register design-specific tools on top of codegraph tools
        from codegraph_design.tools.design_tools import register_all as _reg_design
        _reg_design(self)

        # Register design-smell detection tools
        from codegraph_design.tools.design_smells import register_all as _reg_smells
        _reg_smells(self)

    # ── Tool registration (overrides wide-open base) ────────────────────

    def _register_all(self) -> None:
        """Register only the subset of codegraph tools the design agent needs.

        The base :class:`~codegraph.tools.dispatcher.CodeGraphDispatcher`
        registers 23 low-level graph/info/format/query tools.  The design
        agent only needs discovery + lookup.
        """
        from codegraph.tools.discovery import register_all as _reg_discovery
        from codegraph.tools.lookup import register_all as _reg_lookup

        _reg_discovery(self)
        _reg_lookup(self)

        # Drop administrative / raw-graph tools that bloat the surface.
        _drop = self._handlers.pop
        for name in (
            "browse_namespace", "list_sources", "list_namespaces",
            "alias_lookup", "get_container_info", "dependency_list",
        ):
            _drop(name, None)
            self._schemas.pop(name, None)

    # ── Internal helpers ────────────────────────────────────────────────

    def _remove_tool(self, name: str) -> None:
        """Remove a registered tool by name (no-op if absent)."""
        self._handlers.pop(name, None)
        self._schemas.pop(name, None)

    def _add_to_context(self, cls_dict: dict) -> None:
        """Add a class dict to context_graph as a CompositeEntry."""
        qn = cls_dict.get("qualified_name", "")
        if not qn:
            return
        from codegraph_design.agents.design_oo_prompt import (
            _deserialize_class_dict,
        )
        try:
            node = _deserialize_class_dict(cls_dict)
            entry = CompositeEntry(node=node)
            self.context_graph.entries[
                LayerGraph._node_key(node)
            ] = entry
            log.debug("_add_to_context: seeded '%s' into context_graph", qn)
        except Exception as exc:
            log.warning("_add_to_context: failed to seed '%s': %s", qn, exc)

    # ── Resolution ──────────────────────────────────────────────────────

    def has_qname(self, qname: str) -> bool:
        """Check if a qualified name exists in the context graph, design
        draft graph, or the full codegraph (as a fallback)."""
        if not qname:
            log.debug("has_qname: empty qname — returning False")
            return False
        if self.design_draft_graph.has_qname(qname):
            log.debug("has_qname(%s): resolved in design_draft_graph", qname)
            return True
        if self.context_graph.has_qname(qname):
            log.debug("has_qname(%s): resolved in context_graph", qname)
            return True
        from codegraph_design.tools.design_tools import _qname_in_codegraph
        result = _qname_in_codegraph(qname)
        if result:
            log.debug("has_qname(%s): resolved via codegraph fallback", qname)
        return result

    @property
    def design_draft(self) -> list[dict] | None:
        """Serialize design_draft_graph entries for verification tools."""
        entries = self.design_draft_graph.entries
        if not entries:
            return None
        return [e.serialize() for e in entries.values()]

    @design_draft.setter
    def design_draft(self, value: list[dict] | None) -> None:
        if value:
            self.design_draft_graph = LayerGraph.deserialize(value)
        else:
            self.design_draft_graph = LayerGraph(tags=frozenset({"design"}))


# ══════════════════════════════════════════════════════════════════════════
# VerificationDispatcher — resolve notional stubs to qualified design names
# ══════════════════════════════════════════════════════════════════════════


class VerificationDispatcher(ToolDispatcher):
    """Verification-resolution dispatcher — resolve notional verification
    stubs to qualified design names.

    Extends the base :class:`ToolDispatcher` with just two tools:

    - ``draft_verifications`` — submit resolved verification procedures,
      validate qname references against the design draft + context, and
      return unresolved references with suggestions.
    - ``commit_design_and_verifications`` — terminal tool that validates
      everything and returns the final design + verifications.

    Holds a reference to the :class:`DesignToolDispatcher` for access
    to ``design_draft``, ``context_graph``, and ``has_qname()``.

    Usage::

        design_disp = DesignToolDispatcher(context_classes=[...])
        verif_disp = VerificationDispatcher(design_dispatcher=design_disp)
    """

    def __init__(self, design_dispatcher: DesignToolDispatcher):
        super().__init__()
        self._design_dispatcher = design_dispatcher

        # Register verification tools
        from codegraph_design.tools.verification_tools import (
            register_all as _reg_verif,
        )
        _reg_verif(self)

    # ── Delegate access to the design dispatcher's context ────────────────

    @property
    def design_draft(self) -> list[dict] | None:
        return self._design_dispatcher.design_draft

    @property
    def has_qname(self):
        """Delegate to the design dispatcher's unified resolution."""
        return self._design_dispatcher.has_qname

    @property
    def draft_verifications(self) -> dict[str, list[dict]] | None:
        return getattr(self, "_draft_verifications", None)

    @draft_verifications.setter
    def draft_verifications(self, value: dict[str, list[dict]] | None) -> None:
        self._draft_verifications = value
