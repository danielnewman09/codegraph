"""Required agent-suite labeling.

Agent dependencies are part of the base package requirements.  This conftest
only labels the tests so CI can select the lane; import failures are test
collection failures and must remain visible.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every collected test so CI can select the agent lane."""
    marker = pytest.mark.agents
    for item in items:
        item.add_marker(marker)
