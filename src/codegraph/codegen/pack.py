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


def _normalize(text: str) -> str:
    """Deterministic output normalization (snapshot-stable bytes)."""
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank > _MAX_BLANK_LINES:
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
    ) -> None:
        self.language = language
        self.directory = (
            Path(directory).resolve() if directory else builtin_pack_dir(language)
        )
        if not self.directory.is_dir():
            raise FileNotFoundError(f"template pack not found: {self.directory}")
        self.emit_markers = emit_markers
        self._environment: Environment | None = None

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
        return _normalize(text).rstrip("\n")

    def render_namespace(self, ns: dict, *, indent: int = 0) -> str:
        """Render one namespace block (open, blocks, nested, close).

        Uses the NamespaceNode/namespace_open.j2 + namespace_close.j2
        templates; blocks are rendered via per-type dispatch.
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
        lines = [textwrap.indent(open_text, pad)]
        for block in ns.get("blocks", []):
            lines.append(self.render_node(block, indent=indent + 4))
        for child in ns.get("namespaces", []):
            lines.append(self.render_namespace(child, indent=indent + 4))
        lines.append(textwrap.indent(close_text, pad))
        return "\n".join(lines)

    def render_document(self, ctx: dict, *, indent: int = 0) -> str:
        """Render a FileContext's namespaces + top-level blocks (header)."""
        parts: list[str] = []
        for ns in ctx.get("namespaces", []):
            parts.append(self.render_namespace(ns, indent=indent))
        for block in ctx.get("blocks", []):
            parts.append(self.render_node(block, indent=indent))
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
        return _normalize(text)


#: Context ``type`` values that carry sections (class-like compounds).
_COMPOUND_CTX_TYPES = frozenset({
    "ClassNode", "InterfaceNode", "UnionNode", "CompoundNode",
})


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
