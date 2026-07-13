"""LangChain-compatible callback handlers for agent observability.

Two handlers are provided:

:class:`AgentCallback`
    Emits structured JSON-line events via Python's ``logging`` module.
    Every LLM start/end, tool start/end/error, and agent lifecycle
    event is logged with the ``codegraph_agents`` logger at INFO
    level.  These events can be routed to any logging backend
    (file, Elasticsearch, Datadog, etc.) via standard logging config.

:class:`FileLoggingCallback`
    Writes three files to a per-run directory under *log_dir*:

    * ``agent.log.jsonl`` — JSON-line events for programmatic
      querying (``jq``, Elasticsearch import, etc.)
    * ``conversation.md`` — human-readable turn-by-turn log,
      rewritten incrementally (``tail -f`` friendly)
    * ``metrics.json`` — aggregate token counts, tool latency
      stats, and cost estimate, written at agent completion

    The ``response.json`` file is written separately by
    :meth:`BaseAgent._write_response`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("codegraph_agents")


class AgentCallback(BaseCallbackHandler):
    """Emit structured lifecycle events via ``logging.info()``.

    Every event carries ``extra`` fields suitable for structured
    logging backends (e.g. ``python-json-logger``).  The ``extra``
    dict includes:

    * ``event`` — event type name (``"agent_start"``,
      ``"llm_start"``, ``"tool_end"``, etc.)
    * ``agent`` — agent name
    * ``turn`` — current turn number (for LLM/tool events)
    * ``tool`` — tool name (for tool events)
    * ``duration_ms`` — latency in milliseconds (for end events)
    * ``input_tokens`` / ``output_tokens`` — token counts
      (for LLM end events)

    Usage::

        from langchain_core.runnables import RunnableConfig

        config: RunnableConfig = {
            "callbacks": [AgentCallback("design_oo")],
        }
        graph.invoke(state, config)
    """

    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name
        self._tool_start_times: dict[str, float] = {}
        self._llm_start_time: float = 0.0
        self._turn_count = 0
        self._started = False
        self._ended = False

    # ── Lifecycle ──────────────────────────────────────────────

    def on_chain_start(
        self, serialized: dict, inputs: dict, **kwargs
    ) -> None:
        if self._started:
            return
        self._started = True
        log.info(
            "agent_start",
            extra={
                "event": "agent_start",
                "agent": self.agent_name,
                "phase": "start",
            },
        )

    def on_chain_end(self, outputs: dict, **kwargs) -> None:
        if self._ended:
            return
        self._ended = True
        log.info(
            "agent_end",
            extra={
                "event": "agent_end",
                "agent": self.agent_name,
            },
        )

    # ── LLM events ─────────────────────────────────────────────

    def on_llm_start(
        self, serialized: dict, prompts: list, **kwargs
    ) -> None:
        self._llm_start_time = time.time()
        invocation = kwargs.get("invocation_params", {})
        log.info(
            "llm_start",
            extra={
                "event": "llm_start",
                "agent": self.agent_name,
                "turn": self._turn_count,
                "model": invocation.get("model", ""),
                "prompt_len": (
                    sum(len(p) for p in prompts[0])
                    if prompts
                    else 0
                ),
            },
        )

    def on_llm_end(self, response, **kwargs) -> None:
        duration_ms = int(
            (time.time() - self._llm_start_time) * 1000
        )
        usage = response.llm_output.get("usage", {}) if response.llm_output else {}
        tool_calls = []
        for gen in response.generations:
            msg = (
                gen[0].message
                if isinstance(gen, list)
                else gen.message
            )
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = [tc["name"] for tc in msg.tool_calls]

        log.info(
            "llm_end",
            extra={
                "event": "llm_end",
                "agent": self.agent_name,
                "turn": self._turn_count,
                "duration_ms": duration_ms,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "tool_calls": tool_calls,
            },
        )

    # ── Tool events ────────────────────────────────────────────

    def on_tool_start(
        self, serialized: dict, input_str: str, **kwargs
    ) -> None:
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times[run_id] = time.time()
        log.info(
            "tool_start",
            extra={
                "event": "tool_start",
                "agent": self.agent_name,
                "turn": self._turn_count,
                "tool": serialized.get("name", "?"),
                "input": str(input_str)[:500],
            },
        )

    def on_tool_end(self, output, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        start = self._tool_start_times.pop(run_id, time.time())
        duration_ms = int((time.time() - start) * 1000)
        tool_name = kwargs.get("name", "?")

        log.info(
            "tool_end",
            extra={
                "event": "tool_end",
                "agent": self.agent_name,
                "turn": self._turn_count,
                "tool": tool_name,
                "duration_ms": duration_ms,
            },
        )
        self._turn_count += 1

    def on_tool_error(self, error, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        self._tool_start_times.pop(run_id, None)
        tool_name = kwargs.get("name", "?")
        log.error(
            "tool_error",
            extra={
                "event": "tool_error",
                "agent": self.agent_name,
                "turn": self._turn_count,
                "tool": tool_name,
                "error": str(error)[:500],
            },
        )
        self._turn_count += 1


class FileLoggingCallback(BaseCallbackHandler):
    """Write structured logs to disk alongside agent execution.

    Produces three files in a per-run directory under *log_dir*:

    * ``agent.log.jsonl`` — JSON-line events, queryable with ``jq``
    * ``conversation.md`` — human-readable turn-by-turn log,
      rewritten incrementally (same ``tail -f`` experience as the
      current ``prompt_log_file``)
    * ``metrics.json`` — aggregate token counts, p50/p95 tool
      latency, and cost estimate, written at agent completion

    The directory is named ``{run_id[:8]}_{agent_name}`` to avoid
    collisions between agents and retries.

    Usage::

        callback = FileLoggingCallback(
            log_dir="codegraph/logs",
            agent_name="design_oo",
            run_id="ee66877ef1b04ad6",
        )
        config: RunnableConfig = {"callbacks": [callback]}
        graph.invoke(state, config)
    """

    # ── Per-turn truncation limits ─────────────────────────────

    _TOOL_OUTPUT_MAX_CHARS = 8000

    def __init__(
        self,
        log_dir: str,
        agent_name: str,
        run_id: str,
    ) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.run_id = run_id

        # Build output directory
        short_id = run_id[:8] if len(run_id) >= 8 else run_id
        run_dir = Path(log_dir) / f"{short_id}_{agent_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir = run_dir

        # File handles (opened lazily in on_chain_start, closed once in finalize)
        self._jsonl_path = run_dir / "agent.log.jsonl"
        self._md_path = run_dir / "conversation.md"
        self._jsonl_file: object = None

        # Accumulators
        self._md_lines: list[str] = []
        self._turn_count = 0
        self._run_start = time.time()
        self._started = False
        self._finalized = False

        # Metrics accumulators
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._tool_counts: dict[str, int] = {}
        self._tool_latencies: dict[str, list[float]] = {}
        self._tool_start_times: dict[str, float] = {}
        self._llm_latencies: list[float] = []
        self._llm_start_time: float = 0.0

    # ── JSONL helpers ────────────────────────────────────────

    def _ensure_jsonl_open(self) -> object:
        """Lazy-open the JSONL file handle; idempotent."""
        if self._jsonl_file is None:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            self._jsonl_file = open(self._jsonl_path, "w")
        return self._jsonl_file

    def _emit(self, event: str, **fields: object) -> None:
        """Write a single JSON-line event.  Flushes immediately."""
        record: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "agent": self.agent_name,
            "run_id": self.run_id,
            **fields,
        }
        fh = self._ensure_jsonl_open()
        fh.write(json.dumps(record, default=str) + "\n")
        fh.flush()

    def _rewrite_markdown(self) -> None:
        """Rewrite conversation.md entirely — same incremental
        approach as the current prompt_log_file."""
        self._md_path.parent.mkdir(parents=True, exist_ok=True)
        self._md_path.write_text(
            "\n".join(self._md_lines) + "\n", encoding="utf-8"
        )

    # ── Lifecycle ────────────────────────────────────────────

    def on_chain_start(
        self, serialized: dict, inputs: dict, **kwargs
    ) -> None:
        # Only start logging on the first chain event —
        # LangGraph fires on_chain_start for sub-nodes too.
        if self._started:
            return
        self._started = True

        self._run_start = time.time()
        self._emit("agent_start", phase="start")

        self._md_lines = [
            f"# {self.agent_name} Agent Run",
            f"**Run**: `{self.run_id}`",
            f"**Started**: {datetime.now(timezone.utc).isoformat()}",
            "",
            "---",
            "",
        ]
        self._rewrite_markdown()

    def on_chain_end(self, outputs: dict, **kwargs) -> None:
        # LangGraph fires on_chain_end early (after first super-step),
        # before the full multi-turn loop completes.  Do NOT finalize
        # here — BaseAgent.run() calls finalize() after graph.invoke
        # returns with the full accumulated state.
        pass

    def finalize(self) -> None:
        """Write the summary footer and metrics after the full run.

        Called by ``BaseAgent.run()`` / ``resume()`` after
        ``graph.invoke()`` returns.  Idempotent — safe to call
        even if ``on_chain_end`` already finalized.
        """
        if self._finalized:
            return
        self._finalized = True
        self._flush_footer_and_metrics()

    def _flush_footer_and_metrics(self) -> None:
        """Write the markdown footer and metrics.json."""
        duration_ms = int((time.time() - self._run_start) * 1000)

        # Re-emit agent_end with correct duration
        self._emit("agent_end", duration_ms=duration_ms)

        # Append summary footer to markdown
        self._md_lines.append("")
        self._md_lines.append("---")
        self._md_lines.append("")
        self._md_lines.append(
            f"**Completed** in {duration_ms / 1000:.1f}s"
        )
        self._md_lines.append(f"**Turns**: {self._turn_count}")
        self._md_lines.append(
            f"**Tokens**: {self._total_input_tokens} in / "
            f"{self._total_output_tokens} out"
        )
        self._rewrite_markdown()

        # Write metrics.json
        self._write_metrics(duration_ms)

        # Close JSONL file once everything is written
        if self._jsonl_file is not None:
            self._jsonl_file.close()
            self._jsonl_file = None

    # ── Public logging API (called explicitly by agent nodes) ─

    def log_llm_start(self, *, model: str = "") -> None:
        """Called by agent before each model call.

        Records the JSONL event and begins a new turn in the
        markdown log.
        """
        self._llm_start_time = time.time()
        self._emit(
            "llm_start", turn=self._turn_count, model=model
        )

        # Markdown: turn header
        self._md_lines.append(
            f"## Turn {self._turn_count}"
        )
        self._md_lines.append("")
        self._md_lines.append(f"**Model**: `{model}`")
        self._md_lines.append("")
        self._rewrite_markdown()

    def log_llm_end(
        self,
        *,
        content: str = "",
        tool_calls: list[dict[str, object]] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int | None = None,
    ) -> None:
        """Called by agent after each model call."""
        if duration_ms is None:
            duration_ms = int(
                (time.time() - self._llm_start_time) * 1000
            )
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._llm_latencies.append(duration_ms)

        resolved_tool_calls = tool_calls or []
        self._emit(
            "llm_end",
            turn=self._turn_count,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=[tc["name"] for tc in resolved_tool_calls],
        )

        # Markdown: assistant text
        if content:
            self._md_lines.append(
                f"### Assistant (turn {self._turn_count})"
            )
            self._md_lines.append("")
            self._md_lines.append(content[:5000])
            if len(content) > 5000:
                self._md_lines.append(
                    f"\n... ({len(content) - 5000} more chars)"
                )
            self._md_lines.append("")

        # Markdown: tool call details
        for tc in resolved_tool_calls:
            self._md_lines.append(
                f"### Tool Call: `{tc['name']}`"
                f" (turn {self._turn_count})"
            )
            self._md_lines.append("")
            self._md_lines.append("```json")
            self._md_lines.append(
                json.dumps(
                    tc["args"], indent=2, default=str
                )[:5000]
            )
            self._md_lines.append("```")
            self._md_lines.append("")

        self._rewrite_markdown()

    # ── LLM events (LangChain callback interface — unused) ────

    def on_llm_start(
        self, serialized: dict, prompts: list, **kwargs
    ) -> None:
        pass  # handled via log_llm_start

    def on_llm_end(self, response, **kwargs) -> None:
        pass  # handled via log_llm_end

    # ── Public tool-logging API (called explicitly by agent) ──

    def log_tool_start(self, *, tool_name: str) -> str:
        """Called by agent before each tool dispatch.

        Returns a key that must be passed to ``log_tool_end``.
        """
        import uuid
        key = str(uuid.uuid4())
        self._tool_start_times[key] = time.time()
        self._emit(
            "tool_start",
            turn=self._turn_count,
            tool=tool_name,
        )
        return key

    def log_tool_end(
        self, *, tool_name: str, output: str,
        duration_ms: int | None = None, tool_key: str = "",
    ) -> None:
        """Called by agent after each tool dispatch."""
        start = self._tool_start_times.pop(tool_key, time.time())
        if duration_ms is None:
            duration_ms = int((time.time() - start) * 1000)

        output_str = str(output)
        truncated = (
            output_str[: self._TOOL_OUTPUT_MAX_CHARS]
            if len(output_str) > self._TOOL_OUTPUT_MAX_CHARS
            else output_str
        )

        self._emit(
            "tool_end",
            turn=self._turn_count,
            tool=tool_name,
            duration_ms=duration_ms,
            output_len=len(output_str),
        )

        # Metrics tracking
        self._tool_counts[tool_name] = (
            self._tool_counts.get(tool_name, 0) + 1
        )
        self._tool_latencies.setdefault(tool_name, []).append(
            float(duration_ms)
        )

        # Markdown: tool result
        self._md_lines.append(
            f"**Result** ({duration_ms}ms):"
        )
        self._md_lines.append("")
        self._md_lines.append("```json")
        self._md_lines.append(truncated)
        if len(output_str) > self._TOOL_OUTPUT_MAX_CHARS:
            self._md_lines.append(
                f"\n... ({len(output_str) - self._TOOL_OUTPUT_MAX_CHARS}"
                " more chars)"
            )
        self._md_lines.append("```")
        self._md_lines.append("")
        self._md_lines.append("---")
        self._md_lines.append("")

        self._rewrite_markdown()

        # Increment turn counter after tool execution
        self._turn_count += 1

    def log_tool_error(
        self, *, tool_name: str, error: str, tool_key: str = "",
    ) -> None:
        """Called by agent when a tool dispatch fails."""
        self._tool_start_times.pop(tool_key, None)
        error_str = str(error)[:2000]

        self._emit(
            "tool_error",
            turn=self._turn_count,
            tool=tool_name,
            error=error_str,
        )

        self._md_lines.append(
            f"**ERROR**: `{error_str}`"
        )
        self._md_lines.append("")
        self._rewrite_markdown()

        self._turn_count += 1

    # ── Tool events (LangChain callback interface — unused) ───

    def on_tool_start(
        self, serialized: dict, input_str: str, **kwargs
    ) -> None:
        pass  # handled via log_tool_start

    def on_tool_end(self, output, **kwargs) -> None:
        pass  # handled via log_tool_end

    def on_tool_error(self, error, **kwargs) -> None:
        pass  # handled via log_tool_error

    # ── Metrics ──────────────────────────────────────────────

    def _write_metrics(self, duration_ms: int) -> None:
        """Write aggregate metrics after agent completion."""
        tool_stats: dict[str, dict[str, object]] = {}
        for tname, latencies in self._tool_latencies.items():
            if not latencies:
                continue
            sorted_lats = sorted(latencies)
            n = len(sorted_lats)
            tool_stats[tname] = {
                "count": n,
                "total_ms": sum(sorted_lats),
                "avg_ms": round(sum(sorted_lats) / n, 1),
                "p50_ms": sorted_lats[n // 2],
                "p95_ms": sorted_lats[
                    int(n * 0.95)
                ],
                "max_ms": max(sorted_lats),
            }

        sorted_llm = sorted(self._llm_latencies)
        llm_n = len(sorted_llm)

        metrics: dict[str, object] = {
            "agent": self.agent_name,
            "run_id": self.run_id,
            "duration_ms": duration_ms,
            "turns": self._turn_count,
            "tokens": {
                "input": self._total_input_tokens,
                "output": self._total_output_tokens,
                "total": (
                    self._total_input_tokens
                    + self._total_output_tokens
                ),
            },
            "llm_calls": llm_n,
            "llm_latency": {
                "avg_ms": round(
                    sum(sorted_llm) / llm_n, 1
                )
                if llm_n
                else 0,
                "total_ms": sum(sorted_llm),
                "p50_ms": sorted_llm[llm_n // 2] if llm_n else 0,
                "p95_ms": sorted_llm[
                    int(llm_n * 0.95)
                ]
                if llm_n
                else 0,
            },
            "tools": tool_stats,
            "cost_estimate_usd": self._estimate_cost(),
        }

        metrics_path = self.run_dir / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )

    def _estimate_cost(self) -> float:
        """Rough cost estimate based on token counts.

        Uses approximate Anthropic Claude Sonnet pricing.
        Update rates here as models change.
        """
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = (
            self._total_output_tokens * 15.0 / 1_000_000
        )
        return round(input_cost + output_cost, 4)
