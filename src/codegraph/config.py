"""Neomodel connection configuration.

Set ``config.DATABASE_URL`` from environment variables before any
neomodel model class is imported. Import this module first.
"""

import os
from neomodel import config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# neomodel expects "bolt://user:password@host:port"
_bolt_host = NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
