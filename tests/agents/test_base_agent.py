"""Tests for BaseAgent — graph construction, routing, tool node."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END

from codegraph_agents.base import BaseAgent, AgentConfig


# ── Minimal concrete agent for testing ──────────────────────────


class _MinimalAgent(BaseAgent):
    """Agent with simple tools for graph/routing tests."""

    name = "minimal"
    system_prompt = ChatPromptTemplate.from_messages(
        [("system", "You are a minimal test agent.")]
    )
    context_needs: set[str] = set()
    final_tool_name = "finalize"

    def _create_dispatcher(self) -> Any:
        class DummyDispatcher:
            all_tool_schemas: list[dict] = []
            calls: list[tuple[str, dict]] = []

            def dispatch(self, tool_name: str, tool_input: dict) -> str:
                self.calls.append((tool_name, tool_input))
                return '{"ok": true}'

        self._dummy_dispatcher = DummyDispatcher()
        return self._dummy_dispatcher

    def build_initial_messages(
        self, context: dict[str, Any]
    ) -> list[BaseMessage]:
        return [HumanMessage(content="Test task")]

    def build_result(self, state: dict) -> Any:
        return {"phase": state.get("phase", "unknown")}


# ── Fixture ────────────────────────────────────────────────────


@pytest.fixture
def agent() -> _MinimalAgent:
    return _MinimalAgent(AgentConfig(max_turns=3))


# ── Graph construction ─────────────────────────────────────────


def test_graph_has_required_nodes(agent: _MinimalAgent) -> None:
    """Graph must have think, tools, extract, and boundary nodes."""
    nodes = agent._graph.get_graph().nodes
    assert "__start__" in nodes
    assert "__end__" in nodes
    assert "think" in nodes
    assert "tools" in nodes
    assert "extract" in nodes


def test_checkpointer_attached_when_enabled() -> None:
    """MemorySaver is attached when config.checkpoint=True."""
    a = _MinimalAgent(AgentConfig(checkpoint=True))
    assert a._graph.checkpointer is not None


def test_checkpointer_none_when_disabled() -> None:
    """No checkpointer when config.checkpoint=False."""
    a = _MinimalAgent(AgentConfig(checkpoint=False))
    assert a._graph.checkpointer is None


# ── Routing ────────────────────────────────────────────────────


def test_router_text_only_ends(agent: _MinimalAgent) -> None:
    """Model returns text without tool calls → END."""
    state = {"messages": [AIMessage(content="done")]}
    assert agent._router(state) == END


def test_router_final_tool_extracts(agent: _MinimalAgent) -> None:
    """Model calls the final tool → extract."""
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "finalize",
                        "args": {},
                    }
                ],
            )
        ]
    }
    assert agent._router(state) == "extract"


def test_router_non_final_tool_continues(agent: _MinimalAgent) -> None:
    """Model calls a non-final tool → continue."""
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "search_symbols",
                        "args": {"query": "X"},
                    }
                ],
            )
        ],
        "turn_count": 0,
    }
    assert agent._router(state) == "continue"


def test_router_max_turns_exceeded(agent: _MinimalAgent) -> None:
    """Non-final tool call at max_turns → END."""
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "search_symbols",
                        "args": {},
                    }
                ],
            )
        ],
        "turn_count": 3,  # equal to max_turns
    }
    assert agent._router(state) == END


def test_router_multiple_tools_final_last(agent: _MinimalAgent) -> None:
    """When finalize is mixed with real tools, route to 'tools' first.

    Real tools (e.g. commit_design_and_verifications) MUST execute
    before the agent terminates.  Only route to 'extract' when
    finalize is the *sole* tool call — that is tested separately
    in ``test_router_finalize_alone``.
    """
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "search_symbols",
                        "args": {},
                    },
                    {
                        "id": "t2",
                        "name": "finalize",
                        "args": {},
                    },
                ],
            )
        ]
    }
    # finalize mixed with real tools → execute the real tools first
    assert agent._router(state) == "continue"


def test_router_no_message(agent: _MinimalAgent) -> None:
    """Edge case: state with no messages → END."""
    state: dict = {"messages": []}
    assert agent._router(state) == END


# ── Tools node ─────────────────────────────────────────────────


def test_tools_node_dispatches_correctly(agent: _MinimalAgent) -> None:
    """Tools node dispatches tool calls and returns ToolMessages."""
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call1",
                        "name": "tool_a",
                        "args": {"key": "val1"},
                    },
                    {
                        "id": "call2",
                        "name": "tool_b",
                        "args": {"key": "val2"},
                    },
                ],
            )
        ],
        "turn_count": 0,
        "error_count": 0,
    }

    result = agent._tools_node(state, {})

    # Returns messages + state updates
    msgs = result["messages"]
    assert len(msgs) == 2
    assert all(isinstance(m, ToolMessage) for m in msgs)
    assert msgs[0].tool_call_id == "call1"
    assert msgs[0].name == "tool_a"
    assert msgs[1].tool_call_id == "call2"
    assert msgs[1].name == "tool_b"

    # Turn count incremented (once per tools_node, not per tool call)
    assert result["turn_count"] == 1

    # Dispatcher called
    assert len(agent._dummy_dispatcher.calls) == 2
    assert agent._dummy_dispatcher.calls[0] == (
        "tool_a",
        {"key": "val1"},
    )
    assert agent._dummy_dispatcher.calls[1] == (
        "tool_b",
        {"key": "val2"},
    )


def test_tools_node_handles_errors(agent: _MinimalAgent) -> None:
    """Tools node catches dispatch exceptions and returns error messages."""

    class FailingDispatcher:
        all_tool_schemas: list = []

        def dispatch(self, name: str, inp: dict) -> str:
            raise ValueError("simulated failure")

    agent.dispatcher = FailingDispatcher()

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "bad_tool",
                        "args": {},
                    }
                ],
            )
        ],
        "turn_count": 0,
        "error_count": 0,
    }

    result = agent._tools_node(state, {})

    msgs = result["messages"]
    assert len(msgs) == 1
    assert "simulated failure" in msgs[0].content

    # Error count incremented
    assert result["error_count"] == 1
    assert result["last_tool_success"] is False


# ── OpenAI response parsing ────────────────────────────────────


class TestOpenAIResponseParsing:
    """Tests for _parse_openai_response."""

    def test_text_only(self, agent: _MinimalAgent) -> None:
        """Response with only text content → AIMessage with content, no tool_calls."""
        ChoiceMsg = type("Msg", (), {"content": "I think this works", "tool_calls": None})
        Choice = type("Choice", (), {"message": ChoiceMsg()})
        response = type("Response", (), {"choices": [Choice()]})()

        msg = agent._parse_openai_response(response)
        assert isinstance(msg, AIMessage)
        assert msg.content == "I think this works"
        assert not msg.tool_calls

    def test_tool_calls(self, agent: _MinimalAgent) -> None:
        """Response with tool_calls → AIMessage with tool_calls."""
        TC = type("TC", (), {
            "id": "call_01",
            "function": type("Func", (), {
                "name": "search_symbols",
                "arguments": '{"query": "LayerGraph"}',
            })(),
        })
        ChoiceMsg = type("Msg", (), {"content": "", "tool_calls": [TC()]})
        Choice = type("Choice", (), {"message": ChoiceMsg()})
        response = type("Response", (), {"choices": [Choice()]})()

        msg = agent._parse_openai_response(response)
        assert isinstance(msg, AIMessage)
        assert msg.content == ""
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "search_symbols"
        assert msg.tool_calls[0]["args"] == {"query": "LayerGraph"}

    def test_mixed_text_and_tools(self, agent: _MinimalAgent) -> None:
        """Response with text AND tool_calls → both populated."""
        TC = type("TC", (), {
            "id": "call_02",
            "function": type("Func", (), {
                "name": "import_compound",
                "arguments": '{"qname": "X"}',
            })(),
        })
        ChoiceMsg = type("Msg", (), {"content": "Let me search", "tool_calls": [TC()]})
        Choice = type("Choice", (), {"message": ChoiceMsg()})
        response = type("Response", (), {"choices": [Choice()]})()

        msg = agent._parse_openai_response(response)
        assert msg.content == "Let me search"
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1

    def test_malformed_json_args(self, agent: _MinimalAgent) -> None:
        """Tool call with malformed JSON arguments → args defaults to {}."""
        TC = type("TC", (), {
            "id": "call_bad",
            "function": type("Func", (), {
                "name": "broken_tool",
                "arguments": "not json",
            })(),
        })
        ChoiceMsg = type("Msg", (), {"content": "", "tool_calls": [TC()]})
        Choice = type("Choice", (), {"message": ChoiceMsg()})
        response = type("Response", (), {"choices": [Choice()]})()

        msg = agent._parse_openai_response(response)
        assert msg.tool_calls[0]["args"] == {}

    def test_empty_content(self, agent: _MinimalAgent) -> None:
        """Response with empty (None) content → content is ''."""
        ChoiceMsg = type("Msg", (), {"content": None, "tool_calls": None})
        Choice = type("Choice", (), {"message": ChoiceMsg()})
        response = type("Response", (), {"choices": [Choice()]})()

        msg = agent._parse_openai_response(response)
        assert msg.content == ""


# ── OpenAI message conversion ──────────────────────────────────


class TestMessagesToOpenAI:
    """Tests for _messages_to_openai."""

    def test_system_message(self, agent: _MinimalAgent) -> None:
        result = agent._messages_to_openai([SystemMessage(content="sys")])
        assert result == [{"role": "system", "content": "sys"}]

    def test_human_message(self, agent: _MinimalAgent) -> None:
        result = agent._messages_to_openai([HumanMessage(content="hello")])
        assert result == [{"role": "user", "content": "hello"}]

    def test_ai_message_no_tool_calls(self, agent: _MinimalAgent) -> None:
        result = agent._messages_to_openai([AIMessage(content="ok")])
        assert result == [{"role": "assistant", "content": "ok"}]

    def test_ai_message_with_tool_calls(self, agent: _MinimalAgent) -> None:
        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "search",
                    "args": {"query": "x"},
                }
            ],
        )
        result = agent._messages_to_openai([msg])
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"][0]["id"] == "call_1"
        assert result[0]["tool_calls"][0]["type"] == "function"
        assert result[0]["tool_calls"][0]["function"]["name"] == "search"
        assert '"query": "x"' in result[0]["tool_calls"][0]["function"]["arguments"]

    def test_tool_message(self, agent: _MinimalAgent) -> None:
        msg = ToolMessage(content='{"ok": true}', tool_call_id="call_1", name="search")
        result = agent._messages_to_openai([msg])
        assert result == [
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'}
        ]

    def test_mixed_conversation(self, agent: _MinimalAgent) -> None:
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            HumanMessage(content="task"),
            AIMessage(content="ok"),
            ToolMessage(content="result", tool_call_id="c1"),
        ]
        result = agent._messages_to_openai(msgs)
        assert [m["role"] for m in result] == ["system", "user", "assistant", "tool"]


# ── OpenAI tool schema conversion ──────────────────────────────


class TestToolsToOpenAI:
    """Tests for _tools_to_openai."""

    def test_anthropic_native_format(self, agent: _MinimalAgent) -> None:
        tools = [
            {
                "name": "search",
                "description": "Search for symbols",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
        result = agent._tools_to_openai(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"
        assert result[0]["function"]["description"] == "Search for symbols"
        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_openai_format_passthrough(self, agent: _MinimalAgent) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object"},
                },
            }
        ]
        result = agent._tools_to_openai(tools)
        assert result == tools

    def test_empty_list(self, agent: _MinimalAgent) -> None:
        result = agent._tools_to_openai([])
        assert result == []


# ── Response extraction ───────────────────────────────────────


def test_extract_final_tool_output_finds_match(agent: _MinimalAgent) -> None:
    """Finds the ToolMessage matching final_tool_name in message history."""
    state = {
        "messages": [
            HumanMessage(content="task"),
            AIMessage(content="ok"),
            ToolMessage(
                content='{"design": [1,2,3]}',
                tool_call_id="t1",
                name="finalize",
            ),
        ]
    }
    result = agent._extract_final_tool_output(state)
    assert result is not None
    assert result == {"design": [1, 2, 3]}


def test_extract_final_tool_output_no_match(agent: _MinimalAgent) -> None:
    """Returns None if no ToolMessage matches final_tool_name."""
    state = {
        "messages": [
            HumanMessage(content="task"),
            AIMessage(content="ok"),
            ToolMessage(
                content="ok",
                tool_call_id="t1",
                name="search_symbols",
            ),
        ]
    }
    result = agent._extract_final_tool_output(state)
    assert result is None


# ── Config defaults ────────────────────────────────────────────


def test_agent_config_defaults() -> None:
    """AgentConfig has sensible defaults (env-aware)."""
    config = AgentConfig()
    # model resolves from LLM_MODEL env, falls back to "gpt-4o"
    assert isinstance(config.model, str) and len(config.model) > 0
    assert isinstance(config.base_url, str)
    assert isinstance(config.api_key, str)
    assert config.tool_choice in ("auto", "required", "none")
    assert config.max_tokens == 65536
    assert config.max_turns == 75
    assert config.checkpoint is True
    assert config.log_dir == "codegraph/logs"
    assert len(config.run_id) == 32  # auto-generated UUID hex
    assert AgentConfig(run_id="explicit").run_id == "explicit"


# ── State fields ───────────────────────────────────────────────


def test_agent_state_fields() -> None:
    """AgentState has all expected fields."""
    from codegraph_agents.state import AgentState

    fields = list(AgentState.__annotations__.keys())
    assert "messages" in fields
    assert "agent_name" in fields
    assert "phase" in fields
    assert "turn_count" in fields
    assert "error_count" in fields
    assert "last_tool" in fields
    assert "last_tool_success" in fields
    assert "run_id" not in fields  # config-level, not in state
