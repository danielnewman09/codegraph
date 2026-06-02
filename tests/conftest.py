"""Pytest fixtures for neomodel tests.

Loads Neo4j credentials from the project .env file, then configures
neomodel and clears the database between tests.
"""

import os

import pytest
from dotenv import load_dotenv
from neomodel import db, get_config


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    """Configure neomodel for the test session and ensure labels exist."""
    load_dotenv()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

    host = uri.replace("bolt://", "")
    config = get_config()
    config.database_url = f"bolt://{user}:{password}@{host}"

    # Install labels (creates constraints/indexes)
    db.install_all_labels()
