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

> **Status (2026-08-08):** Phase 1 design synthesis + as-built file
> passthrough are implemented.  D9 dedup covers nested-vs-peer compound
> duplicates (nested wins).  Header/source split and ``defaults.toml``
> convention wiring land with the render slice.

Dispatcher is **provenance mode** (as-built passthrough vs design
synthesis), not node type — so this stays a single module until it
grows; if it does, split by mode (``planner/as_built.py``,
``planner/design.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.codegen.context import base
from codegraph.constants import normalize_language

#: File extensions that denote a source (definition) translation unit.
_SOURCE_EXTS = (".cpp", ".cc", ".cxx", ".c++")

#: Compound types that can own a synthesized design header.
_PLANNABLE_COMPOUNDS = frozenset(
    {"ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ConceptNode", "ModuleNode"}
)


@dataclass
class FilePlan:
    """One planned output file.

    Attributes:
        path: Output path (relative to the output root), e.g.
            ``include/cpp_sqlite/DataAccessObject.hpp``.
        kind: ``"header"`` or ``"source"``.
        node_keys: Keys of the graph entries rendered into this file,
            in render order.
        file_key: For as-built plans, the FileNode entry's key (used to
            pull INCLUDES / path / language); None for design synthesis.
        includes: ``#include`` set (INCLUDES edges + defaults).
        namespaces: Namespace nesting blocks (filled by the context
            builder from qnames).
        language: Canonical language key (``"cpp"``).
    """

    path: str
    kind: str = "header"
    node_keys: list[str] = field(default_factory=list)
    file_key: str | None = None
    includes: list[str] = field(default_factory=list)
    namespaces: list[dict] = field(default_factory=list)
    language: str = "cpp"


class FilePlanner:
    """Assign LayerGraph nodes to output files."""

    def __init__(self, conventions: dict | None = None) -> None:
        self.conventions = conventions or {}

    # ── Entry point ─────────────────────────────────────────────────

    def plan(self, graph) -> list[FilePlan]:
        """Plan output files for *graph*.

        Dispatches on provenance mode: FileNode roots → as-built
        passthrough; otherwise design synthesis.  TestNode files are
        planned in addition in both modes.
        """
        has_files = any(
            type(entry.node).__name__ == "FileNode"
            for entry in graph.entries.values()
        )
        plans = (
            self._plan_as_built(graph)
            if has_files else self._plan_design(graph)
        )
        plans.extend(self._plan_tests(graph))
        return plans

    def _plan_tests(self, graph) -> list[FilePlan]:
        """Synthesize one ``tests/<name>.cpp`` per TestNode (Phase 3).

        Test nodes are composed under requirement nodes (HLR/LLR) which
        render nothing — they are discovered by walking the whole graph
        and planned independently.  Path synthesis mirrors the design
        compound convention: flat ``tests/<TestName>.cpp``.
        """
        plans: list[FilePlan] = []
        seen: set[str] = set()
        for entry in graph._all_entries():
            if type(entry.node).__name__ != "TestNode":
                continue
            name = entry.node.name or "test"
            key = graph._node_key(entry.node)
            if key in seen:
                continue
            seen.add(key)
            plans.append(FilePlan(
                path=f"tests/{name}.cpp",
                kind="test",
                node_keys=[key],
                language="cpp",
            ))
        return plans

    # ── Design graphs: qname-based synthesis (D5, header-only D8) ───

    def _plan_design(self, graph) -> list[FilePlan]:
        plans: list[FilePlan] = []
        planned_keys: set[str] = set()
        nested_keys = self._compound_nested_keys(graph)

        def maybe_plan(entry) -> None:
            key = graph._node_key(entry.node)
            if key in planned_keys or key in nested_keys:
                return  # each uid emitted once (D9); nested wins
            plan = self._design_file(graph, entry)
            if plan is not None:
                plans.append(plan)
                planned_keys.add(key)

        for root_entry in graph.entries.values():
            node_type = type(root_entry.node).__name__
            if node_type == "NamespaceNode":
                for child_type, type_children in root_entry.children.items():
                    if child_type not in _PLANNABLE_COMPOUNDS:
                        continue
                    for _key, child in type_children.items():
                        maybe_plan(child)
            elif node_type in _PLANNABLE_COMPOUNDS:
                maybe_plan(root_entry)
        return plans

    def _design_file(self, graph, entry) -> FilePlan | None:
        node = entry.node
        qn = node.qualified_name or ""
        if qn.startswith("std::"):
            return None  # library reference — not project code (Phase 1)
        name = node.name or (qn.rsplit("::", 1)[-1] if qn else "")
        if not name:
            return None
        ns_path = qn.rsplit("::", 1)[0] if "::" in qn else ""
        rel_dir = "/".join(part for part in ns_path.split("::") if part) if ns_path else ""
        path = f"include/{rel_dir}/{name}.hpp" if rel_dir else f"include/{name}.hpp"
        return FilePlan(
            path=path,
            kind="header",
            node_keys=[graph._node_key(node)],
            language="cpp",
        )

    @staticmethod
    def _compound_nested_keys(graph) -> set[str]:
        """Keys of compounds composed by another compound (D9: nested wins).

        A compound rendered inline inside a parent (e.g. the duplicate
        ``MigrationResult`` structs nested in ``MigrationManager``)
        must not also get its own top-level file.
        """
        nested: set[str] = set()
        for entry in graph._all_entries():
            if type(entry.node).__name__ not in base.COMPOUND_TYPES:
                continue
            for child_type, type_children in entry.children.items():
                if child_type in base.COMPOUND_TYPES:
                    nested.update(type_children.keys())
        return nested

    # ── As-built graphs: FileNode.path passthrough (D5) ─────────────

    def _plan_as_built(self, graph) -> list[FilePlan]:
        plans: list[FilePlan] = []
        seen: set[str] = set()
        for root_entry in graph.entries.values():
            if type(root_entry.node).__name__ != "FileNode":
                continue
            node = root_entry.node
            path = node.path or ""
            if not path:
                continue
            keys: list[str] = []
            for entry in graph._all_entries():
                if type(entry.node).__name__ not in _PLANNABLE_COMPOUNDS:
                    continue
                key = graph._node_key(entry.node)
                if key in seen:
                    continue
                if (getattr(entry.node, "file_path", "") or "") == path:
                    keys.append(key)
                    seen.add(key)
            kind = "source" if path.endswith(_SOURCE_EXTS) else "header"
            plans.append(FilePlan(
                path=path,
                kind=kind,
                node_keys=keys,
                file_key=graph._node_key(node),
                language=normalize_language(node.language or "cpp") or "cpp",
            ))
        return plans


__all__ = ["FilePlan", "FilePlanner"]
