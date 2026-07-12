"""Codegraph Agents — stateful LangGraph-based agent framework.

Provides :class:`BaseAgent` for building LLM agents with checkpointing,
structured logging, and declarative context loading.  Concrete agents
live in sub-packages (``design``, ``decompose``, ``feedback``).

Usage::

    from codegraph_agents import BaseAgent, AgentConfig
    from codegraph_agents.design import DesignAgent

    config = AgentConfig(hlr_uid="abc123", log_dir="codegraph/logs")
    agent = DesignAgent(config)
    result = agent.run()

Core exports:

- :class:`BaseAgent` — abstract foundation for all agents
- :class:`AgentConfig` — typed configuration for agent runs
- :class:`AgentState` — LangGraph-compatible state TypedDict
- :class:`ContextProvider` — declarative context resolution
- :class:`AgentCallback` — structured logging callback
- :class:`FileLoggingCallback` — file-based logging callback
"""

from codegraph_agents.base import BaseAgent
from codegraph_agents.callbacks import (
    AgentCallback,
    FileLoggingCallback,
)
from codegraph_agents.config import AgentConfig
from codegraph_agents.context import ContextProvider
from codegraph_agents.state import AgentState

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "AgentState",
    "ContextProvider",
    "AgentCallback",
    "FileLoggingCallback",
]
