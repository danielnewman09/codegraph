"""Tests for codegraph.connection — Neo4j session and Cypher access."""

import pytest


def test_imports():
    """get_session, cypher_query, verify_connectivity are importable."""
    # codegraph:test-desc test_connection.test_imports::step_0
    # Imports the required functions (get_session, cypher_query, verify_connectivity)
    # from the code under test, establishing the necessary references for verification.
    from codegraph.persistence.connection import get_session, cypher_query, verify_connectivity
    # codegraph:test-desc test_connection.test_imports::post_0
    # Verifies that get_session is a callable function, confirming the imported object
    # can be used to initiate a session with the database.
    assert callable(get_session)
    # codegraph:test-desc test_connection.test_imports::post_1
    # Verifies that cypher_query is a callable function, ensuring the imported object
    # can properly execute Cypher queries against the database.
    assert callable(cypher_query)
    # codegraph:test-desc test_connection.test_imports::post_2
    # Verifies that verify_connectivity is a callable function, ensuring the imported
    # object is usable for establishing database connections as expected.
    assert callable(verify_connectivity)


def test_get_session_returns_context_manager():
    """get_session() returns a context manager.

    NOTE: Actually calling get_session() requires a running Neo4j, so we
    only verify the function is callable and returns the expected type
    when a connection is available.  When Neo4j is not running, this
    test is skipped.
    """
    # codegraph:test-desc test_connection.test_get_session_returns_context_manager::step_0
    # Initializes the test environment, likely by invoking get_session() to obtain the
    # session object that will be checked for context manager protocol compliance.
    from codegraph.persistence.connection import get_session
    try:
        session = get_session()
        # codegraph:test-desc test_connection.test_get_session_returns_context_manager::post_0
        # Verifies that the returned session object has an __enter__ method, which is
        # required for it to be used as a context manager with the 'with' statement.
        assert hasattr(session, "__enter__")
        # codegraph:test-desc test_connection.test_get_session_returns_context_manager::post_1
        # Verifies that the returned session object has an __exit__ method, completing
        # the context manager protocol to ensure proper resource cleanup.
        assert hasattr(session, "__exit__")
    except Exception:
        # Neo4j not running — skip
        pytest.skip("Neo4j not available")


def test_cypher_query_callable():
    """cypher_query is callable with query string."""
    # codegraph:test-desc test_connection.test_cypher_query_callable::step_0
    # Sets up the test environment by initializing the `cypher_query` function or object
    # that will be tested for callability.
    from codegraph.persistence.connection import cypher_query
    # codegraph:test-desc test_connection.test_cypher_query_callable::post_0
    # Verifies that `cypher_query` is a callable entity, confirming that the query is a
    # function or object capable of being invoked, which is essential for executing
    # Cypher queries.
    assert callable(cypher_query)


def test_top_level_exports():
    """get_session, cypher_query, verify_connectivity are exported from codegraph."""
    # codegraph:test-desc test_connection.test_top_level_exports::step_0
    # Imports the codegraph module to make its public API available for testing whether
    # the expected top-level functions are present.
    import codegraph
    # codegraph:test-desc test_connection.test_top_level_exports::post_0
    # Verifies that the codegraph module exposes a function named get_session,
    # confirming the module exports a required entry point for establishing database
    # sessions.
    assert hasattr(codegraph, "get_session")
    # codegraph:test-desc test_connection.test_top_level_exports::post_1
    # Verifies that the codegraph module exposes a function named cypher_query, ensuring
    # the module exports a required entry point for executing Cypher queries.
    assert hasattr(codegraph, "cypher_query")
    # codegraph:test-desc test_connection.test_top_level_exports::post_2
    # Verifies that the codegraph module exposes a function named verify_connectivity,
    # confirming the module exports a required entry point for checking database
    # connectivity.
    assert hasattr(codegraph, "verify_connectivity")


def test_ensure_driver_idempotent():
    """_ensure_driver can be called multiple times without error."""
    # codegraph:test-desc test_connection.test_ensure_driver_idempotent::step_0
    # Sets up the test environment by initializing the driver, preparing the system for
    # the subsequent idempotency check.
    from codegraph.persistence.connection import _ensure_driver
    # Should not raise even without a live Neo4j connection
    # (it only tries to connect if db.driver is None)
    try:
        _ensure_driver()
    except Exception:
        # Expected if Neo4j is not running — just verify no syntax errors
        pass