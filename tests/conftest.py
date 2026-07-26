"""Pytest root configuration.

Loads the Neo4j backend conftest as a plugin so that
``test_neo4j_container``, ``setup_neomodel``, and ``clear_db`` are
available.  Unit tests under ``tests/unit/`` skip Neo4j via
``CODEGRAPH_TEST_SKIP_CONTAINER=1`` in their own ``conftest.py``.
"""

from __future__ import annotations

# Global plugin: Neo4j backend fixtures available everywhere
pytest_plugins = ["tests.backends.neo4j.conftest"]
