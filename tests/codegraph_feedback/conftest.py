"""Test fixtures for codegraph_feedback tests."""

import os
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_requirements_dir(tmp_path):
    """Create a temporary codegraph/requirements directory structure
    with a feedback.md file for testing."""
    req_dir = tmp_path / "codegraph" / "requirements"
    feedback_dir = req_dir / "generated" / "feedback_docs"
    feedback_dir.mkdir(parents=True)

    # Create a sample feedback file
    feedback_content = """# Architecture Diagram Generator — Unified Module View

> **Source**: Neo4j codegraph, `design` tag

The Architecture Diagram Generator shall produce a single unified PlantUML diagram

---

## AG-LLR-01 — Fetch module subgraph via codegraph_query

The tool shall accept a root namespace qualified name (e.g. `codegraph.export`)

### Feedback

The current approach queries ALL modules at once. We should consider streaming
modules one at a time to reduce memory usage. This is a tradeoff: simpler code
but potentially slower for large graphs.

## AG-LLR-02 — Concern classifier from namespace segment derivation

The tool shall classify each class and function into a *concern group*

### Feedback

<!-- Write your feedback on this requirement below. -->

## AG-LLR-03 — Edge routing with relationship-type styling

The tool shall convert INVOKES, DEPENDS_ON, INHERITS_FROM, and COMPOSES

### Feedback

We need to use dashed lines for DEPENDS_ON edges based on the PlantUML spec.
Solid lines should be reserved for COMPOSES only. This is a constraint from
the rendering pipeline.

"""
    feedback_file = feedback_dir / "01_unified_module_view.md"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    feedback_file.write_text(feedback_content)

    # Also create a per-component feedback file
    comp_dir = req_dir / "architecture-diagram-generator"
    comp_dir.mkdir(parents=True, exist_ok=True)
    comp_feedback = comp_dir / "feedback.md"
    comp_feedback.write_text(feedback_content)

    # Save old cwd and chdir
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    yield {
        "tmp_path": tmp_path,
        "feedback_file": str(feedback_file),
        "comp_feedback": str(comp_feedback),
        "req_dir": str(req_dir),
    }

    os.chdir(old_cwd)


@pytest.fixture(scope="session", autouse=True)
def neo4j_connection(setup_neomodel):
    """Apply memory schema for tests that need Neo4j."""
    from codegraph_memory import apply_schema
    apply_schema()
    yield
