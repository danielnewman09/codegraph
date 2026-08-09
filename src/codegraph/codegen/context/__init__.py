"""Per-node-type context builders for codegen.

Mirrors ``src/codegraph/models/`` module-for-module: every node type in
``CodeGraphNode._registry`` has a declared builder here — either a real
context builder (rendered into the file context) or a *declared skip*
(returns ``None``, counted in ``CodegenResult.skipped`` with a reason).

No node type is handled implicitly.  ``tests/codegen/test_completeness.py``
iterates the model registry and asserts this module is exhaustive, so
adding a model type forces an explicit codegen decision.
"""

from __future__ import annotations

from collections.abc import Callable

from codegraph.codegen.context import (
    base,
    compound,
    file,
    implementation,
    literal,
    member,
    namespace,
    parameter,
    project,
    requirements,
    test,
)

#: node_type → build_context(entry, ctx) -> dict | None
#: ``None`` means the node is skipped (a declared no-op, not a bug).
BUILDERS: dict[str, Callable] = {}

#: node_type → human-readable skip reason (only for declared skips).
SKIP_REASONS: dict[str, str] = {}

_MODULES = (
    compound, member, file, namespace, parameter, implementation,
    literal, test, requirements, project,
)

for _module in _MODULES:
    for _node_type in _module.NODE_TYPES:
        BUILDERS[_node_type] = _module.build_context
    SKIP_REASONS.update(getattr(_module, "SKIP_REASONS", {}))


class CodegenContextBuilder:
    """LayerGraph → per-file context dicts (one per planned file).

    Phase 1 render slice: ``build()`` walks the graph, consults the
    FilePlanner for file assignment, and dispatches each node to its
    builder via :data:`BUILDERS`.
    """

    @staticmethod
    def builder_for(node_type: str) -> Callable | None:
        """Return the builder for *node_type*, or ``None`` if unknown."""
        return BUILDERS.get(node_type)

    @staticmethod
    def is_skipped(node_type: str) -> bool:
        """True when *node_type* is a declared skip (renders nothing)."""
        return node_type in SKIP_REASONS

    @staticmethod
    def skip_reason(node_type: str) -> str:
        return SKIP_REASONS.get(node_type, "")

    def build(self, graph, planner=None) -> dict:
        """Build ``{FileKey: FileContext}`` for a LayerGraph.

        Args:
            graph: A :class:`~codegraph.graph.LayerGraph`.
            planner: A FilePlanner (defaults to a fresh one).

        Returns:
            Mapping from planned file key to file context dict.

        Raises:
            NotImplementedError: Phase 1 render slice.
        """
        raise NotImplementedError(
            "CodegenContextBuilder.build: Phase 1 render slice (context builders)"
        )


__all__ = [
    "BUILDERS",
    "SKIP_REASONS",
    "CodegenContextBuilder",
    "base",
]
