"""TypeRef — structured C++ type rendering (Phase 2 fidelity).

Doxygen-index emits types with spacing artifacts that differ from
source style (``std::shared_ptr< spdlog::logger >``, ``Database &db``,
``decltype(& sqlite3_close )``).  ``normalize_declaration`` collapses
these deterministically — template brackets hug their contents, pointer/
reference markers attach to the type, ``>>`` merges — without ever
touching string/char literals, numbers, identifiers, or ``=`` defaults
(so ``pLogger=nullptr`` and ``"cpp_sqlite"`` survive byte-for-byte).

Applied to *reconstructed* as-built declarations (R3 rule 2/3) and
attribute types.  Full-declaration design members (R3 rule 1) are
emitted verbatim and never pass through here.

Token-based: the input is split into lexical tokens (strings,
identifiers, numbers, operators), then reassembled with C++ canonical
spacing rules.  All rules concern *where spaces go between tokens* —
token text is never altered.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(
    r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')   # string / char literal
    |(\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)        # number
    |(\b[A-Za-z_]\w*\b)                          # identifier / keyword
    |(::|->|&&|&|\*|~|=|,|<|>|\(|\)|\[|\]|\{|\}|;|:|\.\.\.)""",
    re.VERBOSE,
)

_KEYWORDS = frozenset({
    "const", "volatile", "unsigned", "signed", "long", "short",
    "struct", "class", "enum", "union", "typename", "constexpr",
    "static", "inline", "virtual", "explicit", "friend", "using",
    "typedef", "namespace", "template", "decltype", "noexcept",
    "override", "final", "mutable", "thread_local", "extern",
    "concept", "requires", "int", "float", "double", "char", "bool",
    "void", "auto", "nullptr", "true", "false",
})

#: Tokens after which an identifier attaches with no space.
_ATTACH = frozenset({"(", "[", "{", ",", ":", "...", "=", "->", "::"})


def _is_ident(tok: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_]\w*", tok or ""))


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for groups in _TOKEN_RE.findall(text):
        out.append(next(g for g in groups if g))
    return out


def scope_parts(qn: str) -> list[str]:
    """Split a qualified name on top-level ``::`` separators.

    Angle brackets are honored so template arguments containing ``::``
    survive: ``cpp_sqlite::IsVector< std::vector< T > >`` splits to
    ``['cpp_sqlite', 'IsVector< std::vector< T > >']`` — a naive
    ``qn.split("::")`` would mangle the template args into bogus
    namespace levels.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    i = 0
    while i < len(qn):
        ch = qn[i]
        if ch == "<":
            depth += 1
            buf.append(ch)
        elif ch == ">":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == ":" and depth == 0 and i + 1 < len(qn) and qn[i + 1] == ":":
            parts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p]


def normalize_declaration(text: str) -> str:
    """Return *text* with deterministic C++ spacing (token text unchanged)."""
    flat = _tokens(text)
    if not flat:
        return text.strip()

    out: list[str] = []
    angle_depth = 0
    last = ""  # last non-space token

    def attach_before() -> bool:
        return (
            last in _ATTACH
            or last in ("&", "&&", "*", ">", ">>", "~")
            or last.endswith(("::", "<"))
        )

    def push(tok: str) -> None:
        out.append(tok)

    for i, tok in enumerate(flat):
        nxt = flat[i + 1] if i + 1 < len(flat) else ""

        if tok == "<":
            angle_depth += 1
            push("<")  # template open always hugs the type
            last = "<"
        elif tok == ">":
            angle_depth = max(0, angle_depth - 1)
            if last == ">":
                out[-1] = ">>"  # merge nested closes: > > → >>
            else:
                push(">")
            last = out[-1]
            # space after a template close before a declarator name
            if angle_depth == 0 and _is_ident(nxt):
                push(" ")
        elif tok in ("&", "&&", "*"):
            # pointer/ref attaches to the type; space before a declarator
            # name (T& name) but not in an expression (decltype(&x))
            expr_ctx = last in ("(", ",", "<")
            push(tok)
            last = tok
            if _is_ident(nxt) and not expr_ctx:
                push(" ")
        elif tok == ",":
            push(",")
            last = ","
            if nxt:
                push(" ")
        elif tok in ("=", "->", ":"):
            push(tok)  # compact: x=y, x->y, init-list a:b
            last = tok
        elif tok == "::":
            push("::")
            last = "::"
        elif tok == "~":
            # destructor marker: hug the name that follows, but keep a
            # space from a preceding word (``virtual ~DAOBase``)
            if _is_ident(last) or last.endswith(("&", "*")):
                push(" ")
            push("~")
            last = "~"
        elif tok in ("(", "[", "{"):
            push(tok)  # always hugs: Foo(, arr[, id{0
            last = tok
        elif tok in (")", "]", "}"):
            push(tok)
            last = tok
        elif tok == ";":
            push(";")
            last = ";"
        elif tok == "...":
            push("...")
            last = "..."
        elif _is_ident(tok):
            if not attach_before():
                push(" ")
            push(tok)
            last = tok
        else:  # number / string literal
            if not attach_before() and last not in ("&", "&&", "*"):
                push(" ")
            push(tok)
            last = tok

    return "".join(out).strip()


def normalize_type(text: str) -> str:
    """Normalize a bare C++ type string (no declarator name)."""
    return normalize_declaration(text)


def free_template_vars(args: str) -> list[str]:
    """Derive the free (template) variables from a specialization's
    argument list, best-effort (Phase 2 — the graph carries no
    TEMPLATE_PARAM edges).

    ``< ForeignKey< T > >`` → ``["T"]``; ``< std::vector< T, Allocator > >``
    → ``["T", "Allocator"]``.  Identifiers that name templates (followed
    by ``<``), are scope-qualified (``std::``), or are keywords are
    excluded.  Constraints (``ValidTransferObject T``) are not derivable
    from the argument list — a documented degradation.
    """
    toks = _tokens(args)
    free: list[str] = []
    prev = ""
    for i, tok in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if not _is_ident(tok) or tok in _KEYWORDS or tok == "std":
            prev = tok
            continue
        if prev == "::" or nxt in ("::", "<"):
            prev = tok
            continue
        if tok not in free:
            free.append(tok)
        prev = tok
    return free
