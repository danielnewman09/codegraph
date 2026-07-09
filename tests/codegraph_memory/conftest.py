"""Compatibility fixtures for codegraph-memory tests.

These tests were originally written against a standalone codegraph-memory
package with its own Neo4j connection fixture.  Now that codegraph-memory
lives inside the codegraph repo, we adapt to codegraph's existing test
infrastructure (test Neo4j container, setup_neomodel, clear_db).
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def neo4j_connection(setup_neomodel):
    """Compatibility shim — codegraph's setup_neomodel already configures
    neomodel and installs labels.  We just need to apply the memory-specific
    schema (constraints/indexes for memory node types)."""
    from codegraph_memory import apply_schema
    apply_schema()
    yield
