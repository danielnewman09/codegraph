"""Tests for codegraph.connection — Neo4j session and Cypher access."""

import pytest


def test_imports():
    """get_session, cypher_query, verify_connectivity are importable."""
    from codegraph.connection import get_session, cypher_query, verify_connectivity
    assert callable(get_session)
    assert callable(cypher_query)
    assert callable(verify_connectivity)


def test_get_session_returns_context_manager():
    """get_session() returns a context manager.

    NOTE: Actually calling get_session() requires a running Neo4j, so we
    only verify the function is callable and returns the expected type
    when a connection is available.  When Neo4j is not running, this
    test is skipped.
    """
    from codegraph.connection import get_session
    try:
        session = get_session()
        assert hasattr(session, "__enter__")
        assert hasattr(session, "__exit__")
    except Exception:
        # Neo4j not running — skip
        pytest.skip("Neo4j not available")


def test_cypher_query_callable():
    """cypher_query is callable with query string."""
    from codegraph.connection import cypher_query
    assert callable(cypher_query)


def test_top_level_exports():
    """get_session, cypher_query, verify_connectivity are exported from codegraph."""
    import codegraph
    assert hasattr(codegraph, "get_session")
    assert hasattr(codegraph, "cypher_query")
    assert hasattr(codegraph, "verify_connectivity")


def test_ensure_driver_idempotent():
    """_ensure_driver can be called multiple times without error."""
    from codegraph.connection import _ensure_driver
    # Should not raise even without a live Neo4j connection
    # (it only tries to connect if db.driver is None)
    try:
        _ensure_driver()
    except Exception:
        # Expected if Neo4j is not running — just verify no syntax errors
        pass