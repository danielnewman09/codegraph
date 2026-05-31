"""Neo4j driver management — shared connection singleton and standalone driver."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from neo4j import GraphDatabase

from codegraph.constants import CONSTRAINTS_AND_INDEXES

log = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")


class Neo4jConnection:
    """Manages a Neo4j driver singleton with session helpers."""

    def __init__(self) -> None:
        self._uri = NEO4J_URI
        self._user = NEO4J_USER
        self._password = NEO4J_PASSWORD
        self._driver = None
        log.info("Neo4jConnection created (uri=%s, user=%s)", self._uri, self._user)

    def get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            log.info("Neo4j driver created (uri=%s)", self._uri)
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            log.info("Neo4j driver closed")

    @contextmanager
    def session(self, database: str = "neo4j"):
        driver = self.get_driver()
        neo4j_session = driver.session(database=database)
        try:
            yield neo4j_session
        finally:
            neo4j_session.close()

    def verify_connectivity(self) -> bool:
        try:
            self.get_driver().verify_connectivity()
            log.debug("Neo4j connectivity verified")
            return True
        except Exception as e:
            log.warning("Neo4j connection failed: %s", e)
            return False

    def ensure_constraints(self):
        """Create indexes and constraints for the shared codegraph data model."""
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping constraint setup")
            return False
        with self.session() as session:
            for stmt in CONSTRAINTS_AND_INDEXES:
                try:
                    session.run(stmt)
                except Exception as e:
                    log.debug("Index/constraint may already exist: %s", e)
        log.info("Neo4j constraints and indexes ensured")
        return True


# Standalone driver (not bound to any app framework)
_standalone_driver = None


def get_standalone_driver():
    """Get or create the standalone Neo4j driver singleton."""
    global _standalone_driver
    if _standalone_driver is None:
        _standalone_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        log.info("Standalone Neo4j driver created")
    return _standalone_driver


def close_standalone_driver():
    global _standalone_driver
    if _standalone_driver is not None:
        _standalone_driver.close()
        _standalone_driver = None
        log.info("Standalone Neo4j driver closed")


@contextmanager
def get_standalone_session(database: str = "neo4j"):
    driver = get_standalone_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()
