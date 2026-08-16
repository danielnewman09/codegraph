"""TemplatePack — language pack resolution + rendering (spec D3, R2).

A TemplatePack is a directory of ``.j2`` files + a resolution table.
The built-in ``cpp`` pack ships in the wheel; users override by
pointing at their own pack directory (``--pack <dir>``).

The pack layout mirrors ``src/codegraph/models/`` — **one directory per
node type**:

    templates/<lang>/<NodeType>/<kind>.j2      # kind variant (e.g. struct.j2)
    templates/<lang>/<NodeType>/<kind>_<variant>.j2   # decl/defn variants
    templates/<lang>/<NodeType>/default.j2    # kind fallback
    templates/<lang>/default.j2               # pack-level fallback (explicit TODO)
    templates/<lang>/_skipped.j2              # declared-skip marker

``resolve(node_type, kind, variant)`` normalizes the kind via the D11
alias table (``enum_value→enumvalue``) and returns the first matching
template name.  Rendering is context-driven (D2): templates receive a
plain context dict (``node``) plus the pack's render helpers as
globals; they never touch models or backends.

All rendered text is normalized (per-line rstrip, ≤2 consecutive blank
lines, single trailing newline) so output is byte-stable regardless of
template whitespace — the snapshot goldens pin the exact bytes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from codegraph.codegen import signature

#: D11 kind-alias table — cross-node-type spelling aliases.
KIND_ALIASES: dict[str, str] = {
    "enum_value": "enumvalue",
}

#: Per-node-type kind aliases — normalize non-canonical spellings to the
#: pack's per-type vocabulary.  The design pipeline emits MethodNode
#: kind="method" / AttributeNode kind="attribute"; the doxygen as-built
#: export uses the raw doxygen memberdef kinds (kind="function" for
#: methods, kind="variable" for attributes) — without these aliases every
#: as-built member falls through to default.j2 and renders as an
#: "unsupported" TODO stub.
KIND_ALIASES_BY_TYPE: dict[str, dict[str, str]] = {
    "MethodNode": {"function": "method"},
    "FunctionNode": {"method": "function"},  # defensive symmetry
    "AttributeNode": {"variable": "attribute"},
}

#: Node types that never get a per-type template directory — the pack
#: renders them via ``_skipped.j2`` (or omits them entirely).  Includes
#: declared-skip scaffolding types + abstract bases (dispatched by kind).
PACK_SKIPPED: frozenset[str] = frozenset({
    # declared skips (mirror context/ skip modules)
    "LiteralNode",
    "TestFixtureNode",
    "HLR", "LLR",
    "Component", "Dependency", "Language", "ProjectMeta",
    # abstract bases — resolved by concrete subclass directory
    "CompoundNode", "MemberNode",
})

_MAX_BLANK_LINES = 1

#: clang-format's MaxEmptyLinesToKeep — the canonical boundary for as-built
#: files: source blank runs up to this width survive canonical formatting, so
#: as-built normalization must not cap them tighter than the formatter does.
_MAX_BLANK_LINES_AS_BUILT = 2


def _normalize(text: str, *, max_blank_lines: int = _MAX_BLANK_LINES) -> str:
    """Deterministic output normalization (snapshot-stable bytes)."""
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank > max_blank_lines:
                continue
        else:
            blank = 0
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def builtin_pack_dir(language: str = "cpp") -> Path:
    """Absolute path of the builtin pack's template directory."""
    import importlib.resources

    ref = importlib.resources.files("codegraph.codegen")
    return Path(ref.joinpath("templates", language))


class TemplatePack:
    """A language pack: template resolution + rendering.

    Attributes:
        language: Canonical language key (``"cpp"``).
        directory: Pack root (defaults to the builtin
            ``codegen/templates/<language>``).
        emit_markers: When True, render ``// @codegraph uid:…`` provenance
            markers above each declaration (R7).  Default False — the
            markers are a provenance side-channel, not required for
            round-trip verification (verify() compares graph uids), and
            they break byte-fidelity with hand-written source.
    """

    def __init__(
        self,
        language: str = "cpp",
        directory: str | Path | None = None,
        *,
        emit_markers: bool = False,
        as_built: bool = False,
    ) -> None:
        self.language = language
        self.directory = (
            Path(directory).resolve() if directory else builtin_pack_dir(language)
        )
        if not self.directory.is_dir():
            raise FileNotFoundError(f"template pack not found: {self.directory}")
        self.emit_markers = emit_markers
        # As-built reconstruction preserves source blank runs up to
        # clang-format's MaxEmptyLinesToKeep (2); synthesized output is
        # capped to one blank line for byte-stable snapshots.
        self.as_built = as_built
        self._environment: Environment | None = None

    @property
    def _max_blank_lines(self) -> int:
        return _MAX_BLANK_LINES_AS_BUILT if self.as_built else _MAX_BLANK_LINES

    # ── Environment ────────────────────────────────────────────────

    @property
    def environment(self) -> Environment:
        if self._environment is None:
            self._environment = self._make_environment()
        return self._environment

    def _make_environment(self) -> Environment:
        env = Environment(
            loader=FileSystemLoader(str(self.directory)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )
        env.filters["indent"] = _indent_filter
        env.filters["guard"] = signature.compute_guard
        env.filters["wrap_lines"] = _wrap_lines_filter
        env.globals["pack"] = self
        env.globals["render_node"] = self.render_node
        env.globals["render_namespace"] = self.render_namespace
        env.globals["render_document"] = self.render_document
        env.globals["render_source_units"] = self.render_source_units
        return env

    # ── Resolution ─────────────────────────────────────────────────

    def resolve(
        self,
        node_type: str,
        kind: str = "",
        *,
        variant: str | None = None,
    ) -> str:
        """Resolve the template name for *node_type* + *kind*.

        Order: ``<NodeType>/<kind>.j2`` → ``<NodeType>/<kind>_<variant>.j2``
        → ``<NodeType>/default.j2`` → pack ``default.j2``.  Raises
        ``FileNotFoundError`` when nothing matches (an explicit error,
        never silent output).
        """
        kind = KIND_ALIASES.get(kind, kind) or ""
        kind = KIND_ALIASES_BY_TYPE.get(node_type, {}).get(kind, kind) or ""
        candidates: list[str] = []
        if kind:
            if variant:
                candidates.append(f"{node_type}/{kind}_{variant}.j2")
            else:
                candidates.append(f"{node_type}/{kind}.j2")
                # Declaration is the default render form: method_decl.j2,
                # attribute.j2, etc. (kind files such as method.j2 may not
                # exist — the decl/defn pair is the builtin convention).
                candidates.append(f"{node_type}/{kind}_decl.j2")
        if variant:
            candidates.append(f"{node_type}/default_{variant}.j2")
        candidates.append(f"{node_type}/default.j2")
        candidates.append("default.j2")
        for candidate in candidates:
            if (self.directory / candidate).is_file():
                return candidate
        raise FileNotFoundError(
            f"no template for {node_type} kind={kind!r} variant={variant!r} "
            f"in {self.directory}"
        )

    # ── Rendering ──────────────────────────────────────────────────

    def render_node(self, ctx: dict, *, indent: int = 0, variant: str | None = None) -> str:
        """Render one context dict through its resolved template.

        *variant* picks decl/defn templates (``MethodNode/method_defn.j2``)
        used by the source file template.
        """
        node_type = ctx.get("type", "")
        if not node_type:
            return ""
        template_name = self.resolve(node_type, ctx.get("kind", ""), variant=variant)
        text = self.environment.get_template(template_name).render(
            node=ctx, pack=self
        )
        if indent:
            text = textwrap.indent(text, " " * indent)
        if ctx.get("body_inline"):
            # Verbatim in-class body: the text is source, not template
            # output — normalization would cap the source's intentional
            # blank lines (e.g. two blank lines before a return).
            return text.rstrip("\n")
        return _normalize(text, max_blank_lines=self._max_blank_lines).rstrip("\n")

    def render_namespace(
        self,
        ns: dict,
        *,
        indent: int = 0,
        leading_blank_lines: int = 0,
        trailing_blank_lines: int = 0,
    ) -> str:
        """Render one namespace block (open, blocks, nested, close).

        Uses the NamespaceNode/namespace_open.j2 + namespace_close.j2
        templates; blocks are rendered via per-type dispatch.

        SourceFragmentNode blocks are verbatim source: their text carries
        its own line endings (including intentional trailing blank lines),
        so they are concatenated raw rather than normalized and joined — a
        fragment's trailing blank line is layout, not noise.
        """
        name = ns.get("name", "")
        env = self.environment
        open_text = env.get_template("NamespaceNode/namespace_open.j2").render(
            node={"name": name}, pack=self
        ).rstrip()
        close_text = env.get_template("NamespaceNode/namespace_close.j2").render(
            node={"name": name}, pack=self
        ).strip()
        pad = " " * indent
        parts: list[str] = []
        parts.append(textwrap.indent(open_text, pad))
        parts.extend("" for _ in range(leading_blank_lines))
        blocks = ns.get("blocks", [])
        prev_end = 0
        for index, block in enumerate(blocks):
            if block.get("type") == "SourceFragmentNode":
                text = block.get("text", "") or ""
                # Defer exactly one final newline to the join: the fragment's
                # internal line endings (including intentional trailing blank
                # lines) are preserved, and the join supplies the boundary
                # newline to the next part (namespace close or next block).
                if text.endswith("\n"):
                    text = text[:-1]
                parts.append(text)
                prev_end = int(block.get("end_line", 0) or 0)
            else:
                start = int(block.get("start_line", 0) or 0)
                # Blank line separators between adjacent structured blocks
                # are derived from the indexed span gap (clang-format keeps
                # up to MaxEmptyLinesToKeep=2; fragments carry their own
                # spacing and are never double-counted here).
                gap = start - prev_end if prev_end else 0
                if prev_end and gap > 1:
                    parts.extend("" for _ in range(min(gap - 1, 2)))
                # Structured parts defer their newline to the join exactly
                # like fragments (no double newline between adjacent parts).
                # A block may carry its own render variant (e.g. out-of-line
                # definitions render via their ``_defn`` template).
                parts.append(self.render_node(
                    block,
                    indent=indent + 4,
                    variant=block.get("variant"),
                ))
                prev_end = int(block.get("end_line", 0) or 0)
        for child in ns.get("namespaces", []):
            parts.append(self.render_namespace(child, indent=indent + 4))
        parts.extend("" for _ in range(trailing_blank_lines))
        parts.append(textwrap.indent(close_text, pad))
        return "\n".join(parts)

    def render_document(self, ctx: dict, *, indent: int = 0) -> str:
        """Render a FileContext's namespaces + top-level blocks (header)."""
        if ctx.get("layout"):
            return self.render_layout(ctx.get("layout"), indent=indent)
        parts: list[str] = []
        namespaces = ctx.get("namespaces", [])
        for index, ns in enumerate(namespaces):
            # File-level layout applies only to the top-level namespace in
            # an as-built file; nested namespaces retain their own structure.
            parts.append(self.render_namespace(
                ns,
                indent=indent,
                leading_blank_lines=(
                    int(ctx.get("namespace_leading_blank_lines", 0))
                    if index == 0 else 0
                ),
                trailing_blank_lines=(
                    int(ctx.get("namespace_trailing_blank_lines", 0))
                    if index == len(namespaces) - 1 else 0
                ),
            ))
        for block in ctx.get("blocks", []):
            parts.append(self.render_node(block, indent=indent))
        return "\n".join(parts)

    def render_layout(self, items: list, *, indent: int = 0) -> str:
        """Render a source-ordered file body layout (complex as-built files).

        Items are emitted in line order; blank-line gaps between consecutive
        items are derived from their source positions (clang-format keeps up
        to MaxEmptyLinesToKeep=2, so wider source gaps are capped).  Namespace
        regions render through ``render_namespace`` with their per-region
        blank layout; residuals are verbatim (one trailing newline deferred
        to the join); mid-file includes render at their source position.
        """
        parts: list[str] = []
        prev_line = 0
        for item in items:
            line = int(item.get("line") or item.get("start_line") or 0)
            gap = (line - prev_line - 1) if prev_line else 0
            if 0 < gap <= 2:
                parts.extend("" for _ in range(gap))
            elif gap > 2:
                parts.extend("" for _ in range(2))
            if item.get("kind") == "region":
                parts.append(self.render_namespace(
                    item,
                    indent=indent,
                    leading_blank_lines=int(item.get("leading_blank_lines") or 0),
                    trailing_blank_lines=int(item.get("trailing_blank_lines") or 0),
                ))
                prev_line = int(item.get("close_line") or 0)
            elif item.get("kind") == "residual":
                text = (item.get("ctx") or {}).get("text", "") or ""
                if text.endswith("\n"):
                    text = text[:-1]
                parts.append(text)
                prev_line = int(item.get("end_line") or 0)
            elif item.get("kind") == "include":
                parts.append(f'#include {item.get("spelling", "")}')
                prev_line = line
        return "\n".join(parts)

    def render_source_units(self, ctx: dict, *, indent: int = 0) -> str:
        """Render out-of-line definitions for body-carrying members (.cpp).

        Walks namespaces → compounds → sections → members with
        ``has_body`` and renders each via its ``_defn`` template variant.
        The implementation export's bodies (``source_bodies`` — grouped
        by top-level namespace) render first, verbatim (the body text
        carries its own ``Class::method`` signature).
        """
        parts: list[str] = []

        def render_source_body(ns: dict, pad: int) -> None:
            if not ns.get("bodies"):
                return
            env = self.environment
            open_text = env.get_template("NamespaceNode/namespace_open.j2").render(
                node={"name": ns["name"]}, pack=self
            ).rstrip()
            close_text = env.get_template("NamespaceNode/namespace_close.j2").render(
                node={"name": ns["name"]}, pack=self
            ).strip()
            parts.append(textwrap.indent(open_text, " " * pad))
            for _ in range(int(ctx.get("namespace_leading_blank_lines", 0))):
                parts.append("")
            for index, body in enumerate(ns["bodies"]):
                # Keep one blank line between out-of-line definitions.
                # clang-format preserves this separation but does not create
                # it for us; the final body directly precedes namespace close.
                parts.append(
                    self.render_node(body, indent=pad + 4, variant="defn")
                    + ("\n" if index < len(ns["bodies"]) - 1 else "")
                )
            for _ in range(int(ctx.get("namespace_trailing_blank_lines", 0))):
                parts.append("")
            parts.append(textwrap.indent(close_text, " " * pad))

        for ns in ctx.get("source_bodies", []):
            render_source_body(ns, indent)

        def walk_compound(compound_ctx: dict, pad: int) -> None:
            for section in compound_ctx.get("sections", []):
                for member in section.get("members", []):
                    if not member.get("has_body"):
                        continue
                    parts.append(self.render_node(member, indent=pad, variant="defn"))

        def walk_namespace(ns: dict, pad: int) -> None:
            for block in ns.get("blocks", []):
                if block.get("type") in _COMPOUND_CTX_TYPES:
                    walk_compound(block, pad)
            for child in ns.get("namespaces", []):
                walk_namespace(child, pad)

        for ns in ctx.get("namespaces", []):
            walk_namespace(ns, indent)
        for block in ctx.get("blocks", []):
            if block.get("type") in _COMPOUND_CTX_TYPES:
                walk_compound(block, indent)
        # A top-level namespace with no body content at all (an empty
        # ``.cpp`` namespace shell, or a file whose classes only declare)
        # still renders its open/close with the indexed blank layout — an
        # empty namespace region is layout, not noise.  Files with
        # implementation-export bodies already render their wrappers via
        # ``source_bodies`` and must not get a second shell.
        if not ctx.get("source_bodies"):
            for ns in ctx.get("namespaces", []):
                if _namespace_has_defns(ns):
                    continue
                parts.append(self.render_namespace(
                    ns,
                    indent=indent,
                    leading_blank_lines=int(ctx.get("namespace_leading_blank_lines", 0)),
                    trailing_blank_lines=int(ctx.get("namespace_trailing_blank_lines", 0)),
                ))
        return "\n".join(parts)

    def render_file(self, ctx: dict, *, kind: str | None = None) -> str:
        """Render a full FileContext to normalized file text.

        *kind* defaults to the context's own ``kind`` (``"header"`` or
        ``"source"``), set by the planner.
        """
        kind = kind or ctx.get("kind", "header")
        template_name = {
            "header": "file_header.j2",
            "source": "file_source.j2",
            "test": "file_test.j2",
        }.get(kind, "file_header.j2")
        text = self.environment.get_template(template_name).render(node=ctx, pack=self)
        # Synthesized output is capped to a single blank run for byte-stable
        # snapshots.  As-built reconstruction preserves what clang-format
        # would keep (MaxEmptyLinesToKeep) so source blank layout survives.
        text = _normalize(text, max_blank_lines=self._max_blank_lines)
        # ``_normalize`` intentionally caps arbitrary blank runs for stable
        # synthesized output.  Restore only the indexed top-level namespace
        # spacing that an as-built file explicitly records (runs wider than
        # the as-built cap survive for as-built files already).
        trailing = int(ctx.get("namespace_trailing_blank_lines", 0))
        namespaces = ctx.get("namespaces", [])
        cap = self._max_blank_lines
        if trailing > cap and namespaces:
            name = namespaces[-1].get("name", "")
            close = f"}} // namespace {name}" if name else "}"
            prefix = "\n" * (cap + 1)
            replacement = "\n" * (trailing + 1)
            position = text.rfind(prefix + close)
            if position >= 0:
                text = text[:position] + replacement + text[position + len(prefix):]
        return text


#: Context ``type`` values that carry sections (class-like compounds).
_COMPOUND_CTX_TYPES = frozenset({
    "ClassNode", "InterfaceNode", "UnionNode", "CompoundNode",
})


def _namespace_has_defns(ns: dict) -> bool:
    """True when *ns* (or a nested namespace) contains any body-carrying
    member that renders as an out-of-line definition."""
    for block in ns.get("blocks", []):
        if block.get("type") not in _COMPOUND_CTX_TYPES:
            continue
        for section in block.get("sections", []):
            if any(m.get("has_body") for m in section.get("members", [])):
                return True
    return any(_namespace_has_defns(child) for child in ns.get("namespaces", []))


def _indent_filter(text: str, width: int = 4) -> str:
    """Jinja filter: indent a block by *width* spaces."""
    if not text:
        return text
    return textwrap.indent(text, " " * width)


def _wrap_lines_filter(text: str, width: int = 78) -> list[str]:
    """Jinja filter: wrap *text* into lines no wider than *width*.

    Used by doc blocks so long detailed descriptions (which the parser
    flattens into one run-on string) render as readable wrapped ``///``
    lines instead of 500-char monster lines.  Existing newlines are
    preserved; blank lines survive.
    """
    if not text:
        return []
    out: list[str] = []
    for para in text.splitlines():
        if not para.strip():
            out.append("")
            continue
        for line in textwrap.wrap(para, width=width, break_long_words=True):
            out.append(line)
    return out


__all__ = [
    "TemplatePack",
    "KIND_ALIASES",
    "KIND_ALIASES_BY_TYPE",
    "PACK_SKIPPED",
    "builtin_pack_dir",
]
