"""Pipeline test configuration.

Sets up Neo4j connection for ingestion fixtures and configures
logging so fixture progress is visible during test runs.
"""

from __future__ import annotations

import logging
import sys

import pytest


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
