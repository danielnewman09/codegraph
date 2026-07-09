"""Design dispatchers — extend CodeGraphDispatcher with requirements-level
discovery tools AND design-agent tools (validate_design, produce_oo_design,
check_class_name) plus verification-resolution tools.

Three dispatcher classes:

- :class:`DesignDiscoveryDispatcher` — extends CodeGraphDispatcher with
  requirements discovery tools (search_requirements, get_hlr_dependencies,
  list_requirements, get_requirement_traces, build_design_context) plus
  workflow tools (ingest_design, generate_hlr_docs, etc.).
- :class:`DesignToolDispatcher` — extends CodeGraphDispatcher with design
  tools (validate_design, check_class_name, produce_oo_design) and mutable
  lookups for prior designs, dependency APIs, and intercomponent classes.
- :class:`VerificationDispatcher` — extends ToolDispatcher with
  verification-resolution tools (draft_verifications,
  commit_design_and_verifications). Holds a reference to a
  :class:`DesignToolDispatcher` for access to the design draft.

Usage (design agent tool loop)::

    from codegraph_design.tools.dispatcher import (
        DesignToolDispatcher, VerificationDispatcher,
    )

    design_disp = DesignToolDispatcher(
        prior_class_lookup={"Thermostat": "climate::Thermostat"},
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    def dispatch(name, inp):
        if name in verif_disp._handlers:
            return verif_disp.dispatch(name, inp)
        return design_disp.dispatch(name, inp)

    tools = design_disp.all_tool_schemas + verif_disp.all_tool_schemas
"""

from __future__ import annotations

from contextlib import contextmanager

from codegraph.tools.dispatcher import CodeGraphDispatcher, ToolDispatcher
from codegraph.persistence.repository import GraphRepository
from codegraph.persistence.connection import get_session


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
# DesignToolDispatcher — design-agent dispatcher with mutable lookups
# ══════════════════════════════════════════════════════════════════════════


class DesignToolDispatcher(CodeGraphDispatcher):
    """Design-agent dispatcher — inherits all codegraph tools + adds
    design validation, name checking, and design storage.

    Holds mutable lookups for prior designs, dependency APIs, and
    intercomponent boundaries.  The ``produce_oo_design`` tool stores
    the design on ``self.design_draft`` so that the
    :class:`VerificationDispatcher` can validate qname references
    against it.

    Usage::

        d = DesignToolDispatcher(
            prior_class_lookup={"Thermostat": "climate::Thermostat"},
            dependency_lookup={"std::vector": "std::vector"},
            intercomponent_classes=[
                {"qualified_name": "ui::Widget", "kind": "class", "name": "Widget"},
            ],
            component_namespace="climate",
        )
        schemas = d.all_tool_schemas
        result = d.dispatch("check_class_name", {"name": "Widget"})
    """

    def __init__(
        self,
        repo: GraphRepository | None = None,
        *,
        prior_class_lookup: dict[str, str] | None = None,
        dependency_lookup: dict[str, str] | None = None,
        intercomponent_classes: list[dict] | None = None,
        component_namespace: str = "",
        sibling_namespaces: list[str] | None = None,
    ):
        super().__init__(repo=repo)

        # ── Mutable context dictionaries ──
        self.prior_class_lookup: dict[str, str] = dict(prior_class_lookup or {})
        self.dependency_lookup: dict[str, str] = dict(dependency_lookup or {})
        self.intercomponent_classes: list[dict] = list(intercomponent_classes or [])
        self.component_namespace: str = component_namespace
        self.sibling_namespaces: list[str] = list(sibling_namespaces or [])

        # ── Mutable draft state ──
        self.design_draft: list[dict] | None = None

        # Register design-specific tools on top of codegraph tools
        from codegraph_design.tools.design_tools import register_all as _reg_design
        _reg_design(self)

    # ── Convenience setters ──────────────────────────────────────────────

    def add_prior_class(self, name: str, qualified_name: str) -> None:
        """Register a bare-name → qualified-name mapping for a newly
        designed class so that future ``check_class_name`` and
        ``validate_design`` calls can resolve it."""
        self.prior_class_lookup[name] = qualified_name

    def set_dependency_lookup(self, lookup: dict[str, str]) -> None:
        """Replace the dependency API lookup (name → qualified_name)."""
        self.dependency_lookup = dict(lookup)

    def set_intercomponent_classes(self, classes: list[dict]) -> None:
        """Replace the inter-component boundary class list."""
        self.intercomponent_classes = list(classes)


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
    to ``design_draft``, ``prior_class_lookup``,
    ``dependency_lookup``, and ``intercomponent_classes``.

    Usage::

        design_disp = DesignToolDispatcher(prior_class_lookup={...})
        verif_disp = VerificationDispatcher(design_dispatcher=design_disp)
    """

    def __init__(self, design_dispatcher: DesignToolDispatcher):
        super().__init__()
        self._design_dispatcher = design_dispatcher

        # Register verification tools
        from codegraph_design.tools.verification_tools import register_all as _reg_verif
        _reg_verif(self)

    # ── Delegate access to the design dispatcher's context ────────────────

    @property
    def design_draft(self) -> list[dict] | None:
        return self._design_dispatcher.design_draft

    @property
    def prior_class_lookup(self) -> dict[str, str]:
        return self._design_dispatcher.prior_class_lookup

    @property
    def dependency_lookup(self) -> dict[str, str]:
        return self._design_dispatcher.dependency_lookup

    @property
    def intercomponent_classes(self) -> list[dict]:
        return self._design_dispatcher.intercomponent_classes

    @property
    def draft_verifications(self) -> dict[str, list[dict]] | None:
        return getattr(self, "_draft_verifications", None)

    @draft_verifications.setter
    def draft_verifications(self, value: dict[str, list[dict]] | None) -> None:
        self._draft_verifications = value