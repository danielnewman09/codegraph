"""FilePlanner — node → file assignment, dedup, header/source split.

Decides which nodes render into which files (spec D5):

- **as-built round-trip:** use ``FileNode.path`` verbatim (regenerate in
  place → sync);
- **design graphs (no FileNode):** synthesize files from qualified names
  + configurable layout conventions (``defaults.toml``:
  ``include/<ns>/<Class>.hpp`` + ``src/<Class>.cpp``, or header-only);
- header/source split: declarations in header, definitions in source,
  only for members carrying a body (ImplementationNode or
  ``body_start``/``body_end``).

Also implements D9 duplicate-uid canonicalization (each uid emitted
once; on conflict prefer the occurrence at the shallowest
namespace-anchored placement, tie-broken by deterministic walk order —
R4: roots in order, children keyed by uid in insertion order, never
sorted by hash) and skips ``kind="type_parameter"`` slots from file
planning (they render inline in ``template<...>`` clauses).

Dispatcher is **provenance mode** (as-built passthrough vs design
synthesis), not node type — so this stays a single module until it
grows; if it does, split by mode (``planner/as_built.py``,
``planner/design.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilePlan:
    """One planned output file.

    Attributes:
        path: Output path (relative to the output root), e.g.
            ``include/cpp_sqlite/DataAccessObject.hpp``.
        kind: ``"header"`` or ``"source"``.
        node_keys: Keys of the graph entries rendered into this file,
            in render order.
        includes: ``#include`` set (INCLUDES edges + defaults).
        namespaces: Namespace nesting blocks.
    """

    path: str
    kind: str = "header"
    node_keys: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    namespaces: list[dict] = field(default_factory=list)


class FilePlanner:
    """Assign LayerGraph nodes to output files.

    Phase 1 render slice: ``plan()`` implements D5/D9 using the graph's
    FileNodes (as-built) or qname synthesis (design) per
    ``defaults.toml`` conventions.
    """

    def __init__(self, conventions: dict | None = None) -> None:
        self.conventions = conventions or {}

    def plan(self, graph) -> list[FilePlan]:
        """Plan output files for *graph*.

        Returns:
            List of FilePlan, in deterministic order.

        Raises:
            NotImplementedError: Phase 1 render slice.
        """
        raise NotImplementedError("FilePlanner.plan: Phase 1 render slice")


__all__ = ["FilePlan", "FilePlanner"]
