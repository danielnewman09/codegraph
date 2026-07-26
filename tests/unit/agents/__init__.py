"""Unit tests for codegraph_agents package — Phase 1 infrastructure."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

from codegraph_agents.base import BaseAgent, AgentConfig
from codegraph_agents.state import AgentState
from codegraph_agents.config import ContextProvider
from codegraph_agents.callbacks import FileLoggingCallback
