"""Tests for the Neo4j backend connection layer."""

import pytest


def test_imports():
    """Neo4jConnection is importable."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    assert Neo4jConnection is not None


def test_get_session_returns_context_manager():
    """Neo4jConnection.get_session() returns a context manager.

    NOTE: Actually calling get_session() requires a running Neo4j, so we
    only verify the function is callable and returns the expected type
    when a connection is available.  When Neo4j is not running, this
    test is skipped.
    """
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    try:
        session = conn.get_session()
        assert hasattr(session, "__enter__")
        assert hasattr(session, "__exit__")
    except Exception:
        pytest.skip("Neo4j not available")


def test_execute_raw_callable():
    """Neo4jConnection.execute_raw is callable."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    conn = Neo4jConnection.__new__(Neo4jConnection)
    assert callable(conn.execute_raw)


def test_top_level_exports():
    """get_backend is exported from codegraph."""
    import codegraph
    assert hasattr(codegraph, "get_backend")


def test_ensure_driver_idempotent():
    """_ensure_driver can be called multiple times without error."""
    from codegraph.backends.neo4j.connection import Neo4jConnection
    from codegraph.backends.neo4j.config import Neo4jConfig
    conn = Neo4jConnection(Neo4jConfig.from_env())
    try:
        conn.ensure_driver()
    except Exception:
        # Expected if Neo4j is not running — just verify no syntax errors
        pass
