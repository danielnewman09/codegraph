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

import os

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
        **kwargs:
            pack: A TemplatePack, or a pack directory path (overrides
                the builtin pack).
            planner: A FilePlanner override.
            builder: A CodegenContextBuilder override.
            output_dir: When given, the generated tree is written here
                (files are still returned in ``result.files``).

    Returns:
        CodegenResult with rendered ``files`` (path → text).
    """
    from codegraph.codegen.context import CodegenContextBuilder
    from codegraph.codegen.pack import TemplatePack
    from codegraph.constants import normalize_language

    lang = normalize_language(language) or "cpp"

    emit_markers = bool(kwargs.get("emit_markers", False))
    pack = kwargs.get("pack")
    if pack is None:
        pack = TemplatePack(language=lang, emit_markers=emit_markers)
    elif isinstance(pack, (str, os.PathLike)):
        pack = TemplatePack(language=lang, directory=pack, emit_markers=emit_markers)
    else:
        pack.emit_markers = emit_markers

    builder = kwargs.get("builder") or CodegenContextBuilder()
    output = builder.build(graph, planner=kwargs.get("planner"))

    files: dict[str, str] = {}
    for path, ctx in output.files.items():
        files[path] = pack.render_file(ctx)

    result = CodegenResult(
        files=files,
        skipped=output.skipped,
        warnings=output.warnings,
        graph_tags=output.graph_tags,
    )

    output_dir = kwargs.get("output_dir")
    if output_dir:
        _written, _skipped_abs = _write_tree(files, output_dir)
        if _skipped_abs:
            result.warnings.append(
                f"{len(_skipped_abs)} absolute-path file(s) not written "
                f"outside output root (external deps): "
                + ", ".join(sorted(_skipped_abs)[:3])
            )
    return result


def generate(graph=None, language: str = "cpp", **kwargs):
    """Render a LayerGraph (or serialized JSON list) into source files.

    Accepts either a :class:`~codegraph.graph.LayerGraph` or a list of
    serialized node dicts (auto-deserialized), so raw graph JSON can be
    rendered without a database (D2).  See
    :func:`generate_from_layer_graph` for keyword options.
    """
    from codegraph.graph import LayerGraph

    if not isinstance(graph, LayerGraph):
        graph = LayerGraph.deserialize(graph)
    return generate_from_layer_graph(graph, language=language, **kwargs)


def _write_tree(files: dict[str, str], output_dir) -> tuple[list[str], list[str]]:
    """Write the rendered file tree under *output_dir*.

    As-built graphs can carry **absolute** planned paths — external
    one-hop dependencies (e.g. conan-cache headers) keep their
    ``FileNode.path`` verbatim.  ``os.path.join(root, absolute)`` would
    silently resolve to the absolute path itself and **overwrite the
    real file**, so absolute paths are skipped: only paths inside the
    output root are written.

    Returns ``(written_paths, skipped_absolute_paths)`` — the caller
    surfaces the skips as a warning.
    """
    import os

    root = os.fspath(output_dir)
    written: list[str] = []
    skipped: list[str] = []
    for rel_path, text in files.items():
        if os.path.isabs(rel_path):
            skipped.append(rel_path)
            continue
        dest = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append(dest)
    return written, skipped


__all__ = ["CodegenResult", "generate", "generate_from_layer_graph"]
