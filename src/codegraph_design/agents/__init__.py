"""Agents package for codegraph_design.

The design discovery workflow is orchestrated by the Pi subagent
``code-analysis.design-discovery``, which calls the ``codegraph_discover``
MCP tool. No Python agent class is needed — the tools in
``codegraph_design.tools`` are the backend, and the Pi subagent provides
the LLM-driven orchestration.

For programmatic (non-LLM) use, call the dispatcher directly::

    from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher

    d = DesignDiscoveryDispatcher()
    result = d.dispatch("build_design_context", {
        "feature_description": "Add PlantUML export",
        "component_name": "Architecture Diagram Generator",
    })
"""