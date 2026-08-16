"""Per-node-type context builders for codegen.

Mirrors ``src/codegraph/models/`` module-for-module: every node type in
``CodeGraphNode._registry`` has a declared builder here — either a real
context builder (rendered into the file context) or a *declared skip*
(returns ``None``, counted in ``CodegenResult.skipped`` with a reason).

No node type is handled implicitly.  ``tests/codegen/test_completeness.py``
iterates the model registry and asserts this module is exhaustive, so
adding a model type forces an explicit codegen decision.

``CodegenContextBuilder.build(graph, planner)`` orchestrates: counts
declared skips + orphaned members (D10), plans output files (via the
FilePlanner), builds one FileContext per planned file, and nests
compounds into namespace blocks by qualified name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

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
    source_fragment,
    test,
)
from codegraph.codegen import typeref

#: ``_scope_parts`` is re-exported from typeref for compatibility.
_scope_parts = typeref.scope_parts

#: node_type → build_context(entry, state) -> dict | None
#: ``None`` means the node is skipped (a declared no-op, not a bug).
BUILDERS: dict[str, Callable] = {}

#: node_type → human-readable skip reason (only for declared skips).
SKIP_REASONS: dict[str, str] = {}

_MODULES = (
    compound, member, file, namespace, parameter, implementation,
    literal, test, requirements, project, source_fragment,
)

for _module in _MODULES:
    _module_skips = getattr(_module, "SKIP_REASONS", {})
    for _node_type in _module.NODE_TYPES:
        if _node_type in _module_skips:
            # Per-type declared skip (e.g. TestFixtureNode inside an
            # otherwise-real module): registered as a skip_builder.
            BUILDERS[_node_type] = base.skip_builder(_module_skips[_node_type])
        else:
            BUILDERS[_node_type] = _module.build_context
    SKIP_REASONS.update(_module_skips)


@dataclass
class BuildState:
    """Shared state threaded through a codegen run.

    Attributes:
        graph: The LayerGraph being built.
        flat: node_key → CompositeEntry index (built once, shared).
        skipped: node_type → count of filtered nodes.
        warnings: Human-readable notes (orphans, duplicates, gaps).
        as_built: True when the input graph carries the ``as-built`` tag —
            as-built generation must render exactly what was indexed
            (no synthesized forward declarations, includes, or docs).
    """

    graph: object | None = None
    flat: dict = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # As-built mode mirrors the planner's provenance detection: a graph
        # with FileNode roots is an indexed source tree (render what was
        # indexed — never synthesize forward declarations, includes, or
        # docs).  The ``as-built`` tag alone is not sufficient: design
        # goldens can carry both tags (e.g. 'as-built' + 'design').
        self.as_built = False
        if self.graph is not None:
            self.as_built = any(
                type(entry.node).__name__ == "FileNode"
                for entry in getattr(self.graph, "entries", {}).values()
            )

    def count_skip(self, node_type: str) -> None:
        self.skipped[node_type] = self.skipped.get(node_type, 0) + 1


@dataclass
class BuildOutput:
    """Result of a context build (before template rendering).

    Attributes:
        files: ``{relative_path: FileContext dict}``.
        skipped: node_type → count of filtered nodes.
        warnings: Human-readable notes.
        graph_tags: Tags of the input LayerGraph.
        as_built: True when the input graph is FileNode-rooted (as-built
            mode) — the pack uses this to preserve source blank layout.
    """

    files: dict[str, dict] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    graph_tags: frozenset[str] = frozenset()
    as_built: bool = False


class CodegenContextBuilder:
    """LayerGraph → per-file context dicts (one per planned file)."""

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

    def build(self, graph, planner=None) -> BuildOutput:
        """Build ``{path: FileContext}`` for a LayerGraph.

        Args:
            graph: A :class:`~codegraph.graph.LayerGraph`.
            planner: A FilePlanner (defaults to a fresh one).

        Returns:
            BuildOutput with per-file contexts + skip/warning tallies.
        """
        from codegraph.codegen.planner import FilePlanner

        state = BuildState(graph=graph, flat=graph._flat_index())

        # 1. Count declared skips across every node (D11 scaffolding).
        for entry in graph._all_entries():
            node_type = type(entry.node).__name__
            if node_type in SKIP_REASONS:
                state.count_skip(node_type)

        # 2. Orphaned members at root (D10) render nothing — count + warn.
        orphan_qnames: list[str] = []
        for _key, entry in graph.entries.items():
            node_type = type(entry.node).__name__
            if node_type in base.MEMBER_TYPES and node_type not in SKIP_REASONS:
                state.count_skip(node_type)
                orphan_qnames.append(entry.node.qualified_name or entry.node.name or _key)
        if orphan_qnames:
            state.warnings.append(
                f"orphaned members skipped (D10): {len(orphan_qnames)} — "
                + ", ".join(sorted(orphan_qnames)[:8])
            )

        # 3. Plan files and build one FileContext per plan.
        if planner is None:
            planner = FilePlanner()
        plans = planner.plan(graph)

        files: dict[str, dict] = {}
        for plan in plans:
            file_ctx = self._build_file_context(graph, state, plan)
            if file_ctx is not None:
                files[plan.path] = file_ctx

        return BuildOutput(
            files=files,
            skipped=state.skipped,
            warnings=state.warnings,
            graph_tags=graph.tags,
            as_built=state.as_built,
        )

    # ── File-context assembly ──────────────────────────────────────

    def _build_file_context(self, graph, state, plan) -> dict | None:
        """Assemble one FileContext from a FilePlan."""
        top_contexts: list[dict] = []
        test_blocks: list[dict] = []
        for key in plan.node_keys:
            entry = state.flat.get(key)
            if entry is None:
                continue
            node_type = type(entry.node).__name__
            ctx = None
            if node_type in base.COMPOUND_TYPES:
                ctx = compound.build_context(entry, state)
            elif node_type == "NamespaceNode":
                ctx = namespace.build_context(entry, state)
            elif node_type in base.MEMBER_TYPES:
                ctx = member.build_context(entry, state)
            elif node_type == "TestNode":
                # Tests render as top-level blocks in their own .cpp file
                # (never namespace-nested — test qnames carry design-
                # pipeline namespaces like ``vm::``).
                ctx = test.build_context(entry, state)
            elif node_type == "SourceFragmentNode":
                ctx = source_fragment.build_context(entry, state)
            if ctx is None:
                continue
            if node_type == "TestNode":
                test_blocks.append(ctx)
            else:
                top_contexts.append(ctx)

        includes: list[str] = []
        indexed_file_ctx: dict = {}
        if plan.file_key:
            file_entry = state.flat.get(plan.file_key)
            if file_entry is not None:
                indexed_file_ctx = file.build_context(file_entry, state) or {}
                includes = list(indexed_file_ctx.get("includes", []))
        # The indexed source sequence is authoritative for as-built files.
        # In particular, an empty item denotes a deliberate include-group
        # separator; merging it with the planner's edge-derived list moves
        # that separator to the end and loses its source position.
        if not includes:
            includes = list(dict.fromkeys(plan.includes))

        file_ctx = {
            "type": "FileNode",
            "kind": plan.kind,
            "path": plan.path,
            # Design/test synthesis creates generated artifacts. As-built
            # reconstruction must not inject a banner absent from the index.
            "generated_banner": plan.file_key is None,
            "guard": (
                indexed_file_ctx.get("guard", "")
                if plan.file_key else _guard_for(plan.path)
            ),
            "language": plan.language or "cpp",
            "includes": includes,
            "namespace_leading_blank_lines": indexed_file_ctx.get(
                "namespace_leading_blank_lines", 0
            ),
            "namespace_trailing_blank_lines": indexed_file_ctx.get(
                "namespace_trailing_blank_lines", 0
            ),
            "guard_leading_blank_lines": indexed_file_ctx.get(
                "guard_leading_blank_lines", 0
            ),
            "leading_blank_lines": indexed_file_ctx.get("leading_blank_lines", 0),
            "forward_decls": [],
            "namespaces": _nest_by_namespace(top_contexts),
            "blocks": _top_level_blocks(top_contexts) + test_blocks,
        }
        # Preserve an otherwise-empty top-level namespace shell (e.g. a
        # ``.cpp`` whose namespace holds only blank lines): the FileNode
        # records the namespace name and the renderer emits open/close with
        # the indexed blank layout instead of dropping the region entirely.
        if not file_ctx["namespaces"] and indexed_file_ctx.get("namespace_name"):
            file_ctx["namespaces"] = [{
                "name": indexed_file_ctx["namespace_name"],
                "blocks": [],
                "namespaces": [],
            }]
        # Source files (.cpp) are rebuilt from the implementation export:
        # every method whose body lives in this file is routed here and
        # rendered inside its top-level namespace (the out-of-line
        # definition text carries its own ``Class::method`` signature).
        if plan.kind == "source":
            file_ctx["source_bodies"] = _collect_source_bodies(
                graph, state, plan.path
            )
        else:
            # Headers may carry structural complexity that the simple
            # namespace-tree path cannot express: re-opened namespace
            # regions, mid-file includes, or out-of-line definitions that
            # live in the header itself.  When present, the body is
            # rendered as a source-ordered layout instead.
            layout = _build_layout(
                file_ctx, top_contexts, graph, state, plan, indexed_file_ctx
            )
            if layout is not None:
                file_ctx["layout"] = layout
        return file_ctx


def _build_layout(file_ctx, top_contexts, graph, state, plan, indexed_file_ctx) -> list | None:
    """Source-ordered body layout for a structurally complex as-built header.

    Returns None for simple files (single namespace region, no mid-file
    include, no header-resident out-of-line definitions) — those keep the
    plain ``namespaces``/``blocks`` rendering.  When present, ``layout`` is
    a list of ordered items:

    - ``{"kind": "region", name, open_line, close_line,
       leading_blank_lines, trailing_blank_lines, blocks}`` — one namespace
       region with its source-ordered blocks (compounds, residuals, and
       header-resident out-of-line bodies);
    - ``{"kind": "residual", line, ctx}`` — a file-level residual;
    - ``{"kind": "include", line, spelling}`` — a mid-file include.
    """
    regions = list(indexed_file_ctx.get("namespace_regions") or [])
    if not regions:
        return None
    first_region_open = regions[0]["open_line"]

    # Split includes: top-of-file includes render in the header template;
    # mid-file includes (source line at/after the first namespace open)
    # become layout items at their source position.
    inc_lines = list(indexed_file_ctx.get("include_directive_lines") or [])
    includes = list(file_ctx.get("includes") or [])
    top_includes: list[str] = []
    mid_includes: list[dict] = []
    has_mid_include = False
    for i, inc in enumerate(includes):
        line = inc_lines[i] if i < len(inc_lines) else 0
        if line and line >= first_region_open:
            mid_includes.append({"kind": "include", "line": line, "spelling": inc})
            has_mid_include = True
        else:
            top_includes.append(inc)
    if top_includes and has_mid_include:
        while top_includes and top_includes[-1] == "":
            top_includes.pop()  # the group separator belongs to the mid include
    file_ctx["includes"] = top_includes

    # Header-resident out-of-line bodies (same file, non-contiguous with
    # their declaration) render at their source position in the header.
    header_bodies = _collect_flat_bodies(graph, state, plan.path)
    for body in header_bodies:
        body["variant"] = "defn"

    # Assign every namespace-anchored block (compound, placed residual,
    # header body) to the region containing its start line; file-level
    # residuals (placement "") become file units.
    region_blocks: list[list[dict]] = [[] for _ in regions]
    file_units: list[dict] = []
    for ctx in top_contexts:
        start = int(ctx.get("start_line") or 0)
        if ctx.get("type") == "SourceFragmentNode" and not ctx.get("placement"):
            file_units.append({"kind": "residual", "line": start, "ctx": ctx,
                               "end_line": int(ctx.get("end_line") or 0)})
            continue
        placed = False
        for index, region in enumerate(regions):
            if region["open_line"] <= start <= region["close_line"]:
                region_blocks[index].append(ctx)
                placed = True
                break
        if not placed:
            file_units.append({"kind": "residual", "line": start, "ctx": ctx,
                               "end_line": int(ctx.get("end_line") or 0)})
    for body in header_bodies:
        line = int(body.get("_line") or body.get("start_line") or 0)
        for index, region in enumerate(regions):
            if region["open_line"] <= line <= region["close_line"]:
                region_blocks[index].append(body)
                break

    items: list[dict] = []
    for index, region in enumerate(regions):
        items.append({
            "kind": "region",
            "name": region["name"],
            "start_line": region["open_line"],
            "close_line": region["close_line"],
            "leading_blank_lines": int(region.get("leading_blank_lines") or 0),
            "trailing_blank_lines": int(region.get("trailing_blank_lines") or 0),
            "blocks": sorted(region_blocks[index], key=_source_order_key),
        })
    items.extend(file_units)
    items.extend(mid_includes)
    return sorted(items, key=lambda item: (
        int(item.get("line") or item.get("start_line") or 0),
        item.get("kind", ""),
    ))


def _collect_flat_bodies(graph, state, plan_path: str) -> list[dict]:
    """Flat member contexts for out-of-line bodies living in *plan_path*.

    Unlike ``_collect_source_bodies`` (grouped for the .cpp renderer), this
    returns individual contexts so the layout can interleave them with
    residuals at their exact source lines.  Bodies are verbatim source and
    render via the ``_defn`` variant.
    """
    bodies: list[dict] = []
    for entry in state.flat.values():
        node = entry.node
        if type(node).__name__ not in ("MethodNode", "FunctionNode"):
            continue
        body = getattr(node, "body", "") or ""
        body_file = getattr(node, "body_file", "") or ""
        if not body:
            continue
        if body_file != plan_path:
            continue
        ctx = member.build_context(entry, state)
        if ctx is None or not ctx.get("body") or ctx.get("body_inline"):
            continue
        ctx["_line"] = (
            getattr(node, "body_start", 0)
            or getattr(node, "line_number", 0)
            or 0
        )
        bodies.append(ctx)
    return bodies


def _collect_source_bodies(graph, state, plan_path: str) -> list[dict]:
    """Member contexts for every method/function whose implementation body
    lives in *plan_path* (the implementation export routes bodies to their
    .cpp via ``body_file``)."""
    bodies: list[dict] = []
    for entry in state.flat.values():
        node = entry.node
        if type(node).__name__ not in ("MethodNode", "FunctionNode"):
            continue
        body = getattr(node, "body", "") or ""
        body_file = getattr(node, "body_file", "") or ""
        if not body:
            continue
        if body_file and body_file != plan_path:
            continue
        if not body_file and (getattr(node, "file_path", "") or "") != plan_path:
            continue
        ctx = member.build_context(entry, state)
        if ctx is not None and ctx.get("body"):
            # Source order is the only faithful ordering. For out-of-line
            # definitions, body_start belongs to the implementation file;
            # line_number often points at the header declaration instead.
            ctx["_line"] = (
                getattr(node, "body_start", 0)
                or getattr(node, "line_number", 0)
                or 0
            )
            bodies.append(ctx)
    # Group by the top-level namespace (``cpp_sqlite``) — bodies carry
    # their own ``Class::method`` scope, so only the namespace wrapper
    # is needed.
    grouped: dict[str, list[dict]] = {}
    for ctx in bodies:
        qn = ctx.get("placement", "") or ctx.get("qualified_name", "") or ""
        ns = qn.split("::", 1)[0] if "::" in qn else ""
        grouped.setdefault(ns, []).append(ctx)
    return [
        {
            "name": name,
            "bodies": sorted(ctxs, key=lambda c: (c.pop("_line", 0), c.get("qualified_name", ""))),
        }
        for name, ctxs in sorted(grouped.items())
    ]


def _guard_for(path: str) -> str:
    from codegraph.codegen import signature

    return signature.compute_guard(path) if path else ""


def _nest_by_namespace(top_contexts: list[dict]) -> list[dict]:
    """Nest compound contexts into namespace blocks by qualified name.

    ``cpp_sqlite::MigrationManager`` → ``[{"name": "cpp_sqlite",
    "blocks": [<ctx>], "namespaces": []}]``.  Contexts without a
    ``::``-qualified name fall through to the file's top-level
    ``blocks`` (handled by ``_top_level_blocks``).

    Nested namespaces live under each node's ``namespaces`` dict — the
    previous implementation stored them as sibling keys of the parent
    node, so any qname with three or more top-level ``::`` parts (or
    ``::`` inside template args) silently dropped its compound.

    Blocks are ordered by source position (``start_line``) so that
    structured declarations and residual fragments interleave exactly as
    they appear in the indexed source — fragments are never appended by
    node type.
    """
    root = {"blocks": [], "namespaces": {}}

    for ctx in top_contexts:
        qn = ctx.get("qualified_name", "") or ""
        parts = _scope_parts(qn)
        if len(parts) < 2:
            continue  # not namespace-anchored → top-level blocks
        node = root
        for part in parts[:-1]:
            node = node["namespaces"].setdefault(
                part, {"blocks": [], "namespaces": {}}
            )
        node["blocks"].append(ctx)

    def render(node: dict, name: str) -> dict:
        return {
            "name": name,
            "blocks": sorted(
                node["blocks"], key=_source_order_key
            ),
            "namespaces": [
                render(child, child_name)
                for child_name, child in node["namespaces"].items()
            ],
        }

    return [render(node, name) for name, node in root["namespaces"].items()]


def _source_order_key(ctx: dict) -> tuple[int, str]:
    """Sort key placing contexts by their first owned source line.

    Out-of-line body contexts carry ``_line`` (the body's source position in
    its implementation file); compounds/residuals use ``start_line``.  Falls
    back to ``line_number`` for contexts that predate the span fields, then
    to the qualified name for determinism.
    """
    line = (
        int(ctx.get("_line") or 0)
        or int(ctx.get("start_line") or 0)
        or int(ctx.get("line_number") or 0)
        or 0
    )
    return (line, ctx.get("qualified_name") or ctx.get("name") or "")


def _top_level_blocks(top_contexts: list[dict]) -> list[dict]:
    """Contexts with no namespace anchor (bare qnames, as-built files)."""
    blocks = [
        ctx
        for ctx in top_contexts
        if "::" not in (ctx.get("qualified_name", "") or "")
    ]
    return sorted(blocks, key=_source_order_key)


__all__ = [
    "BUILDERS",
    "SKIP_REASONS",
    "BuildState",
    "BuildOutput",
    "CodegenContextBuilder",
    "base",
]
