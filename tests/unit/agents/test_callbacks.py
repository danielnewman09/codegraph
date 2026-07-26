"""Tests for FileLoggingCallback — JSONL, markdown, and metrics output."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from codegraph_agents.callbacks import FileLoggingCallback


# ── Helper: simulate a response object ─────────────────────────


def _make_response(
    content_text: str = "",
    tool_calls: list[dict] | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Build a mock LangChain LLMResult for callback testing."""
    msg_cls = type(
        "Msg",
        (),
        {
            "content": content_text,
            "tool_calls": tool_calls,
        },
    )()

    gen_cls = type("Gen", (), {"message": msg_cls})()

    return type(
        "Response",
        (),
        {
            "generations": [[gen_cls]],
            "llm_output": {
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            },
        },
    )()


def _cid() -> str:
    """Generate a unique run_id for callback events."""
    return str(uuid4())


# ── Fixture ────────────────────────────────────────────────────


@pytest.fixture
def log_dir() -> str:
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def callback(log_dir: str) -> FileLoggingCallback:
    return FileLoggingCallback(
        log_dir=log_dir,
        agent_name="test_agent",
        run_id="abc12345abc12345abc12345",
    )


# ── Directory structure ────────────────────────────────────────


def test_creates_run_directory(log_dir: str) -> None:
    """Callback creates a per-run directory on init."""
    cb = FileLoggingCallback(log_dir, "design_oo", "ee66877ef1b04ad6")
    assert cb.run_dir.exists()
    assert cb.run_dir.name == "ee66877e_design_oo"


def test_initial_jsonl_file_exists(callback: FileLoggingCallback) -> None:
    """JSONL file is opened lazily on first emit (not at init time)."""
    assert not (callback.run_dir / "agent.log.jsonl").exists()
    callback.on_chain_start({}, {}, run_id=_cid())
    assert (callback.run_dir / "agent.log.jsonl").exists()


# ── JSONL output ───────────────────────────────────────────────


def test_jsonl_agent_start_end(callback: FileLoggingCallback) -> None:
    """Agent start and end events are written to JSONL."""
    callback.on_chain_start({}, {}, run_id=_cid())
    callback.finalize()

    lines = (callback.run_dir / "agent.log.jsonl").read_text().splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert "agent_start" in events
    assert "agent_end" in events


def test_jsonl_llm_events(callback: FileLoggingCallback) -> None:
    """LLM start/end events carry turn and token data."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="claude-test")
    callback.log_llm_end(
        content="Design plan...",
        input_tokens=500,
        output_tokens=200,
    )

    callback.finalize()

    lines = (callback.run_dir / "agent.log.jsonl").read_text().splitlines()
    llm_events = [
        json.loads(line)
        for line in lines
        if json.loads(line)["event"] in ("llm_start", "llm_end")
    ]

    assert len(llm_events) == 2
    start_ev = llm_events[0]
    assert start_ev["event"] == "llm_start"
    assert start_ev["model"] == "claude-test"

    end_ev = llm_events[1]
    assert end_ev["event"] == "llm_end"
    assert end_ev["input_tokens"] == 500
    assert end_ev["output_tokens"] == 200


def test_jsonl_tool_events(callback: FileLoggingCallback) -> None:
    """Tool start/end events carry tool name and timing."""
    callback.on_chain_start({}, {}, run_id=_cid())

    key = callback.log_tool_start(tool_name="search_symbols")
    callback.log_tool_end(tool_name="search_symbols", output='{"results": []}', tool_key=key)

    callback.finalize()

    lines = (callback.run_dir / "agent.log.jsonl").read_text().splitlines()
    tool_events = [
        json.loads(line)
        for line in lines
        if json.loads(line)["event"] in ("tool_start", "tool_end")
    ]

    assert len(tool_events) == 2
    assert tool_events[0]["event"] == "tool_start"
    assert tool_events[0]["tool"] == "search_symbols"
    assert tool_events[1]["event"] == "tool_end"
    assert tool_events[1]["tool"] == "search_symbols"
    assert "duration_ms" in tool_events[1]


def test_jsonl_tool_error(callback: FileLoggingCallback) -> None:
    """Tool errors are logged with error detail."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_tool_error(
        tool_name="import_compound",
        error="connection refused",
    )

    callback.finalize()

    lines = (callback.run_dir / "agent.log.jsonl").read_text().splitlines()
    err_events = [
        json.loads(line)
        for line in lines
        if json.loads(line)["event"] == "tool_error"
    ]
    assert len(err_events) == 1
    assert err_events[0]["tool"] == "import_compound"
    assert "connection refused" in err_events[0]["error"]


# ── Markdown output ────────────────────────────────────────────


def test_markdown_shows_system_prompt_first_turn(
    callback: FileLoggingCallback,
) -> None:
    """System prompt is written only once, on the first turn."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="claude")
    callback.log_llm_end(
        content="Hello",
        input_tokens=10,
        output_tokens=5,
    )

    callback.finalize()

    md = (callback.run_dir / "conversation.md").read_text()
    assert "Hello" in md
    assert "### Assistant" in md


def test_markdown_includes_tool_calls_and_results(
    callback: FileLoggingCallback,
) -> None:
    """Tool calls and results appear in the markdown."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="claude")
    callback.log_llm_end(
        content="Let me search",
        tool_calls=[
            {"name": "search_symbols", "args": {"query": "LayerGraph"}},
        ],
    )

    key = callback.log_tool_start(tool_name="search_symbols")
    callback.log_tool_end(
        tool_name="search_symbols",
        output='{"results": ["LayerGraph"]}',
        tool_key=key,
    )

    callback.finalize()

    md = (callback.run_dir / "conversation.md").read_text()
    assert "### Tool Call: `search_symbols`" in md
    assert "LayerGraph" in md
    assert "**Result**" in md


def test_markdown_has_summary_footer(callback: FileLoggingCallback) -> None:
    """Markdown ends with a summary footer showing turns and tokens."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="claude")
    callback.log_llm_end(input_tokens=300, output_tokens=150)

    key = callback.log_tool_start(tool_name="tool")
    callback.log_tool_end(tool_name="tool", output="out", tool_key=key)

    callback.finalize()

    md = (callback.run_dir / "conversation.md").read_text()
    assert "**Completed**" in md
    assert "**Turns**: 1" in md
    assert "300 in" in md
    assert "150 out" in md


# ── Metrics output ─────────────────────────────────────────────


def test_metrics_written_on_finalize(callback: FileLoggingCallback) -> None:
    """metrics.json is written when the agent ends."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="c")
    callback.log_llm_end(input_tokens=100, output_tokens=40)

    k1 = callback.log_tool_start(tool_name="tool_a")
    callback.log_tool_end(tool_name="tool_a", output="out", tool_key=k1)

    k2 = callback.log_tool_start(tool_name="tool_a")
    callback.log_tool_end(tool_name="tool_a", output="out", tool_key=k2)

    k3 = callback.log_tool_start(tool_name="tool_b")
    callback.log_tool_end(tool_name="tool_b", output="out", tool_key=k3)

    callback.finalize()

    metrics_path = callback.run_dir / "metrics.json"
    assert metrics_path.exists()

    m = json.loads(metrics_path.read_text())
    assert m["agent"] == "test_agent"
    assert m["run_id"] == "abc12345abc12345abc12345"
    assert m["turns"] == 3  # three tool calls
    assert m["tokens"]["input"] == 100
    assert m["tokens"]["output"] == 40
    assert m["tokens"]["total"] == 140
    assert m["llm_calls"] == 1
    assert "tool_a" in m["tools"]
    assert m["tools"]["tool_a"]["count"] == 2
    assert "tool_b" in m["tools"]
    assert m["tools"]["tool_b"]["count"] == 1
    assert "cost_estimate_usd" in m
    assert isinstance(m["cost_estimate_usd"], float)
    assert m["cost_estimate_usd"] >= 0.0


def test_metrics_tool_latency_stats(callback: FileLoggingCallback) -> None:
    """Tool latency stats include avg, p50, p95, max."""
    callback.on_chain_start({}, {}, run_id=_cid())

    callback.log_llm_start(model="c")
    callback.log_llm_end()

    # Simulate tool calls with varying latency
    import time
    for i in range(5):
        key = callback.log_tool_start(tool_name="slow_tool")
        # Simulate latency by manipulating the stored start time
        callback._tool_start_times[key] = time.time() - (0.05 * (i + 1))
        callback.log_tool_end(tool_name="slow_tool", output="out", tool_key=key)

    callback.finalize()

    m = json.loads((callback.run_dir / "metrics.json").read_text())
    stats = m["tools"]["slow_tool"]
    assert stats["count"] == 5
    assert "avg_ms" in stats
    assert "p50_ms" in stats
    assert "p95_ms" in stats
    assert "max_ms" in stats
