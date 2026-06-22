"""Pytest fixtures for neomodel tests.

Loads Neo4j credentials from the project .env file, then configures
neomodel and clears the database once before the test session.
"""

import os

import pytest
from dotenv import load_dotenv
from neomodel import db, get_config


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    """Configure neomodel, install labels, and clear the database once
    before the test session starts.
    """
    load_dotenv()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

    host = uri.replace("bolt://", "")
    config = get_config()
    config.database_url = f"bolt://{user}:{password}@{host}"

    # Drop ALL existing constraints and indexes so that a schema change
    # (e.g. qualified_name going from UniqueIdProperty to StringProperty)
    # doesn't collide with stale constraints from a previous session.
    try:
        results, _ = db.cypher_query(
            "SHOW CONSTRAINTS YIELD name RETURN name"
        )
        for r in results:
            db.cypher_query(f"DROP CONSTRAINT {r[0]} IF EXISTS")
        results, _ = db.cypher_query(
            'SHOW INDEXES YIELD name, type WHERE type <> "LOOKUP" RETURN name'
        )
        for r in results:
            db.cypher_query(f"DROP INDEX {r[0]} IF EXISTS")
    except Exception:
        pass  # best-effort — ignore if Neo4j is empty/fresh

    # Install labels (creates constraints/indexes)
    db.install_all_labels()

    # Wipe the database once before the session
    db.cypher_query("MATCH (n) DETACH DELETE n")


@pytest.fixture(autouse=True)
def clear_db():
    """Clear the Neo4j database before each test.

    Ensures that tests with explicit unique identifiers (refid,
    qualified_name) don't collide with data from previous tests.
    """
    yield
    db.cypher_query("MATCH (n) DETACH DELETE n")