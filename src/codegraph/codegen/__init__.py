"""Codegen — LayerGraph → source code (C++ first).

A top-level subsystem (peer of ``codegraph.export``) that maps codegraph
node types to language templates using Jinja2.  Renders a LayerGraph
(design or as-built) into a tree of ``.hpp``/``.cpp`` files with a
deterministic, documented template contract per node type, plus a
round-trip verification path (export → parse → uid-diff).

Public API (Phase 1 render slice):

    result = generate_from_layer_graph(graph, language="cpp")
    result = generate(graph=graph, language="cpp")     # graph-aware alias

The module reads only ``LayerGraph`` instances — never a backend — so a
pack can be tested against raw graph JSON without a database (D2).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodegenResult:
    """Outcome of a codegen run.

    Attributes:
        files: Planned ``{relative_path: file_text}`` (empty until the
            render slice lands; ``--dry-run`` returns this without writing).
        skipped: ``{node_type: count}`` — nodes filtered from output
            (declared skips, orphans, untyped stubs).
        warnings: Human-readable warnings (duplicate-uid conflicts,
            signature-quality loss, missing types).
        graph_tags: The tags of the input LayerGraph (e.g.
            ``frozenset({"design"})``).
    """

    files: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    graph_tags: frozenset[str] = frozenset()

    def summarize(self) -> str:
        """One-line summary for CLI/log output."""
        parts = [f"{len(self.files)} file(s)"]
        if self.skipped:
            parts.append(
                "skipped: "
                + ", ".join(f"{k}={v}" for k, v in sorted(self.skipped.items()))
            )
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return "; ".join(parts)


def generate_from_layer_graph(graph, language: str = "cpp", **kwargs):
    """Render *graph* (a LayerGraph) into source files for *language*.

    Args:
        graph: A :class:`~codegraph.graph.LayerGraph`.
        language: Target language key (``"cpp"``; ``normalize_language``
            aliases are accepted defensively).
        **kwargs: ``pack`` (TemplatePack or pack directory), ``planner``
            (FilePlanner override), ``output_dir`` (write tree here).

    Returns:
        CodegenResult.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        "codegen.generate_from_layer_graph: Phase 1 render slice "
        "(context builders → FilePlanner → TemplatePack)"
    )


def generate(graph=None, language: str = "cpp", **kwargs):
    """Convenience wrapper accepting either a LayerGraph or a graph JSON
    list of dicts (auto-deserialized via ``LayerGraph.deserialize``).

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError(
        "codegen.generate: Phase 1 render slice "
        "(accepts LayerGraph or serialized JSON list)"
    )


__all__ = ["CodegenResult", "generate", "generate_from_layer_graph"]
