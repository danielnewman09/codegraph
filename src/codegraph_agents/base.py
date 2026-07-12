"""Base agent class with LangGraph checkpointing.

Provides :class:`BaseAgent`, the abstract foundation for all codegraph
agents.  Subclasses define:

- ``name`` — stable agent identifier (e.g. ``"design_oo"``)
- ``system_prompt`` — :class:`~langchain_core.prompts.ChatPromptTemplate`
- ``context_needs`` — declarative context requirements
- ``final_tool_name`` — the tool that terminates the loop
- ``register_tools(dispatcher)`` — registers tools on the dispatcher
- ``build_initial_messages(context)`` — assembles the first user message
- ``build_result(state)`` — extracts structured result from final state

The agent's LangGraph has three nodes:

- ``think`` — model call (one LLM invocation per graph step)
- ``tools`` — tool execution (dispatches to registered handlers)
- ``extract`` — post-loop result extraction (terminal node)

The routing function decides whether to continue the tool loop
(think → tools → think → ...), extract the result (think → extract),
or end.  Checkpoints are written after every step.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from codegraph_agents.callbacks import (
    AgentCallback,
    FileLoggingCallback,
)
from codegraph_agents.config import AgentConfig
from codegraph_agents.state import AgentState

log = logging.getLogger("codegraph_agents")

_FILE_LOG_FORMAT = logging.Formatter(
    "%(asctime)s %(name)-26s %(levelname)-7s %(message)s"
)


class BaseAgent(ABC):
    """Stateful agent with LangGraph checkpointing.

    Subclasses must implement the abstract contract below.
    See :ref:`module docstring <codegraph_agents.base>` for details.

    Lifecycle::

        agent = DesignAgent(AgentConfig(hlr_uid="abc123"))
        result = agent.run()
        # On failure, resume from checkpoint:
        agent.resume("abc123")
        # Inspect state mid-run:
        state = agent.get_state("abc123")
    """

    # ── Subclass contract (override in concrete agents) ─────────

    name: ClassVar[str] = "base"
    """Stable agent identifier (e.g. ``"design_oo"``)."""

    system_prompt: ClassVar[ChatPromptTemplate]
    """System prompt template.  Formatted with loaded context."""

    context_needs: ClassVar[set[str]] = set()
    """Declarative context needs resolved by :class:`ContextProvider`."""

    final_tool_name: ClassVar[str] = ""
    """Tool that terminates the loop (triggers extraction)."""

    def __init__(
        self, config: AgentConfig | None = None
    ) -> None:
        self.config = config or AgentConfig()
        self.dispatcher = (
            self._create_dispatcher()
        )
        self._context: dict[str, Any] = {}
        self._graph = self._build_graph()

    # ── Abstract contract ───────────────────────────────────────

    @abstractmethod
    def _create_dispatcher(self) -> Any:
        """Create and return a tool dispatcher with all tools registered.

        Called once at ``__init__``.  Must return an object with
        ``dispatch(tool_name, tool_input) -> str`` and
        ``all_tool_schemas`` property.
        """
        ...

    @abstractmethod
    def build_initial_messages(
        self, context: dict[str, Any]
    ) -> list[BaseMessage]:
        """Build the initial ``HumanMessage`` from loaded context.

        Args:
            context: Resolved context dict (keys match
                ``context_needs``).

        Returns:
            A list with at least one ``HumanMessage``.
        """
        ...

    @abstractmethod
    def build_result(self, state: AgentState) -> Any:
        """Extract structured result from the final agent state.

        Called after the graph reaches the ``extract`` node.

        Args:
            state: The final :class:`AgentState`.

        Returns:
            An agent-specific result object.
        """
        ...

    # ── Context loading (overridable) ────────────────────────────

    def load_context(self) -> dict[str, Any]:
        """Resolve all ``context_needs`` from Neo4j.

        Uses :class:`~codegraph_agents.config.ContextProvider`
        to resolve each declared need.  Override for custom
        loading logic.

        Returns:
            Dict mapping need names to resolved values.
        """
        from codegraph_agents.context import ContextProvider

        ctx: dict[str, Any] = {}
        for need in self.context_needs:
            ctx[need] = ContextProvider.resolve(
                need, self.config
            )
        return ctx

    # ── LangGraph construction ──────────────────────────────────

    def _build_graph(self) -> StateGraph:
        """Build the agent's :class:`~langgraph.graph.StateGraph`.

        Structure::

            __start__ → think ⇄ tools
            think → extract → END

        The ``think`` node makes one LLM call.  The ``tools`` node
        executes any tool calls from the response.  The ``router``
        decides whether to continue, extract, or end.
        """
        workflow = StateGraph(AgentState)

        workflow.add_node("think", self._think_node)
        workflow.add_node("tools", self._tools_node)
        workflow.add_node("extract", self._extract_node)

        workflow.set_entry_point("think")

        workflow.add_conditional_edges(
            "think",
            self._router,
            {
                "continue": "tools",
                "extract": "extract",
                END: END,
            },
        )
        workflow.add_edge("tools", "think")
        workflow.add_edge("extract", END)

        checkpointer = (
            MemorySaver()
            if self.config.checkpoint
            else None
        )
        return workflow.compile(checkpointer=checkpointer)

    # ── Graph nodes ─────────────────────────────────────────────

    def _think_node(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """One LLM call.  Returns an ``AIMessage`` (possibly with
        tool calls) to append to the message history."""
        messages = state.get("messages", [])

        # Build the full message list: system + history
        try:
            system_text = self._format_system_prompt()
        except Exception as exc:
            log.error(
                "Failed to format system prompt: %s", exc,
                exc_info=True,
            )
            system_text = (
                "You are a software architect. "
                "Produce an OO class design."
            )

        full_messages = [
            SystemMessage(content=system_text),
            *messages,
        ]

        # Call the model
        try:
            tools_schemas = getattr(
                self.dispatcher, "all_tool_schemas", []
            )
            ai_message = self._call_model(
                full_messages, tools_schemas
            )
        except Exception as exc:
            log.error(
                "Model call failed: %s", exc, exc_info=True,
            )
            # Return a text-only AIMessage so the router can END
            from langchain_core.messages import AIMessage as Msg
            return {
                "messages": [
                    Msg(content=f"Error: {exc}")
                ]
            }

        log.info(
            "Model response: finish=%s, content_len=%d, tool_calls=%d",
            getattr(ai_message, "response_metadata", {}).get(
                "finish_reason", ""
            ),
            len(str(ai_message.content)) if ai_message.content else 0,
            len(getattr(ai_message, "tool_calls", []) or []),
        )

        return {"messages": [ai_message]}

    def _tools_node(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Execute tool calls from the last ``AIMessage``.

        Returns ``ToolMessage`` objects to append.
        """
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []

        results: list[ToolMessage] = []
        success = True
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_input = tc.get("args", {})
            tool_id = tc.get("id", "")

            try:
                output = self.dispatcher.dispatch(
                    tool_name, tool_input
                )
                results.append(
                    ToolMessage(
                        content=str(output),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
            except Exception as exc:
                error_msg = json.dumps(
                    {"error": str(exc)}
                )
                results.append(
                    ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                success = False
                log.warning(
                    "Tool '%s' failed: %s", tool_name, exc
                )

        turn = state.get("turn_count", 0)
        errors = state.get("error_count", 0)

        return {
            "messages": results,
            "turn_count": turn + 1,
            "error_count": errors + (0 if success else 1),
            "last_tool": tool_calls[-1]["name"] if tool_calls else "",
            "last_tool_success": success,
        }

    def _extract_node(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Terminal node — marks the phase as ``"done"``."""
        return {"phase": "done"}

    # ── Routing ─────────────────────────────────────────────────

    def _router(self, state: AgentState) -> str:
        """Decide: continue tool loop, extract result, or end."""
        messages = state.get("messages", [])
        if not messages:
            log.warning("Router: no messages → END")
            return END

        last = messages[-1]
        last_type = type(last).__name__
        tool_calls = getattr(last, "tool_calls", None) or []
        has_content = bool(getattr(last, "content", None))

        log.info(
            "Router: %d messages, last=%s, tool_calls=%d, content=%s, turn=%s",
            len(messages), last_type, len(tool_calls),
            has_content, state.get("turn_count", 0),
        )

        if not tool_calls:
            # Log the model's text response (if any) so we can see why it
            # didn't produce tool calls — critical for debugging 0-turn runs.
            content_preview = ""
            if has_content:
                raw = str(getattr(last, "content", ""))
                content_preview = raw[:500]
            log.warning(
                "Router: no tool_calls on last message → END. "
                "Model response (first 500 chars): %s",
                content_preview,
            )
            return END

        for tc in tool_calls:
            if tc.get("name") == self.final_tool_name:
                log.info("Router: final tool '%s' → extract", self.final_tool_name)
                return "extract"

        if state.get("turn_count", 0) >= self.config.max_turns:
            log.warning(
                "Agent '%s' reached max_turns (%d). Ending.",
                self.name,
                self.config.max_turns,
            )
            return END

        return "continue"

    # ── Model calling (OpenAI) ──────────────────────────────────

    def _format_system_prompt(self) -> str:
        """Format the system prompt template with loaded context.

        Uses ``partial`` to safely handle missing template variables
        — the prompt text may reference variables from the old
        agent that aren't populated by ``load_context()``.
        """
        from langchain_core.prompts.prompt import PromptTemplate
        # Collect all template variable names
        template_vars: set[str] = set()
        if isinstance(self.system_prompt, ChatPromptTemplate):
            for msg in self.system_prompt.messages:
                if hasattr(msg, "prompt") and hasattr(msg.prompt, "template"):
                    from string import Formatter
                    template_vars.update(
                        fn for _, fn, _, _ in
                        Formatter().parse(msg.prompt.template) if fn
                    )

        # Fill missing vars with empty string
        safe_context = dict(self._context)
        for var in template_vars:
            safe_context.setdefault(var, "")

        messages = self.system_prompt.format_messages(**safe_context)
        return str(messages[0].content) if messages else ""

    def _call_model(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, Any]],
    ) -> AIMessage:
        """Call the OpenAI API and return an ``AIMessage``.

        Converts LangChain messages to OpenAI dict format, calls
        the chat completions API, and parses the response.
        """
        oai_messages = self._messages_to_openai(messages)
        oai_tools = self._tools_to_openai(tools)

        log.info(
            "Calling model: %d messages, %d tools (timeout=%ds)",
            len(oai_messages), len(oai_tools),
            self.config.timeout,
        )

        response = self._raw_openai_call(oai_messages, oai_tools)

        log.info(
            "Model response: finish=%s, content_len=%d, tool_calls=%d",
            response.choices[0].finish_reason,
            len(response.choices[0].message.content or ""),
            len(response.choices[0].message.tool_calls or []),
        )

        return self._parse_openai_response(response)

    def _messages_to_openai(
        self, messages: list[BaseMessage]
    ) -> list[dict[str, Any]]:
        """Convert LangChain messages to OpenAI dict format.

        SystemMessage → ``{"role": "system", ...}``
        HumanMessage  → ``{"role": "user", ...}``
        AIMessage     → ``{"role": "assistant", ...}``
        ToolMessage   → ``{"role": "tool", "tool_call_id": ..., ...}``
        """
        result: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({
                    "role": "system",
                    "content": str(msg.content) if msg.content else "",
                })
            elif isinstance(msg, HumanMessage):
                result.append({
                    "role": "user",
                    "content": str(msg.content) if msg.content else "",
                })
            elif isinstance(msg, AIMessage):
                entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(msg.content) if msg.content else "",
                }
                existing_tool_calls = getattr(msg, "tool_calls", None)
                if existing_tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }
                        for tc in existing_tool_calls
                    ]
                result.append(entry)
            elif isinstance(msg, ToolMessage):
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": str(msg.content) if msg.content else "",
                })

        return result

    def _tools_to_openai(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert tool schemas to OpenAI API format.

        Our schemas may use Anthropic-native format
        (``name``, ``description``, ``input_schema``) or
        already be in OpenAI format (``function`` wrapping).
        Either way we produce OpenAI format:

        .. code-block:: json

            {"type": "function", "function": {"name": "...",
             "description": "...", "parameters": {...}}}
        """
        result: list[dict[str, Any]] = []
        for tool in tools:
            if "function" in tool:
                # Already in OpenAI format
                result.append(tool)
            elif "name" in tool:
                # Anthropic-native: convert
                result.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                })
        return result

    def _raw_openai_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Execute the raw OpenAI chat completions call."""
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {}
        if self.config.api_key:
            client_kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        client = OpenAI(timeout=self.config.timeout, **client_kwargs)

        create_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = self.config.tool_choice

        return client.chat.completions.create(**create_kwargs)

    def _parse_openai_response(self, response: Any) -> AIMessage:
        """Parse an OpenAI chat completion response into an ``AIMessage``.

        Handles both text-only and tool-call responses.
        """
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls: list[dict[str, Any]] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                args_str = tc.function.arguments
                try:
                    args = json.loads(args_str)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                })

        return AIMessage(
            content=content,
            **( {"tool_calls": tool_calls} if tool_calls else {}),
        )

    # ── File logging ───────────────────────────────────────────

    def _setup_file_logger(self) -> logging.FileHandler | None:
        """Attach a file handler so all operational logs land in
        ``{log_dir}/{short_run_id}_{agent_name}/agent.log``.

        Captures every logger that produces agent output:
        ``codegraph_agents``, ``codegraph_agents.design``,
        ``codegraph_agents.context``, ``codegraph_agents.decompose``,
        ``codegraph_design.tools``.
        """
        if not self.config.log_dir:
            return None

        short_id = self.config.run_id[:8]
        run_dir = (
            Path(self.config.log_dir)
            / f"{short_id}_{self.name}"
        )
        run_dir.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(
            run_dir / "agent.log", encoding="utf-8"
        )
        handler.setFormatter(_FILE_LOG_FORMAT)
        handler.setLevel(logging.DEBUG)

        for name in (
            "codegraph_agents",
            "codegraph_agents.design",
            "codegraph_agents.context",
            "codegraph_agents.decompose",
            "codegraph_design.tools",
        ):
            lg = logging.getLogger(name)
            lg.setLevel(logging.DEBUG)
            lg.addHandler(handler)

        return handler

    def _teardown_file_logger(
        self, handler: logging.FileHandler | None
    ) -> None:
        """Remove and close the file handler."""
        if handler is None:
            return
        for name in (
            "codegraph_agents",
            "codegraph_agents.design",
            "codegraph_agents.context",
            "codegraph_agents.decompose",
            "codegraph_design.tools",
        ):
            logging.getLogger(name).removeHandler(handler)
        handler.close()

    # ── Public API ──────────────────────────────────────────────

    def _build_callbacks(
        self,
    ) -> list[BaseCallbackHandler]:
        """Build the callback chain for this run."""
        callbacks: list[BaseCallbackHandler] = [
            AgentCallback(self.name),
        ]
        if self.config.log_dir:
            callbacks.append(
                FileLoggingCallback(
                    log_dir=self.config.log_dir,
                    agent_name=self.name,
                    run_id=self.config.run_id,
                )
            )
        return callbacks

    def run(self) -> Any:
        """Run the agent end-to-end.

        Loads context, builds initial messages, invokes the LangGraph,
        and returns the extracted result.

        Returns:
            The agent-specific result from
            :meth:`build_result`.

        Raises:
            RuntimeError: If the graph fails to reach completion.
        """
        self._context = self.load_context()
        initial_messages = self.build_initial_messages(
            self._context
        )

        initial_state: AgentState = {
            "messages": initial_messages,
            "agent_name": self.name,
            "phase": "start",
            "turn_count": 0,
            "error_count": 0,
        }

        thread_id = self.config.run_id
        run_config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
            },
            "callbacks": self._build_callbacks(),
        }

        file_handler = self._setup_file_logger()
        try:
            final_state = self._graph.invoke(
                initial_state, run_config
            )
        finally:
            self._teardown_file_logger(file_handler)

        # Write response.json
        self._write_response(final_state)

        return self.build_result(final_state)

    def resume(
        self,
        thread_id: str | None = None,
    ) -> Any:
        """Resume a paused or failed run from its last checkpoint.

        Args:
            thread_id: The thread ID to resume.  Defaults to
                ``config.run_id``.

        Returns:
            The extracted result from the resumed run.
        """
        resume_id = thread_id or self.config.run_id
        run_config: RunnableConfig = {
            "configurable": {
                "thread_id": resume_id,
            },
            "callbacks": self._build_callbacks(),
        }

        file_handler = self._setup_file_logger()
        try:
            final_state = self._graph.invoke(
                None, run_config
            )
        finally:
            self._teardown_file_logger(file_handler)

        self._write_response(final_state)
        return self.build_result(final_state)

    def get_state(
        self, thread_id: str | None = None
    ) -> AgentState | None:
        """Inspect checkpointed state for debugging.

        Args:
            thread_id: The thread ID to inspect.  Defaults to
                ``config.run_id``.

        Returns:
            The checkpointed :class:`AgentState`, or ``None`` if
            no checkpoint exists or checkpointing is disabled.
        """
        lookup_id = thread_id or self.config.run_id
        graph = self._graph
        if not hasattr(graph, "get_state"):
            return None

        cfg: RunnableConfig = {
            "configurable": {"thread_id": lookup_id},
        }
        snapshot = graph.get_state(cfg)
        return snapshot.values if snapshot else None

    # ── Response persistence ────────────────────────────────────

    def _write_response(
        self, state: AgentState
    ) -> None:
        """Write ``response.json`` if logging is enabled.

        Searches the message history for the final tool call
        and writes its parsed output.
        """
        if not self.config.log_dir:
            return

        result = self._extract_final_tool_output(state)
        if result is None:
            return

        short_id = self.config.run_id[:8]
        run_dir = (
            Path(self.config.log_dir)
            / f"{short_id}_{self.name}"
        )
        run_dir.mkdir(parents=True, exist_ok=True)

        response_path = run_dir / "response.json"
        response_path.write_text(
            json.dumps(result, indent=2, default=str),
            encoding="utf-8",
        )

    def _extract_final_tool_output(
        self, state: AgentState
    ) -> dict[str, Any] | None:
        """Extract the output of the final tool from message history.

        Walks the messages backward to find the ``ToolMessage``
        corresponding to :attr:`final_tool_name`.
        """
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, ToolMessage) and msg.name == self.final_tool_name:
                content = str(msg.content)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
        return None
