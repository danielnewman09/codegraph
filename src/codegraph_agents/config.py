"""Agent configuration.

Provides :class:`AgentConfig` — typed parameters for a single agent run.

On import, loads the project root ``.env`` file via ``python-dotenv``
(``override=False`` — never clobber already-set env vars).  All
LLM-related defaults are resolved from environment variables at config
construction time.

For context loading, see :mod:`codegraph_agents.context`.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger("codegraph_agents.config")

# ── Auto-load project .env (override=False — ok if already loaded) ──
_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _DOTENV_PATH.exists():
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)


@dataclass
class AgentConfig:
    """Typed configuration for a single agent run.

    All LLM defaults read from environment variables at construction
    time (pre-loaded from the project root ``.env``):

    * ``LLM_MODEL`` → :attr:`model` (default ``"gpt-4o"``)
    * ``LLM_BASE_URL`` → :attr:`base_url` (default ``""``)
    * ``LLM_API_KEY`` → :attr:`api_key` (default ``""``)
    * ``LLM_TOOL_CHOICE`` → :attr:`tool_choice` (default ``"auto"``)

    Attributes:
        run_id: Unique identifier for this run.  Auto-generated
            UUID if not set.
        hlr_uid: UUID of the HLR being processed
            (optional — only set for HLR-specific agents).
        model: LLM model name.
        base_url: OpenAI-compatible API base URL.
        api_key: API key for the LLM provider.
        tool_choice: ``"auto"``, ``"required"``, or ``"none"``.
        max_tokens: Maximum tokens per turn.
        max_turns: Safety limit on agent iterations.
        timeout: Timeout in seconds for each model call
            (default 120).  The OpenAI SDK default is 600s which
            can cause silent hangs on transient network issues.
        log_dir: Directory for structured log output
            (JSONL, markdown, metrics, response).
        checkpoint: Enable LangGraph checkpointing.
        component_namespace: Namespace constraint for the target
            component (used by design/decompose agents).
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    hlr_uid: str = ""

    model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY", "")
    )
    tool_choice: str = field(
        default_factory=lambda: os.getenv("LLM_TOOL_CHOICE", "auto")
    )
    max_tokens: int = 65536
    max_turns: int = 75
    timeout: int = 120
    log_dir: str = "codegraph/logs"
    checkpoint: bool = True

    component_namespace: str = ""


# Backward-compat — ContextProvider moved to codegraph_agents.context
from codegraph_agents.context import ContextProvider  # noqa: E402, F401
