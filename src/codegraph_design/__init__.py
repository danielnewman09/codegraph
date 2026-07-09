"""codegraph_design — tools for design discovery.

Mirrors the structure of ``ticketing_system/backend_migrated/`` with
tools and dispatchers for the design discovery workflow.

The package provides:

- :class:`DesignDiscoveryDispatcher` — extends CodeGraphDispatcher with
  requirements-level discovery tools (search, dependency traversal,
  traceability, context assembly).

The discovery workflow is orchestrated by the Pi subagent
``code-analysis.design-discovery``, which calls the ``codegraph_discover``
MCP tool. No Python agent class is needed — the tools are the backend,
and the Pi subagent provides the LLM-driven orchestration.

For programmatic (non-LLM) use, call the dispatcher directly::

    from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher

    d = DesignDiscoveryDispatcher()
    result = d.dispatch("build_design_context", {
        "feature_description": "Add PlantUML export",
        "component_name": "Architecture Diagram Generator",
    })
"""