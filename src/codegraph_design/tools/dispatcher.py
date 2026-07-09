"""Design discovery dispatcher — extends CodeGraphDispatcher with
requirements-level discovery tools.

Mirrors the ticketing-system's ``DesignToolDispatcher`` pattern: inherits
all codegraph tools (graph_fetch, search_symbols, etc.) and adds
requirements discovery tools (search_requirements, get_hlr_dependencies,
list_requirements, get_requirement_traces, build_design_context).
"""

from __future__ import annotations

from codegraph.tools.dispatcher import CodeGraphDispatcher


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