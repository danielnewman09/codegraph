"""Pipeline test configuration.

Sets up Neo4j connection for ingestion fixtures and configures
logging so fixture progress is visible during test runs.

Shared fixtures:

* ``_cleanup_design_data`` — autouse module cleanup
* ``ingest_requirements`` — loads requirements markdown, returns HLR uid
"""

from __future__ import annotations

import logging
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
    """Override root conftest — use the main Neo4j container, never wipe.

    The root ``tests/conftest.py`` starts a test container on port 7688
    and wipes it.  Pipeline tests use the main container on 7687
    so that ingested as-built + requirements data persists across
    the module.
    """
    _setup_logging()

    try:
        from neomodel import config, db

        config.DATABASE_URL = "bolt://neo4j:codegraph@localhost:7687"
        db.set_connection(config.DATABASE_URL)

        # Smoke test — do NOT wipe the database
        results, _ = db.cypher_query("RETURN 1")
        assert results[0][0] == 1
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
    """Check if Neo4j is reachable."""
    try:
        from neomodel import db
        db.set_connection("bolt://neo4j:codegraph@localhost:7687")
        db.cypher_query("RETURN 1")
        return True
    except Exception:
        return False


# ── Shared fixtures ──────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _cleanup_design_data():
    """Clear stale design/scaffold/requirements nodes before the module.

    Prevents constraint violations when requirements content has
    changed between runs and old UIDs conflict with new node types.
    """
    if not _has_neomodel_connection():
        return
    from neomodel import db as neodb
    neodb.cypher_query(
        "MATCH (n) WHERE 'design' IN n.tags "
        "OR 'scaffold' IN n.tags "
        "OR 'requirements' IN n.tags "
        "DETACH DELETE n"
    )


@pytest.fixture(scope="module")
def ingest_requirements():
    """Import requirements + tests from the saved markdown.

    Returns the HLR uid for use by lint/design agents.
    """
    import logging
    log = logging.getLogger(__name__)

    md_path = PIPELINE_DATA_DIR / "migration_manager_requirements.md"
    if not md_path.exists():
        pytest.skip(f"requirements fixture not found: {md_path}")

    from codegraph.export.markdown import MarkdownImporter

    log.info("Ingesting requirements fixture: %s", md_path)
    text = md_path.read_text(encoding="utf-8")
    importer = MarkdownImporter(
        tags=frozenset({"design"}), strict=False,
    )
    graph = importer.import_markdown(text)

    entries = list(graph._all_entries())
    log.info("Parsed %d entries from requirements markdown", len(entries))

    graph.to_neo4j()
    log.info("Persisted %d entries to Neo4j (design)", len(entries))

    for diag in importer.diagnostics:
        log.warning("Markdown diagnostic: %s", diag)

    # Find the Database Migration Manager HLR specifically
    from codegraph_requirements.models import HLR

    hlrs = list(HLR.nodes.filter(name="Database Migration Manager"))
    assert len(hlrs) == 1, (
        f"Expected 1 HLR named 'Database Migration Manager', "
        f"got {len(hlrs)}: {[h.name for h in HLR.nodes.all()]}"
    )
    hlr_uid = hlrs[0].uid
    log.info("HLR uid: %s (name: %s)", hlr_uid[:16], hlrs[0].name)
    return hlr_uid
