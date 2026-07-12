"""LangGraph-compatible agent state definitions.

All agents share the same :class:`AgentState` TypedDict.  LangGraph
checkpoints this after every graph step (think → tools → extract),
enabling resume-on-failure and mid-run inspection.

Mutable codegraph objects (:class:`~codegraph.graph.LayerGraph`,
:class:`~codegraph.tools.dispatcher.ToolDispatcher`) are passed via
``config["configurable"]`` rather than the state dict, avoiding
serialization overhead on checkpoint writes.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State that flows through every agent's LangGraph.

    Checkpointed after every step.  Tool handlers access mutable
    codegraph objects (LayerGraph, dispatcher) via
    ``config["configurable"]`` so they don't need serialization.

    Fields:
        messages: Accumulated message history
            (system + human + AI + tool results).
            Uses ``add_messages`` reducer for append-only semantics.
        agent_name: Stable agent identifier
            (e.g. ``"design_oo"``, ``"decompose_hlr"``).
        phase: Current phase label
            (``"start"``, ``"discover"``, ``"design"``,
            ``"verify"``, ``"commit"``, ``"done"``).
        turn_count: Number of model invocations so far.
        error_count: Cumulative tool execution errors.
        last_tool: Name of the most recently called tool
            (for debugging / monitoring).
        last_tool_success: Whether the last tool call succeeded.
    """

    messages: Annotated[list[BaseMessage], add_messages]

    agent_name: str

    phase: str
    turn_count: int
    error_count: int

    last_tool: str
    last_tool_success: bool
