"""Neomodel connection configuration.

Set ``config.DATABASE_URL`` from environment variables before any
neomodel model class is imported. Import this module first.
"""

import os
from neomodel import get_config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# Use the modern configuration API (neomodel 6.x)
_bolt_host = NEO4J_URI.replace("bolt://", "")
config = get_config()
config.database_url = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
