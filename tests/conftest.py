"""Pytest root configuration.

Loads the repo-root ``.env`` via python-dotenv so backend selection and
other settings can be configured without exporting shell variables::

    # .env
    CODEGRAPH_BACKEND=sqlite
    CODEGRAPH_TEST_SKIP_CONTAINER=1

Explicitly-set environment variables (shell / CI) take precedence over
the ``.env`` file (``override=False`` is the default).

Then registers the matching backend's conftest as a plugin: the SQLite
conftest by default (in-memory database, no Docker); when
``CODEGRAPH_BACKEND=neo4j`` the Neo4j backend fixtures are registered
instead (``test_neo4j_container``, ``setup_neomodel``, ``clear_db``).
Unit tests under ``tests/unit/`` skip Neo4j via
``CODEGRAPH_TEST_SKIP_CONTAINER=1`` in their own ``conftest.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env before the backend decision below (anchored to
# this file so it works regardless of cwd).  Shell/CI environment
# variables win over the file because load_dotenv defaults to
# override=False.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Desktop-launched pytest processes do not always inherit the interactive
# shell's Homebrew/pipx paths.  The integration suites require these tools;
# expose their standard local installation directories to Python and every
# subprocess it launches.
_tool_dirs = [Path("/opt/homebrew/bin"), Path.home() / ".local" / "bin"]
_path_parts = os.environ.get("PATH", "").split(os.pathsep)
for _tool_dir in reversed(_tool_dirs):
    _text = str(_tool_dir)
    if _tool_dir.is_dir() and _text not in _path_parts:
        _path_parts.insert(0, _text)
os.environ["PATH"] = os.pathsep.join(_path_parts)

# Backend selection drives which plugin's fixtures are global.
if os.environ.get("CODEGRAPH_BACKEND", "sqlite").lower() == "sqlite":
    pytest_plugins = ["tests.backends.sqlite.conftest"]
else:
    pytest_plugins = ["tests.backends.neo4j.conftest"]
