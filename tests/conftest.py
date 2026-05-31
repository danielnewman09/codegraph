"""Pytest fixtures for neomodel tests.

Requires a running Neo4j instance. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
environment variables, or defaults to bolt://localhost:7687 with neo4j/msd-local-dev.
"""

import pytest
from neomodel import db, get_config


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    """Configure neomodel for the test session and ensure labels exist."""
    import os

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

    host = uri.replace("bolt://", "")
    config = get_config()
    config.database_url = f"bolt://{user}:{password}@{host}"

    # Install labels (creates constraints/indexes)
    db.install_all_labels()


@pytest.fixture(autouse=True)
def clear_db():
    """Wipe all nodes and relationships before each test for isolation."""
    db.cypher_query("MATCH (n) DETACH DELETE n")
    yield
