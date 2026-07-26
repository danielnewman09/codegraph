# Agents Hybrid Architecture Plan

**Status**: Draft for review
**Date**: 2026-07-11

## 1. Module Layout

New package `codegraph_agents/` at `src/codegraph_agents/`, alongside
existing packages.  Follows the same `codegraph_*` naming convention.

```
src/codegraph_agents/
├── __init__.py             # Public API: BaseAgent, AgentConfig, ContextProvider
├── base.py                 # BaseAgent class
├── config.py               # AgentConfig, ContextProvider
├── callbacks.py            # Structured logging callbacks
├── state.py                # AgentState TypedDicts, serialization helpers
│
├── design/                 # Design agent (migrated from codegraph_design)
│   ├── __init__.py
│   ├── agent.py            # DesignAgent(BaseAgent)
│   ├── prompts.py          # ChatPromptTemplate definitions
│   ├── tools.py            # Tool registration (moved from design_tools.py)
│   ├── smells.py           # Design smell checks (moved from design_smells.py)
│   └── verify.py           # Verification tools (moved from verification_tools.py)
│
├── decompose/              # Decompose agent (migrated from codegraph_design)
│   ├── __init__.py
│   ├── agent.py            # DecomposeAgent(BaseAgent)
│   ├── prompts.py          # ChatPromptTemplate definitions
│   └── tools.py            # Validation + dependency discovery tools
│
└── feedback/               # Feedback agent (migrated from codegraph_feedback)
    ├── __init__.py
    ├── agent.py            # FeedbackAgent(BaseAgent)
    ├── prompts.py          # ChatPromptTemplate definitions
    └── tools.py            # Feedback analysis tools

Existing packages affected:
├── codegraph_design/       # → DEPRECATED, re-exports from codegraph_agents.design
├── codegraph_feedback/     # → DEPRECATED, re-exports from codegraph_agents.feedback
└── codegraph_requirements/ # → persistence.py moves to codegraph_agents/persistence.py
                              (unified scaffold + design persistence)
```

**Dependency additions** (to pyproject.toml):

```toml
dependencies = [
    "langchain-core>=0.3.0",   # messages, prompts, callbacks
    "langgraph>=0.2.0",        # checkpointing, StateGraph
]
```

## 2. `AgentConfig` — typed configuration

```python
# codegraph_agents/config.py

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class AgentConfig:
    """Configuration for a single agent run."""
    model: str = ""
    max_tokens: int = 65536
    max_turns: int = 75
    log_dir: str = ""
    checkpoint: bool = True        # Enable LangGraph checkpointing
    interrupt_after: str = ""      # Phase name to pause after (human-in-the-loop)

    # Context loading
    component_namespace: str = ""
    hlr_uid: str = ""

    # Retry
    max_retries: int = 1           # Retry on validation failure
```

## 3. `AgentState` — LangGraph-compatible typed state

```python
# codegraph_agents/state.py

from typing import Annotated, Any
from operator import add

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    """State that flows through every agent's LangGraph.

    LangGraph checkpoints this after every step.  Tool handlers
    access mutable codegraph objects (LayerGraph, dispatcher) via
    ``config["configurable"]`` so they don't need serialization.
    """
    # Message history — accumulated via add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Agent identity
    agent_name: str
    hlr_uid: str

    # Phase tracking (agents advance through phases explicitly)
    phase: str                     # "discover" | "design" | "verify" | "commit" | "done"
    turn_count: int                # Incremented per model call

    # Visibility markers (for debugging / monitoring)
    last_tool: str                 # Last tool called
    last_tool_success: bool        # Whether it succeeded
    error_count: int               # Cumulative tool errors
```

## 4. `BaseAgent` — core abstraction

```python
# codegraph_agents/base.py

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from codegraph_agents.config import AgentConfig
from codegraph_agents.state import AgentState
from codegraph_agents.callbacks import AgentCallback
from codegraph.tools.dispatcher import ToolDispatcher

log = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Stateful agent with LangGraph checkpointing.

    Subclasses define:
      - ``name: ClassVar[str]`` — stable agent identifier (e.g. "design_oo")
      - ``system_prompt: ChatPromptTemplate`` — system prompt as a LangChain template
      - ``context_needs: set[str]`` — declarative context requirements
      - ``final_tool_name: str`` — tool that terminates the loop
      - ``register_tools(dispatcher)`` — registers tools on the dispatcher
      - ``build_initial_messages(context)`` — assembles the first user message
      - ``build_result(state)`` — extracts structured result from final state

    The agent's LangGraph has three nodes:
      - ``think`` — model calls tools
      - ``tools`` — tool execution node
      - ``extract`` — post-loop result extraction

    The routing function decides whether to continue the tool loop,
    advance to a new phase, or end.  Subclasses can override routing
    for phase-based workflows.
    """

    name: ClassVar[str] = "base"
    system_prompt: ClassVar[ChatPromptTemplate]
    context_needs: ClassVar[set[str]] = set()
    final_tool_name: ClassVar[str]

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self.dispatcher = ToolDispatcher()
        self._context: dict[str, Any] = {}
        self._callbacks: list[BaseCallbackHandler] = []
        self._checkpointer = MemorySaver() if self.config.checkpoint else None

        # Let subclasses register their tools
        self.register_tools(self.dispatcher)

        # Build the graph once at construction
        self._graph = self._build_graph()

    # ── Subclass contract ──────────────────────────────────────────

    @abstractmethod
    def register_tools(self, dispatcher: ToolDispatcher) -> None:
        """Register tools on *dispatcher*.  Called once at __init__."""
        ...

    @abstractmethod
    def build_initial_messages(self, context: dict) -> list[BaseMessage]:
        """Build the initial HumanMessage from loaded context."""
        ...

    @abstractmethod
    def build_result(self, state: AgentState) -> Any:
        """Extract structured result from final state."""
        ...

    def load_context(self) -> dict:
        """Resolve ``context_needs`` from Neo4j.  Override for custom loading."""
        from codegraph_agents.config import ContextProvider
        ctx: dict[str, Any] = {}
        for need in self.context_needs:
            ctx[need] = ContextProvider.resolve(need, self.config)
        return ctx

    # ── LangGraph construction ─────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        """Build the agent's StateGraph.

        Default structure:
            __start__ → think ⇄ tools
            think → extract → END
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

        return workflow.compile(checkpointer=self._checkpointer)

    # ── Graph nodes ────────────────────────────────────────────────

    def _think_node(self, state: AgentState, config: RunnableConfig) -> dict:
        """Model thinks and optionally calls a tool."""
        from llm_caller import call_tool_loop

        # For the hybrid: we use our own tool loop here.
        # LangGraph's role is checkpointing + routing, not model calling.
        # The tool loop runs within this node until it either:
        #   a) calls the final tool → phase="commit"
        #   b) hits max turns → error state
        #   c) calls a phase-transition tool → phase update

        # In practice, each "think" invocation is ONE model call,
        # and the graph loops think → tools → think → ...
        messages = state.get("messages", [])
        system_text = self.system_prompt.format(**self._context)

        # Single model call, not full loop
        result = self._single_model_call(system_text, messages)
        return result

    def _tools_node(self, state: AgentState, config: RunnableConfig) -> dict:
        """Execute the tool call from the last model message."""
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", [])

        results = []
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_input = tc["args"]
            try:
                output = self.dispatcher.dispatch(tool_name, tool_input)
                results.append(ToolMessage(
                    content=str(output),
                    tool_call_id=tc["id"],
                    name=tool_name,
                ))
            except Exception as exc:
                results.append(ToolMessage(
                    content=json.dumps({"error": str(exc)}),
                    tool_call_id=tc["id"],
                    name=tool_name,
                ))

        return {"messages": results, "turn_count": state.get("turn_count", 0) + 1}

    def _extract_node(self, state: AgentState, config: RunnableConfig) -> dict:
        """Post-loop extraction.  Terminal node."""
        return {"phase": "done"}

    # ── Routing ────────────────────────────────────────────────────

    def _router(self, state: AgentState) -> str:
        """Decide: continue tool loop, extract result, or end."""
        last_msg = state["messages"][-1]

        # If the final tool was just called, transition to extract
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == self.final_tool_name:
                    return "extract"

        # If the model wants to call a tool, continue the loop
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            # Check turn limit
            if state.get("turn_count", 0) >= self.config.max_turns:
                return END
            return "continue"

        # No tool call and not final tool → end
        return END

    # ── Public API ─────────────────────────────────────────────────

    def run(self) -> Any:
        """Run the agent end-to-end.  Returns the extracted result."""
        self._context = self.load_context()
        initial_messages = self.build_initial_messages(self._context)

        initial_state: AgentState = {
            "messages": initial_messages,
            "agent_name": self.name,
            "hlr_uid": self.config.hlr_uid,
            "phase": "start",
            "turn_count": 0,
            "error_count": 0,
        }

        run_config: RunnableConfig = {
            "configurable": {
                "thread_id": self.config.hlr_uid or "default",
                "dispatcher": self.dispatcher,
                "context": self._context,
            },
            "callbacks": self._callbacks + [AgentCallback(self.name)],
        }

        final_state = self._graph.invoke(initial_state, run_config)
        return self.build_result(final_state)

    def resume(self, thread_id: str, approval: dict | None = None) -> Any:
        """Resume a paused run (e.g. after human review)."""
        run_config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
        }
        if approval:
            run_config["configurable"]["approval"] = approval

        final_state = self._graph.invoke(None, run_config)
        return self.build_result(final_state)

    def get_state(self, thread_id: str) -> AgentState | None:
        """Inspect checkpointed state for debugging."""
        if not self._checkpointer:
            return None
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = self._graph.get_state(config)
        return snapshot.values if snapshot else None
```

## 5. `DesignAgent` — first concrete implementation

```python
# codegraph_agents/design/agent.py

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from codegraph_agents.base import BaseAgent, AgentConfig, AgentState
from codegraph_agents.design.prompts import DESIGN_SYSTEM_PROMPT
from codegraph.tools.dispatcher import ToolDispatcher


class DesignAgent(BaseAgent):
    """Design agent — produce OO class design + resolve verification stubs.

    Lifecycle:
      1. load_context() → loads HLR, LLRs, component namespace,
         prior design compounds, sibling namespaces from Neo4j
      2. build_initial_messages() → assembles HumanMessage with
         requirements text, notional verification stubs, component hint
      3. run() → enters LangGraph:
         a. think: model proposes design / verifications
         b. tools: dispatcher executes tools (validate_design,
            produce_oo_design, draft_verifications, etc.)
         c. router: detects "commit_design_and_verifications" → extract
         d. extract: reconciles scaffold → design, persists to Neo4j
      4. build_result() → returns DesignResult with counts
    """

    name = "design_oo"
    context_needs = {
        "hlr_subtree",            # HLR + LLRs + existing scaffold
        "component_namespace",    # namespace constraint
        "prior_design_compounds", # classes already designed for other HLRs
        "sibling_namespaces",     # other components in same project
    }
    final_tool_name = "commit_design_and_verifications"

    def register_tools(self, dispatcher: ToolDispatcher) -> None:
        from codegraph_agents.design.tools import register_design_tools
        from codegraph_agents.design.smells import register_smell_tools
        from codegraph_agents.design.verify import register_verification_tools
        from codegraph.tools.query import register_all as register_codegraph_tools

        register_codegraph_tools(dispatcher)
        register_design_tools(dispatcher)
        register_smell_tools(dispatcher)
        register_verification_tools(dispatcher)

    def build_initial_messages(self, context: dict) -> list[BaseMessage]:
        hlr = context["hlr"]
        llrs = context["llrs"]
        notional = context["notional_verifications"]

        ns = context.get("component_namespace", "")
        ns_block = f"\n\nThe required namespace is: `{ns}`" if ns else ""

        comp = context.get("component_name", "")
        comp_block = f"\n\nThis HLR belongs to component: **{comp}**" if comp else ""

        return [HumanMessage(content=f"""\
Design the object-oriented class structure and resolve verification stubs
for the following requirements:

HLR: {hlr.description}
{comp_block}
{ns_block}

{notional.to_prompt_text()}
""")]

    def build_result(self, state: AgentState) -> DesignResult:
        # Extract from the final tool message
        last_msg = state["messages"][-1]
        # ... parse JSON from commit_design_and_verifications output
        raw = json.loads(last_msg.content)
        return DesignResult(
            design=raw.get("design", []),
            verifications=raw.get("verifications", []),
        )
```

## 6. Checkpointing in practice

The key value of LangGraph checkpointing for us:

```
Turn 0  → state checkpointed (empty context_graph, no design draft)
Turn 1  → model calls import_compound("codegraph.graph.LayerGraph")
Turn 2  → tool result: context_graph now has 12 entries
         → CHECKPOINT: {phase: "discover", context_graph_keys: 12, turn_count: 2}
Turn 3  → model calls import_compound("codegraph.export.plantuml.PlantUMLExporter")
Turn 4  → tool result: context_graph now has 8 more entries
... (continues designing)
Turn 37 → RateLimitError from Anthropic API
         → Agent.run() raises
         → User calls agent.resume("hlr-uid-abc")
         → Graph picks up from Turn 36's checkpoint
         → Only burns 38 turns, not 75
```

Without checkpointing, a rate limit at turn 37 means restarting the entire
75-turn loop from scratch, burning ~337K tokens.

## 7. Callback-based observability

```python
# codegraph_agents/callbacks.py

import json
import time
import logging
from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("codegraph_agents")

class AgentCallback(BaseCallbackHandler):
    """Structured event emitter for agent lifecycle.

    Emits JSON-line events that can be routed to files, Elasticsearch,
    Datadog, or just structured log handlers.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._tool_start_times: dict[str, float] = {}

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._llm_start = time.time()
        invocation = kwargs.get("invocation_params", {})
        log.info("llm_start", extra={
            "event": "llm_start",
            "agent": self.agent_name,
            "model": invocation.get("model", ""),
            "prompt_len": sum(len(p) for p in prompts[0]) if prompts else 0,
        })

    def on_llm_end(self, response, **kwargs):
        duration_ms = int((time.time() - self._llm_start) * 1000)
        usage = response.llm_output.get("usage", {})
        tool_calls = []
        for gen in response.generations:
            msg = gen[0].message if isinstance(gen, list) else gen.message
            if hasattr(msg, "tool_calls"):
                tool_calls = [tc["name"] for tc in msg.tool_calls]

        log.info("llm_end", extra={
            "event": "llm_end",
            "agent": self.agent_name,
            "duration_ms": duration_ms,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "tool_calls": tool_calls,
        })

    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times[run_id] = time.time()
        log.info("tool_start", extra={
            "event": "tool_start",
            "agent": self.agent_name,
            "tool": serialized.get("name", "?"),
            "input": str(input_str)[:500],
        })

    def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        start = self._tool_start_times.pop(run_id, time.time())
        duration_ms = int((time.time() - start) * 1000)
        log.info("tool_end", extra={
            "event": "tool_end",
            "agent": self.agent_name,
            "tool": kwargs.get("name", "?"),
            "duration_ms": duration_ms,
        })

    def on_tool_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times.pop(run_id, None)
        log.error("tool_error", extra={
            "event": "tool_error",
            "agent": self.agent_name,
            "tool": kwargs.get("name", "?"),
            "error": str(error)[:500],
        })

    def on_chain_start(self, serialized, inputs, **kwargs):
        """Agent run starts."""
        log.info("agent_start", extra={
            "event": "agent_start",
            "agent": self.agent_name,
        })

    def on_chain_end(self, outputs, **kwargs):
        """Agent run ends."""
        log.info("agent_end", extra={
            "event": "agent_end",
            "agent": self.agent_name,
        })
```

## 8. ContextProvider — declarative context loading

```python
# codegraph_agents/config.py (additions)

from typing import Callable, Any

class ContextProvider:
    """Resolve declarative context needs from Neo4j.

    Each "context need" is a string key (e.g. "hlr_subtree") that
    maps to a resolver function.  Agents declare their needs in
    ``context_needs`` and the provider resolves them before the
    agent runs.

    Resolvers are registered at module load time.  Custom resolvers
    can be added by applications that extend codegraph.
    """

    _resolvers: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, resolver: Callable[[AgentConfig], Any]) -> None:
        if name in cls._resolvers:
            raise ValueError(f"Context need '{name}' already registered")
        cls._resolvers[name] = resolver

    @classmethod
    def resolve(cls, need: str, config: AgentConfig) -> Any:
        resolver = cls._resolvers.get(need)
        if resolver is None:
            raise ValueError(
                f"Unknown context need: '{need}'. "
                f"Available: {list(cls._resolvers.keys())}"
            )
        return resolver(config)


# ── Built-in resolvers ─────────────────────────────────────────────

def _resolve_hlr_subtree(config: AgentConfig) -> dict:
    from codegraph.persistence.repository import GraphRepository
    from codegraph_requirements.models import HLR

    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        raise ValueError(f"HLR {config.hlr_uid} not found")

    repo = GraphRepository()
    graph = repo.get_hlr_subtree(config.hlr_uid)

    # Extract HLR, LLRs, notional verifications from the graph
    return _extract_hlr_context(hlr, graph)


def _resolve_component_namespace(config: AgentConfig) -> str:
    from codegraph_requirements.models import HLR
    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    if not hlr:
        return ""
    comps = hlr.component.all()
    return getattr(comps[0], "namespace", "") if comps else ""


def _resolve_prior_design_compounds(config: AgentConfig) -> list[dict]:
    from codegraph_requirements.models import HLR
    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    context_classes: list[dict] = []
    for other_hlr in HLR.nodes.all():
        if other_hlr.uid == config.hlr_uid:
            continue
        for target in other_hlr.design_compounds.all():
            context_classes.append({
                "qualified_name": target.qualified_name,
                "name": target.name or "",
                "kind": getattr(target, "kind", "class"),
            })
    return context_classes


def _resolve_sibling_namespaces(config: AgentConfig) -> list[str]:
    from codegraph_requirements.models import HLR
    hlr = HLR.nodes.get_or_none(uid=config.hlr_uid)
    namespaces: list[str] = []
    seen: set[str] = set()
    for other_hlr in HLR.nodes.all():
        if other_hlr.uid == config.hlr_uid:
            continue
        comps = other_hlr.component.all()
        if comps:
            ns = getattr(comps[0], "namespace", "")
            if ns and ns not in seen:
                seen.add(ns)
                namespaces.append(ns)
    return namespaces


# Register built-ins
ContextProvider.register("hlr_subtree", _resolve_hlr_subtree)
ContextProvider.register("component_namespace", _resolve_component_namespace)
ContextProvider.register("prior_design_compounds", _resolve_prior_design_compounds)
ContextProvider.register("sibling_namespaces", _resolve_sibling_namespaces)
```

## 9. Architecture diagram

```
┌────────────────────────────────────────────────────────────────┐
│                       Agent Runner                              │
│  (CLI, MCP bridge, or programmatic)                            │
│                                                                 │
│   agent = DesignAgent(config)                                   │
│   result = agent.run()          # single call                   │
│   state = agent.get_state(id)   # inspect checkpoint            │
│   agent.resume(id)              # resume after error            │
└──────────────┬─────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                         BaseAgent                                │
│                                                                   │
│  load_context()      build_initial_messages()                     │
│        │                      │                                   │
│        ▼                      ▼                                   │
│  ┌──────────┐        ┌──────────────────┐                        │
│  │ Context  │        │ LangGraph State  │                        │
│  │ Provider │        │   Graph           │                        │
│  │          │        │                    │                        │
│  │ Neo4j ◄──┤        │  ┌──────────────┐ │                        │
│  │ queries  │        │  │    think     │ │  ← model + prompt      │
│  └──────────┘        │  │              │ │                        │
│                      │  └──┬───────┬───┘ │                        │
│                      │     │       │     │                        │
│                      │     ▼       ▼     │                        │
│                      │  ┌────┐ ┌───────┐ │                        │
│                      │  │tools│ │extract│ │  ← tool dispatch +    │
│                      │  │     │ │       │ │     result extraction │
│                      │  └──┬──┘ └───┬───┘ │                        │
│                      │     │         │     │                        │
│                      │     └───loop──┘     │                        │
│                      │                    │                        │
│                      │  MemorySaver       │  ← checkpoints after   │
│                      │  (checkpoints)     │     every step         │
│                      └────────────────────┘                        │
│                                                                   │
│  Callbacks: on_llm_start → on_tool_start → on_tool_end → ...     │
│  (structured JSON-line events, route to any backend)              │
└──────────────────────────────────────────────────────────────────┘

Dependencies:
  langchain-core  → messages, prompts, callbacks (lightweight, 5 deps)
  langgraph       → StateGraph, MemorySaver, checkpointing (10 deps)
  llm-caller      → kept for single model calls (no LangChain providers)
  codegraph       → LayerGraph, GraphRepository, ToolDispatcher (existing)
```

## 10. Migration plan

### Phase 1: Infrastructure (no behavior change)

1. **Add `codegraph_agents/` package** with `base.py`, `config.py`,
   `state.py`, `callbacks.py`.  Not yet wired to anything.
2. **Add `langchain-core` and `langgraph` to pyproject.toml**.
3. **Write unit tests** for `BaseAgent` graph construction, routing,
   checkpoint serialization.  Mock the model calls.
4. **Wire `codegraph_agents` into `pyproject.toml` packages**.

_Deliverable_: `BaseAgent` class exists and is tested in isolation.
No existing behavior is changed.

### Phase 2: Port DesignAgent (backward-compatible)

1. **Create `codegraph_agents/design/agent.py`** — `DesignAgent(BaseAgent)`.
2. **Move tool schemas and handlers** from `codegraph_design/tools/design_tools.py`
   to `codegraph_agents/design/tools.py`.  Handlers become methods or
   module-level functions that take `dispatcher` instead of `ctx`.
3. **Move verification tools** from `codegraph_design/tools/verification_tools.py`
   to `codegraph_agents/design/verify.py`.
4. **Move design smells** to `codegraph_agents/design/smells.py`.
5. **Move prompt builders** to `codegraph_agents/design/prompts.py`,
   converting to `ChatPromptTemplate`.
6. **Add `codegraph_design` deprecation shim**: import `DesignAgent` and
   `design_and_persist_hlr` from new location, re-export.

_Deliverable_: `DesignAgent.run()` produces identical results to
`design_and_persist_hlr()`.  Existing tests pass with new imports.

### Phase 3: Port DecomposeAgent

1. **Create `codegraph_agents/decompose/agent.py`** — `DecomposeAgent(BaseAgent)`.
2. **Move decomposition validation** from `decompose_hlr.py` to
   `codegraph_agents/decompose/tools.py`.
3. **Move dependency discovery** tools.
4. **Add `codegraph_design` deprecation shim** for `decompose_and_persist_hlr`.

_Deliverable_: `DecomposeAgent.run()` produces identical results.

### Phase 4: Port FeedbackAgent

1. **Create `codegraph_agents/feedback/agent.py`**.
2. **Move from `codegraph_feedback/`**.
3. **Deprecation shim** for existing imports.

### Phase 5: Unify persistence

1. **Create `codegraph_agents/persistence.py`** — single `DesignPersistence`
   class that handles both decompose and design persistence.
2. **Merge `persist_decomposition()` and `_reconcile_design_with_scaffold()`**
   into one lifecycle-aware store.
3. **Remove `codegraph_requirements/persistence.py`**.

### Phase 6: Cut over

1. **Update MCP bridge** to use `codegraph_agents.DesignAgent` instead of
   `codegraph_design.agents.design_oo.design_and_persist_hlr`.
2. **Remove deprecation shims** from `codegraph_design/` and
   `codegraph_feedback/`.
3. **Archive old code** (git tag + move to `_legacy/`).

## 11. File-based logging with LangChain callbacks

### 11.1 Directory layout

Every agent run writes to a per-HLR directory under `log_dir`:

```
{log_dir}/
└── {hlr_uid[:8]}_{agent_name}/
    ├── agent.log.jsonl        # Structured JSON-line events (queryable)
    ├── conversation.md         # Human-readable turn-by-turn log (tail -f)
    ├── response.json           # Final result (same as current)
    ├── metrics.json            # Aggregate: tokens, latency, tool counts
    └── checkpoints/            # LangGraph checkpoints (for resume)
        ├── turn_000.json
        ├── turn_001.json
        └── ...
```

Concrete example:

```
codegraph/logs/
├── ee66877e_design_oo/
│   ├── agent.log.jsonl
│   ├── conversation.md
│   ├── response.json
│   ├── metrics.json
│   └── checkpoints/
│       ├── turn_000.json
│       ├── turn_001.json
│       └── ...
├── d3ab9921_decompose/
│   └── ...
└── f714aa03_feedback/
    └── ...
```

### 11.2 `FileLoggingCallback` — writes JSONL + Markdown simultaneously

```python
# codegraph_agents/callbacks.py

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("codegraph_agents")


class FileLoggingCallback(BaseCallbackHandler):
    """LangChain callback that writes structured logs to disk.

    Produces two files simultaneously:
    - ``agent.log.jsonl`` — JSON-line events for programmatic querying
      (can be loaded with ``jq``, imported to Elasticsearch, etc.)
    - ``conversation.md`` — human-readable markdown that can be
      ``tail -f``'d during a run (rewritten after every turn, same
      incremental approach as the current prompt_log_file).

    At agent completion, also writes:
    - ``response.json`` — the final structured result
    - ``metrics.json`` — aggregate token counts, latency, tool stats

    Usage:
        callback = FileLoggingCallback(
            log_dir="codegraph/logs",
            agent_name="design_oo",
            hlr_uid="ee66877e...",
        )
        config = {"callbacks": [callback]}
        agent.run(config)
    """

    def __init__(
        self,
        log_dir: str,
        agent_name: str,
        hlr_uid: str,
    ):
        self.agent_name = agent_name
        self.hlr_uid = hlr_uid

        # Build output directory
        short_uid = hlr_uid[:8] if len(hlr_uid) >= 8 else hlr_uid
        run_dir = Path(log_dir) / f"{short_uid}_{agent_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir = run_dir

        # File handles
        self._jsonl_path = run_dir / "agent.log.jsonl"
        self._md_path = run_dir / "conversation.md"
        self._jsonl_file = open(self._jsonl_path, "w")

        # Accumulators for the markdown file (rewritten after each event)
        self._md_lines: list[str] = []
        self._turn_count = 0
        self._run_start = time.time()

        # Metrics accumulators
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._tool_counts: dict[str, int] = {}
        self._tool_latencies: dict[str, list[float]] = {}
        self._tool_start_times: dict[str, float] = {}
        self._llm_latencies: list[float] = []

    # ── JSONL helpers ───────────────────────────────────────────────

    def _emit(self, event: str, **fields) -> None:
        """Write a JSON-line event.  Flush after every write so tail -f works."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "agent": self.agent_name,
            "hlr_uid": self.hlr_uid,
            **fields,
        }
        self._jsonl_file.write(json.dumps(record, default=str) + "\n")
        self._jsonl_file.flush()

    def _rewrite_markdown(self) -> None:
        """Rewrite conversation.md — same incremental approach as current."""
        self._md_path.write_text("\n".join(self._md_lines) + "\n", encoding="utf-8")

    # ── Lifecycle events ────────────────────────────────────────────

    def on_chain_start(self, serialized, inputs, **kwargs):
        self._run_start = time.time()
        self._emit("agent_start", phase="start")

        self._md_lines = [
            f"# {self.agent_name} Agent Run",
            f"**HLR**: `{self.hlr_uid}`",
            f"**Started**: {datetime.now(timezone.utc).isoformat()}",
            "",
            "---",
            "",
        ]
        self._rewrite_markdown()

    def on_chain_end(self, outputs, **kwargs):
        duration_ms = int((time.time() - self._run_start) * 1000)
        self._emit("agent_end", duration_ms=duration_ms)

        # Append summary footer to markdown
        self._md_lines.append("")
        self._md_lines.append("---")
        self._md_lines.append("")
        self._md_lines.append(f"**Completed** in {duration_ms/1000:.1f}s")
        self._md_lines.append(f"**Turns**: {self._turn_count}")
        self._md_lines.append(f"**Tokens**: {self._total_input_tokens} in / {self._total_output_tokens} out")
        self._rewrite_markdown()

        # Write metrics.json
        self._write_metrics(duration_ms)

        # Close JSONL
        self._jsonl_file.close()

    # ── LLM events ──────────────────────────────────────────────────

    def on_llm_start(self, serialized, prompts, **kwargs):
        invocation = kwargs.get("invocation_params", {})
        model = invocation.get("model", "")
        prompt_text = "\n".join(prompts[0]) if prompts else ""

        self._emit("llm_start", turn=self._turn_count, model=model)

    def on_llm_end(self, response, **kwargs):
        duration_ms = int(
            (time.time() - getattr(self, "_llm_start_time", time.time())) * 1000
        )
        self._llm_start_time = time.time()  # reset for next call

        usage = response.llm_output.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._llm_latencies.append(duration_ms)

        tool_calls = []
        message_text = ""
        for gen in response.generations:
            msg = gen[0].message if isinstance(gen, list) else gen.message
            message_text = getattr(msg, "content", "") or ""
            if hasattr(msg, "tool_calls"):
                tool_calls = [
                    {"name": tc["name"], "args": tc["args"]}
                    for tc in msg.tool_calls
                ]

        self._emit(
            "llm_end",
            turn=self._turn_count,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=[tc["name"] for tc in tool_calls],
        )

        # Markdown: assistant response
        if message_text:
            self._md_lines.append(f"### Assistant (turn {self._turn_count})")
            self._md_lines.append("")
            self._md_lines.append(message_text)
            self._md_lines.append("")

        for tc in tool_calls:
            self._md_lines.append(
                f"### Tool Call: `{tc['name']}` (turn {self._turn_count})"
            )
            self._md_lines.append("")
            self._md_lines.append("```json")
            self._md_lines.append(json.dumps(tc["args"], indent=2))
            self._md_lines.append("```")
            self._md_lines.append("")

        self._rewrite_markdown()

    # ── Tool events ─────────────────────────────────────────────────

    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times[run_id] = time.time()
        tool_name = serialized.get("name", "?")

        self._emit("tool_start", turn=self._turn_count, tool=tool_name)

    def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        start = self._tool_start_times.pop(run_id, time.time())
        duration_ms = int((time.time() - start) * 1000)
        tool_name = kwargs.get("name", "?")

        output_str = str(output)
        truncated = output_str[:5000]

        self._emit(
            "tool_end",
            turn=self._turn_count,
            tool=tool_name,
            duration_ms=duration_ms,
            output_len=len(output_str),
        )

        # Metrics tracking
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1
        self._tool_latencies.setdefault(tool_name, []).append(duration_ms)

        # Markdown: tool result
        self._md_lines.append(f"**Result** ({duration_ms}ms):")
        self._md_lines.append("")
        self._md_lines.append("```json")
        self._md_lines.append(truncated)
        if len(output_str) > 5000:
            self._md_lines.append(f"... ({len(output_str) - 5000} more chars)")
        self._md_lines.append("```")
        self._md_lines.append("")
        self._md_lines.append("---")
        self._md_lines.append("")

        self._rewrite_markdown()

        # Increment turn counter after tool execution
        self._turn_count += 1

    def on_tool_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times.pop(run_id, None)
        tool_name = kwargs.get("name", "?")
        error_str = str(error)[:2000]

        self._emit(
            "tool_error",
            turn=self._turn_count,
            tool=tool_name,
            error=error_str,
        )

        self._md_lines.append(f"**ERROR**: `{error_str}`")
        self._md_lines.append("")
        self._rewrite_markdown()

        self._turn_count += 1

    # ── Metrics ─────────────────────────────────────────────────────

    def _write_metrics(self, duration_ms: int) -> None:
        """Write aggregate metrics after agent completion."""
        # Compute tool latency stats
        tool_stats = {}
        for tool_name, latencies in self._tool_latencies.items():
            sorted_lats = sorted(latencies)
            tool_stats[tool_name] = {
                "count": len(latencies),
                "total_ms": sum(latencies),
                "avg_ms": sum(latencies) / len(latencies),
                "p50_ms": sorted_lats[len(sorted_lats) // 2],
                "p95_ms": sorted_lats[int(len(sorted_lats) * 0.95)],
                "max_ms": max(latencies),
            }

        sorted_llm_lats = sorted(self._llm_latencies)
        metrics = {
            "agent": self.agent_name,
            "hlr_uid": self.hlr_uid,
            "duration_ms": duration_ms,
            "turns": self._turn_count,
            "tokens": {
                "input": self._total_input_tokens,
                "output": self._total_output_tokens,
                "total": self._total_input_tokens + self._total_output_tokens,
            },
            "llm_calls": len(self._llm_latencies),
            "llm_latency": {
                "avg_ms": sum(self._llm_latencies) / len(self._llm_latencies) if self._llm_latencies else 0,
                "total_ms": sum(self._llm_latencies),
                "p50_ms": sorted_llm_lats[len(sorted_llm_lats) // 2] if sorted_llm_lats else 0,
                "p95_ms": sorted_llm_lats[int(len(sorted_llm_lats) * 0.95)] if sorted_llm_lats else 0,
            },
            "tools": tool_stats,
            "cost_estimate_usd": self._estimate_cost(),
        }

        metrics_path = self.run_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def _estimate_cost(self) -> float:
        """Rough cost estimate.  Update rates as models change."""
        # Claude Sonnet 4 pricing (approximate)
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = self._total_output_tokens * 15.0 / 1_000_000
        return round(input_cost + output_cost, 4)
```

### 11.3 JSONL format (`agent.log.jsonl`)

Each line is a self-contained JSON object.  Queryable with `jq` or
importable to any structured log backend.

```jsonl
{"ts":"2026-07-11T14:32:01.123Z","event":"agent_start","agent":"design_oo","hlr_uid":"ee66877e...","phase":"start"}
{"ts":"2026-07-11T14:32:01.456Z","event":"llm_start","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"model":"claude-sonnet-4-20250514"}
{"ts":"2026-07-11T14:32:04.789Z","event":"llm_end","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"duration_ms":3333,"input_tokens":4523,"output_tokens":287,"tool_calls":["search_symbols","import_compound"]}
{"ts":"2026-07-11T14:32:04.800Z","event":"tool_start","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"tool":"search_symbols"}
{"ts":"2026-07-11T14:32:04.862Z","event":"tool_end","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"tool":"search_symbols","duration_ms":62,"output_len":1234}
{"ts":"2026-07-11T14:32:04.870Z","event":"tool_start","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"tool":"import_compound"}
{"ts":"2026-07-11T14:32:05.912Z","event":"tool_end","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"tool":"import_compound","duration_ms":1042,"output_len":3456}
{"ts":"2026-07-11T14:32:05.920Z","event":"tool_error","agent":"design_oo","hlr_uid":"ee66877e...","turn":0,"tool":"import_compound","error":"ValueError: No compound found for 'not.a.real.Class'"}
...
{"ts":"2026-07-11T14:35:22.451Z","event":"agent_end","agent":"design_oo","hlr_uid":"ee66877e...","duration_ms":201328}
```

Query examples with `jq`:

```bash
# All tool calls that took > 1 second
jq 'select(.event=="tool_end" and .duration_ms > 1000)' agent.log.jsonl

# Token usage per turn
jq 'select(.event=="llm_end") | {turn, input_tokens, output_tokens}' agent.log.jsonl

# Tool call frequency
jq 'select(.event=="tool_end") | .tool' agent.log.jsonl | sort | uniq -c | sort -rn

# Errors only
jq 'select(.event=="tool_error")' agent.log.jsonl

# Reconstruct the full timeline
jq -r '[.ts, .event, .turn // "", .tool // "", .duration_ms // ""] | @tsv' agent.log.jsonl
```

### 11.4 Markdown format (`conversation.md`)

Human-readable, rewritten after every event (same `tail -f` experience
as the current `prompt_log_file`).  Every tool call and result gets its
own section with timing.

```markdown
# design_oo Agent Run
**HLR**: `ee66877e...`
**Started**: 2026-07-11T14:32:01.123Z

---

### Assistant (turn 0)

The first step is to discover relevant as-built classes. I'll search
for existing graph and export infrastructure.

### Tool Call: `search_symbols` (turn 0)

```json
{
  "query": "LayerGraph"
}
```

**Result** (62ms):

```json
{
  "results": [
    {"qualified_name": "codegraph.graph.LayerGraph", "kind": "class"},
    {"qualified_name": "codegraph.graph.layer_graph.LayerGraph", "kind": "class"}
  ]
}
```

---

### Tool Call: `import_compound` (turn 0)

```json
{
  "qualified_name": "codegraph.graph.LayerGraph"
}
```

**Result** (1042ms):

```json
{
  "imported": true,
  "nodes_imported": 12,
  "context_graph_size": 12,
  "imported_nodes": [
    {"qualified_name": "codegraph.graph.LayerGraph", "kind": "class"},
    ...
  ]
}
```

---

### Assistant (turn 1)

Now I have the as-built context loaded. Let me design the architecture
classes.

### Tool Call: `validate_design` (turn 1)

```json
{
  "nodes": [
    {"type": "ClassNode", "qualified_name": "archgen::DiagramGenerator", ...},
    ...
  ]
}
```

**Result** (45ms):

```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Class 'DiagramGenerator' has no methods"]
}
```

---

... (continues for all turns) ...

---

**Completed** in 201.3s
**Turns**: 42
**Tokens**: 189456 in / 8734 out
```

### 11.5 Response file (`response.json`)

Same as the current `_response.json` — the final parsed tool output.
For `commit_design_and_verifications`, this is the full design nodes
+ verification procedures.

```json
{
  "design": [
    {
      "type": "ClassNode",
      "kind": "class",
      "name": "DiagramGenerator",
      "qualified_name": "archgen::DiagramGenerator",
      ...
    }
  ],
  "verifications": {
    "abc123": [...]
  }
}
```

### 11.6 Metrics file (`metrics.json`)

Aggregate stats written at agent completion.  Useful for cost tracking,
performance regression detection, and comparing runs.

```json
{
  "agent": "design_oo",
  "hlr_uid": "ee66877ef1b04ad6",
  "duration_ms": 201328,
  "turns": 42,
  "tokens": {
    "input": 189456,
    "output": 8734,
    "total": 198190
  },
  "llm_calls": 21,
  "llm_latency": {
    "avg_ms": 9500,
    "total_ms": 199500,
    "p50_ms": 8200,
    "p95_ms": 18100
  },
  "tools": {
    "search_symbols": {
      "count": 4,
      "total_ms": 245,
      "avg_ms": 61.25,
      "p50_ms": 58,
      "p95_ms": 72,
      "max_ms": 78
    },
    "import_compound": {
      "count": 6,
      "total_ms": 6540,
      "avg_ms": 1090,
      "p50_ms": 1050,
      "p95_ms": 1380,
      "max_ms": 1423
    },
    "validate_design": {
      "count": 8,
      "total_ms": 360,
      "avg_ms": 45,
      "p50_ms": 42,
      "p95_ms": 68,
      "max_ms": 72
    },
    "produce_oo_design": {
      "count": 2,
      "total_ms": 180,
      "avg_ms": 90,
      "p50_ms": 90,
      "p95_ms": 95,
      "max_ms": 95
    },
    "draft_verifications": {
      "count": 3,
      "total_ms": 450,
      "avg_ms": 150,
      "p50_ms": 145,
      "p95_ms": 170,
      "max_ms": 175
    },
    "check_design_smells": {
      "count": 2,
      "total_ms": 120,
      "avg_ms": 60,
      "p50_ms": 60,
      "p95_ms": 65,
      "max_ms": 65
    },
    "commit_design_and_verifications": {
      "count": 1,
      "total_ms": 85,
      "avg_ms": 85,
      "p50_ms": 85,
      "p95_ms": 85,
      "max_ms": 85
    }
  },
  "cost_estimate_usd": 0.6994
}
```

### 11.7 Integration with `BaseAgent.run()`

```python
# codegraph_agents/base.py (additions)

def run(self) -> Any:
    self._context = self.load_context()
    initial_messages = self.build_initial_messages(self._context)

    initial_state: AgentState = {
        "messages": initial_messages,
        "agent_name": self.name,
        "hlr_uid": self.config.hlr_uid,
        "phase": "start",
        "turn_count": 0,
        "error_count": 0,
    }

    # Build callback chain: structured logging + file logging
    callbacks: list[BaseCallbackHandler] = [
        AgentCallback(self.name),  # structured log events (logging.info)
    ]
    if self.config.log_dir:
        callbacks.append(FileLoggingCallback(
            log_dir=self.config.log_dir,
            agent_name=self.name,
            hlr_uid=self.config.hlr_uid,
        ))

    run_config: RunnableConfig = {
        "configurable": {
            "thread_id": self.config.hlr_uid or "default",
            "dispatcher": self.dispatcher,
            "context": self._context,
        },
        "callbacks": callbacks,
    }

    final_state = self._graph.invoke(initial_state, run_config)
    result = self.build_result(final_state)

    # Write response.json (same format as current)
    if self.config.log_dir:
        self._write_response(result)

    return result
```

### 11.8 Comparison: current vs proposed

| Aspect | Current (`prompt_log_file`) | Proposed (`FileLoggingCallback`) |
|--------|----------------------------|-----------------------------------|
| **Files per run** | 3 (`_response.json`, `.md`, `_raw.txt`) | 4 (`response.json`, `conversation.md`, `agent.log.jsonl`, `metrics.json`) |
| **Markdown format** | Flat dump of system prompt + all messages/tools/results | Sectioned by turn, with timing per tool call |
| **Structured querying** | None — grep the markdown | Full: `jq` queries on JSONL, metrics.json for aggregates |
| **`tail -f` support** | Yes (rewritten after every turn) | Yes (same incremental rewrite) |
| **Token tracking** | Implicit (count lines) | Explicit per-turn (`input_tokens`, `output_tokens`) in both JSONL and metrics |
| **Tool latency** | Not tracked | Per-call in JSONL, aggregates (p50/p95/avg) in metrics |
| **Cost estimate** | Manual calculation | Automatic in `metrics.json` (rates configurable) |
| **Error tracking** | Mixed into markdown | Separate JSONL events, error count in metrics |
| **Per-run comparison** | Diff two markdown files | Diff two `metrics.json` files |
| **Retry/resume logging** | Overwrites previous log | New directory per run (deduplicated by timestamp) |

## 12. Implementation status (Phase 1 complete)

### What's built

```
src/codegraph_agents/
├── __init__.py            # Public API: BaseAgent, AgentConfig, AgentState, etc.
├── config.py              # AgentConfig dataclass (run_id auto-generated UUID)
├── state.py               # AgentState TypedDict (agent-agnostic, no hlr_uid)
├── callbacks.py           # AgentCallback + FileLoggingCallback
├── base.py                # BaseAgent with OpenAI backend, LangGraph + checkpointing
│
├── context/               # Declarative context loading
│   ├── __init__.py        # ContextProvider class
│   └── builtins.py        # 4 resolvers: hlr_subtree, component_namespace,
│                          #   prior_design_compounds, sibling_namespaces
│
├── design/
│   ├── __init__.py        # Exports DesignAgent, DesignResult
│   └── agent.py           # Skeleton (Phase 2)
│
├── decompose/__init__.py  # Placeholder (Phase 3)
└── feedback/__init__.py   # Placeholder (Phase 4)
```

### Key decisions made

1. **OpenAI-only backend**. Direct OpenAI SDK call (~60 lines), no
   Anthropic, no `langchain-openai`, no `ChatOpenAI`. Model config reads
   `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY` from env.

2. **Single model call per `think` node**. LangGraph owns the tool loop.
   One Anthropic→OpenAI API call per graph step → checkpoint granularity
   at every turn.

3. **`LayerGraph` stays in `config["configurable"]`**. Not serialized in
   state, avoiding checkpoint overhead.

4. **`run_id` vs `hlr_uid` split**. `run_id` is auto-generated UUID for
   logging/checkpointing (every agent has one). `hlr_uid` is optional and
   used only by HLR-specific context resolvers. AgentState has no HLR-
   specific fields.

5. **`hlr_uid` removed from AgentState**. State is agent-agnostic:
   `messages`, `agent_name`, `phase`, `turn_count`, `error_count`,
   `last_tool`, `last_tool_success`.

### What diverged from the original plan

- **Backends module removed**. Original plan had `codegraph_agents/backends/`
  with Anthropic + OpenAI + factory. Instead, OpenAI calling is inline in
  `base.py` (~4 methods, ~120 lines). Simpler, and Anthropic wasn't needed.
- **`llm-caller` not used**. The plan said "keep llm-caller for model calls."
  In practice, llm-caller's API (extract tool input dict) doesn't match what
  LangGraph needs (full response with content + tool_calls + IDs). Direct
  OpenAI SDK is actually thinner.

### Test coverage (67 tests)

| Area | Tests |
|------|-------|
| Graph construction, routing (6 scenarios), tools node | 11 |
| OpenAI response parsing (text, tool_calls, mixed, malformed, empty) | 5 |
| OpenAI message conversion (system/user/AI/tool/mixed) | 6 |
| OpenAI tool schema conversion | 3 |
| Response extraction, config defaults, state fields | 4 |
| FileLoggingCallback (JSONL, markdown, metrics, errors) | 11 |
| ContextProvider registration/errors | 8 |
| Context resolvers (hlr_subtree, component_namespace, prior_design, siblings) | 19 |

### Open questions

1. **LayerGraph serialization overhead**: If we checkpoint the LayerGraph
   after every turn, serialization adds 50-200ms/turn. For a 75-turn run,
   that's 4-15 seconds. Acceptable? Alternative: keep LayerGraph in
   `config["configurable"]` (not serialized), only checkpoint messages +
   phase metadata. **Decision: keep in configurable — not serialized.**

2. **Interrupt points for human review**: After design phase, should the
   agent pause and wait for human approval? Would use
   `graph.interrupt_before=["verify_phase"]`. **Not yet decided.**

3. **Phase 2 (DesignAgent port)**: Move `codegraph_design/tools/` →
   `codegraph_agents/design/tools.py`. Wire up `DesignAgent` with real
   tools, prompts, smells, and verification resolution. Deprecation shim
   in `codegraph_design/`.
