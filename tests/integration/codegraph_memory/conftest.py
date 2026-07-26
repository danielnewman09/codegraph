"""Pytest configuration for codegraph-memory tests.

Integrates with the parent codegraph test infrastructure:
- ``setup_neomodel`` (session-scoped) — connects to the test Neo4j container
- ``clear_db`` (function-scoped, autouse) — wipes the database after each test

Adds a ``neo4j_connection`` fixture (alias for ``setup_neomodel`` +
``apply_schema``) so existing memory tests work without modification.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def neo4j_connection(setup_neomodel):
    """Apply memory schema after neomodel is configured.

    Depends on the parent conftest's ``setup_neomodel`` fixture which
    starts the test Neo4j container, configures neomodel, and installs
    base codegraph labels/constraints.
    """
    from codegraph_memory import apply_schema
    apply_schema()
    return setup_neomodel
