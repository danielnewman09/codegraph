"""Canonical generated-artifact locations for Python integration tests."""

from __future__ import annotations

import os
from pathlib import Path


CODEGRAPH_ROOT = Path(
    os.environ.get("CODEGRAPH_ROOT", Path(__file__).resolve().parents[4])
)
ARTIFACT_ROOT = CODEGRAPH_ROOT / "tests"
UNIT_TEST_DATA = ARTIFACT_ROOT / "unit_test_data"
CODEGRAPH_OUTPUT = ARTIFACT_ROOT / "codegraph_output"

#: Provenance tag for repository-authored requirements documents ingested by
#: the unified index operation (see design_intent/14-prioritized-work-roadmap.md,
#: Priority 4).
REQUIREMENTS_TAG = "requirements"

#: Tags marking the durable overlay layer.  Overlay nodes are repository-owned
#: (they share the project ``source``) but are *not* parser-owned as-built
#: facts: requirement documents, and the design/scaffold placeholders they
#: carry, are authored and reviewed by hand.
OVERLAY_TAGS = frozenset({REQUIREMENTS_TAG, "design", "scaffold"})


def node_tags(node) -> tuple[str, ...]:
    """Return the tags of a backend ``CodeGraphNode`` or a serialized dict."""
    if isinstance(node, dict):
        tags = node.get("tags") or ()
    else:
        tags = getattr(node, "tags", ()) or ()
    return tuple(tags)


def is_overlay(node) -> bool:
    """True when a node belongs to the durable (non-as-built) overlay."""
    return any(tag in OVERLAY_TAGS for tag in node_tags(node))
