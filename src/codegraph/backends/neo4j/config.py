"""Neo4j backend configuration.

Extracted from ``codegraph.persistence.config``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from codegraph.backends.interface import BackendConfig


@dataclass
class Neo4jConfig(BackendConfig):
    """Neo4j connection configuration.

    Attributes:
        uri: Bolt URI (e.g. ``bolt://localhost:7687``).
        user: Neo4j username.
        password: Neo4j password.
    """

    uri: str = ""
    user: str = ""
    password: str = ""

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Build a Neo4jConfig from environment variables.

        Reads ``NEO4J_URI``, ``NEO4J_USER``, ``NEO4J_PASSWORD``.
        """
        return cls(
            uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", ""),
        )

    @property
    def database_url(self) -> str:
        """Return the full bolt URL with credentials embedded.

        e.g. ``bolt://neo4j:password@localhost:7687``
        """
        _bolt_host = self.uri.replace("bolt://", "")
        return f"bolt://{self.user}:{self.password}@{_bolt_host}"
