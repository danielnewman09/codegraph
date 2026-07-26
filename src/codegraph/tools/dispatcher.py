"""Tool dispatcher infrastructure for codegraph agent tools.

Provides :class:`ToolDispatcher` base class and
:class:`CodeGraphDispatcher` — a pre-built dispatcher with all
codegraph query, format, discovery, and lookup tools registered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager

from codegraph.persistence.repository import GraphRepository
from codegraph.export.format import export_graph, import_graph as format_import_graph
from codegraph.graph import LayerGraph


class ToolDispatcher:
    """Base class for tool dispatchers.

    Registers handler functions by tool name alongside their JSON
    schemas and dispatches calls to the appropriate handler.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], str]] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, schema: dict,
                 handler: Callable[[dict], str]) -> None:
        """Register a handler and its JSON schema for a tool name."""
        if name in self._handlers:
            raise ValueError(f"Duplicate tool handler: {name}")
        self._handlers[name] = handler
        self._schemas[name] = schema

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call to the registered handler."""
        handler = self._handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return handler(tool_input)

    @property
    def all_tool_schemas(self) -> list[dict]:
        """Return all registered tool schemas for LLM tools parameter."""
        return list(self._schemas.values())


class CodeGraphDispatcher(ToolDispatcher):
    """Pre-built dispatcher with all codegraph tools registered.

    Holds a :class:`GraphRepository` for Neo4j access and an in-memory
    ``current_graph`` that tools can cache.

    Usage::

        d = CodeGraphDispatcher()
        schemas = d.all_tool_schemas
        result = d.dispatch("graph_fetch", {"tag": "design"})
    """

    def __init__(self, repo: GraphRepository | None = None):
        super().__init__()
        self.repo = repo or GraphRepository()
        self.current_graph: LayerGraph | None = None

        self._register_all()

    def _register_all(self) -> None:
        """Register all query, format, info, discovery, and lookup tools."""
        from codegraph.tools.query import register_all as _reg_query
        from codegraph.tools.format_tools import register_all as _reg_format
        from codegraph.tools.info import register_all as _reg_info
        from codegraph.tools.discovery import register_all as _reg_discovery
        from codegraph.tools.lookup import register_all as _reg_lookup

        _reg_query(self)
        _reg_format(self)
        _reg_info(self)
        _reg_discovery(self)
        _reg_lookup(self)


def create_dispatcher() -> CodeGraphDispatcher:
    """Create a ready-to-use :class:`CodeGraphDispatcher`."""
    return CodeGraphDispatcher()


# ── Shared serialization helper ───────────────────────────────────────────


def _serialize_graph(graph: LayerGraph, fmt: str,
                     public_only: bool = True) -> str:
    """Serialize a LayerGraph to the requested format."""
    if fmt == "markdown":
        return export_graph(graph, format="markdown",
                           public_only=public_only)
    elif fmt == "plantuml":
        return export_graph(graph, format="plantuml")
    elif fmt == "json":
        return export_graph(graph, format="json")
    return export_graph(graph, format="markdown")
