"""Pipeline test configuration.

Sets up the storage backend (SQLite by default, Neo4j opt-in) for
ingestion fixtures and configures logging so fixture progress is
visible during test runs.

Shared fixtures:

* ``_cleanup_design_data`` — autouse module cleanup
* ``ingest_requirements`` — loads requirements markdown, returns HLR uid
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

# Path to the cpp_sqlite test data shared across pipeline tests
PIPELINE_DATA_DIR = Path(__file__).parent / "data" / "cpp_sqlite"


def _setup_logging():
    """Configure root logger and agent loggers to show DEBUG+ on stderr during tests.

    Uses ``setLevel`` directly instead of ``basicConfig`` because pytest
    may already have installed handlers on the root logger, making
    ``basicConfig`` a no-op.
    """
    logging.root.setLevel(logging.DEBUG)
    # Ensure agent loggers inherit the permissive level
    for name in (
        "codegraph_agents",
        "codegraph_agents.design",
        "codegraph_agents.context",
        "codegraph_agents.decompose",
        "codegraph_agents.requirements_lint",
        "codegraph_design.tools",
    ):
        logging.getLogger(name).setLevel(logging.DEBUG)
    # Suppress noisy neo4j driver debug logs
    logging.getLogger("neo4j").setLevel(logging.ERROR)
    logging.getLogger("neomodel").setLevel(logging.ERROR)


@pytest.fixture(autouse=True)
def clear_db():
    """Override the root clear_db fixture — do NOT wipe between tests.

    Pipeline tests use module-scoped fixtures that ingest data once.
    The root conftest's autouse clear_db would destroy that data after
    each test function.  This override replaces it with a no-op so
    ingested data survives across all tests in the module.
    """
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    """Backend-aware setup — SQLite by default, Neo4j opt-in.

    SQLite (``CODEGRAPH_BACKEND=sqlite``, the default): the root
    conftest's sqlite plugin already installed an in-memory
    ``SqliteBackend``; nothing to do here.  Pipeline modules ingest
    once (``clear_db`` is a no-op in this conftest) and the in-memory
    DB is discarded when the session ends — no persistent store to
    accumulate stale data.

    Neo4j (``CODEGRAPH_BACKEND=neo4j``): use the main development
    container on port 7687 and never wipe it, so ingested as-built +
    requirements data persists across the module.
    """
    _setup_logging()

    if os.environ.get("CODEGRAPH_BACKEND", "sqlite").lower() != "neo4j":
        # SQLite (or memory) — the root conftest already configured the
        # backend for this session.
        yield
        return

    try:
        from codegraph.backends import get_backend, set_backend
        from codegraph.backends.neo4j import Neo4jBackend, Neo4jConfig

        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="codegraph",
        )
        set_backend(Neo4jBackend(config))

        # Smoke test — do NOT wipe the database
        if not get_backend().health_check():
            pytest.skip("Neo4j not available")
    except Exception as exc:
        pytest.skip(f"Neo4j not available: {exc}")

    yield


@pytest.fixture(scope="session")
def test_neo4j_container():
    """Override root conftest — skip the test container for pipeline tests.

    Pipeline tests use the main development Neo4j container (port 7687),
    not the isolated test container.
    """
    yield


# ── Shared helpers ───────────────────────────────────────────────


def _has_neomodel_connection():
    """Check if the active storage backend is reachable."""
    try:
        from codegraph.backends import get_backend
        return get_backend().health_check()
    except Exception:
        return False


def _cleanup_design_and_scaffold() -> None:
    """Clear stale design/scaffold/requirements nodes.

    Prevents constraint violations when requirements content has
    changed between runs and old UIDs conflict with new node types.
    """
    if not _has_neomodel_connection():
        return
    from codegraph.backends import get_backend
    g = get_backend().graph
    for tag in ("design", "scaffold", "requirements"):
        for uid in g.find_uids_by_tag(tag):
            g.delete_by_uid(uid)


def _ingest_requirements_text(
    label: str, md_path: Path,
) -> str:
    """Ingest a requirements markdown file and return the HLR uid.

    Args:
        label: Human-readable label for logging.
        md_path: Path to the markdown file.

    Returns:
        The uid of the 'Database Migration Manager' HLR node.
    """
    import logging
    log = logging.getLogger(__name__)

    if not md_path.exists():
        raise FileNotFoundError(f"requirements fixture not found: {md_path}")

    from codegraph.export.markdown import MarkdownImporter

    log.info("[%s] Ingesting requirements: %s", label, md_path.name)
    text = md_path.read_text(encoding="utf-8")
    importer = MarkdownImporter(
        tags=frozenset({"design"}), strict=False,
    )
    graph = importer.import_markdown(text)

    entries = list(graph._all_entries())
    log.info("[%s] Parsed %d entries from requirements", label, len(entries))

    graph.to_neo4j()
    log.info("[%s] Persisted %d entries to Neo4j", label, len(entries))

    for diag in importer.diagnostics:
        log.warning("Markdown diagnostic: %s", diag)

    from codegraph_requirements.models import HLR
    hlrs = list(HLR.nodes.filter(name="Database Migration Manager"))
    assert len(hlrs) == 1, (
        f"[{label}] Expected exactly 1 HLR named 'Database Migration Manager', "
        f"got {len(hlrs)}: {[h.name for h in HLR.nodes.all()]}"
    )
    hlr_uid = hlrs[0].uid
    log.info("[%s] HLR uid: %s (name: %s)", label, hlr_uid[:16], hlrs[0].name)
    return hlr_uid


# ── Shared fixtures ──────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _cleanup_design_data():
    """Clear stale design/scaffold/requirements nodes before the module.

    Prevents constraint violations when requirements content has
    changed between runs and old UIDs conflict with new node types.
    """
    _cleanup_design_and_scaffold()


@pytest.fixture(scope="module")
def ingest_requirements_v2():
    """Import v2 requirements + tests (with all lint fixes applied).

    Returns the HLR uid for use by lint/design agents.
    """
    md_path = PIPELINE_DATA_DIR / "migration_manager_requirements_v2.md"
    return _ingest_requirements_text("v2", md_path)


@pytest.fixture(scope="module")
def ingest_requirements():
    """Import v1 requirements + tests from the saved markdown.

    Returns the HLR uid for use by lint/design agents.
    """
    md_path = PIPELINE_DATA_DIR / "migration_manager_requirements.md"
    return _ingest_requirements_text("v1", md_path)
