"""Agent tools for codegraph — LLM-ready query, format, discovery,
and lookup operations.

Module structure (one file per tool family)::

    tools/
    ├── __init__.py          # This file — re-exports
    ├── dispatcher.py        # ToolDispatcher, CodeGraphDispatcher
    ├── query.py             # graph_fetch, graph_fetch_namespace, etc.
    ├── format_tools.py      # graph_format_export, graph_format_import
    ├── info.py              # graph_list_tags
    ├── discovery.py         # search_symbols, get_compound, get_member, etc.
    └── lookup.py            # container_lookup, alias_lookup, dependency_list

Usage::

    from codegraph.tools import CodeGraphDispatcher
    from llm_caller import call_tool_loop

    dispatcher = CodeGraphDispatcher()

    result = call_tool_loop(
        system="You are a design agent...",
        messages=[{"role": "user", "content": "Review current design"}],
        tools=dispatcher.all_tool_schemas,
        final_tool_name="graph_format_export",
        tool_dispatcher=dispatcher.dispatch,
    )
"""

from codegraph.tools.dispatcher import (
    CodeGraphDispatcher,
    ToolDispatcher,
    create_dispatcher,
)

__all__ = [
    "CodeGraphDispatcher",
    "ToolDispatcher",
    "create_dispatcher",
]
