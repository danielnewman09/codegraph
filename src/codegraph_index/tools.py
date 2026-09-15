"""Compatibility export for Codegraph's dependency-query tools.

The indexing package does not own a backend driver or query language. The
historical toolset now lives with Codegraph's other graph tools; this module
preserves the old import path for callers that still use it.
"""

from codegraph.tools.dependency import DependencyGraphTools, create_toolset

__all__ = ["DependencyGraphTools", "create_toolset"]
