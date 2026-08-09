"""Signature reconciliation + include-guard computation (R3).

Phase 1 v1 rendering is passthrough of stored strings (D4), but the
context contract still needs a *minimal declarator parser*:

1. detect which encoding a ``type_signature`` uses:
   - **full declaration** (design, committed fixture; spec D8):
     ``"virtual int getVersion() const = 0"`` — contains ``(`` or starts
     with a leading specifier; this also covers the pipeline copy's
     degraded variant ``"int getVersion() const"`` (declaration minus
     leading qualifiers / pure-virtual markers);
   - **return-type-only** (doxygen-dependency-parser working tree):
     ``type_signature`` = return type only, ``argsstring`` = params +
     trailing qualifiers;
2. split a declaration into ``SignatureParts`` (leading, return_type,
   name, params, qualifiers) for the member context contract;
3. derive the out-of-line ``Type::`` definition for ``.cpp`` files
   (as-built ``definition + argsstring`` with the ``Scope::`` prefix
   stripped, then re-prefixed with the *actual* file nesting context);
4. compute include guards from a file path.

Contract: strings are authoritative, flags are hints (D8).  Templates
render ``declaration`` — never ``return_type + " " + name``.

Phase 1 limitations (documented, Phase 2 TypeRef territory): function
pointer return types (``void (*)(int)``), array parameters
(``int arr[10]``), and ``<``/``=`` operators inside default-value
expressions are not parsed structurally — the splitter degrades to
whole-segment passthrough rather than emitting wrong output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Leading specifiers that unambiguously open a declaration (never part
#: of a return type).  ``const`` is deliberately excluded — ``const int``
#: is a return type, not a leading specifier.
_LEADING_SPECIFIERS = frozenset({
    "virtual", "explicit", "static", "constexpr", "consteval",
    "constinit", "inline", "friend", "thread_local", "mutable",
})

_OPERATOR_RE = re.compile(r"\boperator\b")

#: Leading flag → keyword (D8: flags are hints; only applied when the
#: string doesn't already carry the keyword).
_LEADING_FLAG_KEYWORDS: dict[str, str] = {
    "is_virtual": "virtual",
    "is_static": "static",
    "is_constexpr": "constexpr",
    "is_explicit": "explicit",
    "is_inline": "inline",
}

_BODY_MARKER_RE = re.compile(r"=\s*(0|default|delete)\b|\{[^}]*\}")


@dataclass
class SignatureParts:
    """Decomposed C++ declaration.

    Attributes:
        leading: Leading specifiers in original order (``"virtual"``,
            ``"explicit MigrationManager"``-style prefixes); ``""`` when
            none.  Structured so the context builder can derive member
            flags from strings (D8: stored flags are unreliable).
        return_type: Return type text (``""`` for ctors/dtors/operators).
        name: Function/member name.
        params: ``[{"name", "type", "default"}]`` — parsed from the
            parameter list (R6), position-ordered.
        qualifiers: Trailing qualifiers (``const``, ``override``,
            ``noexcept``, ``= 0``, ``= default``, …) in original order.
        body_hint: True when the declaration ends with a self-contained
            definition marker (``= 0`` pure virtual, ``= default``,
            ``= delete``, or ``{ ... }``) — such members must never be
            emitted as out-of-line ``.cpp`` definitions.
        raw: The original declaration text.
    """

    leading: str = ""
    return_type: str = ""
    name: str = ""
    params: list[dict] = field(default_factory=list)
    qualifiers: str = ""
    body_hint: bool = False
    raw: str = ""


def is_full_declaration(type_signature: str) -> bool:
    """True when *type_signature* is a complete declaration (R3 rule 1).

    Full-declaration encoding: contains ``(`` (a parameter list) or
    starts with a leading specifier (``virtual``, ``explicit``, …).
    """
    ts = type_signature.strip()
    if not ts:
        return False
    if "(" in ts:
        return True
    first = ts.split(maxsplit=1)[0]
    return first in _LEADING_SPECIFIERS


def _strip_leading_specifiers(text: str) -> tuple[str, str]:
    """Split leading specifiers from the rest of a declaration.

    Returns ``(leading, rest)`` — e.g. ``("virtual", "int getVersion() const = 0")``.
    """
    leading: list[str] = []
    rest = text.strip()
    while True:
        match = re.match(r"^([A-Za-z_]\w*)\s+", rest)
        if not match or match.group(1) not in _LEADING_SPECIFIERS:
            break
        leading.append(match.group(1))
        rest = rest[match.end():]
    return " ".join(leading), rest.strip()


def _find_parens(text: str) -> tuple[int, int] | None:
    """Locate the first top-level parameter list ``(`` … ``)``.

    Tracks parens, angle brackets, and square brackets so a ``(`` inside
    template args or array bounds is not mistaken for the parameter
    list.  Returns ``(open_index, close_index)`` or ``None``.
    """
    depth = angle = square = 0
    open_index: int | None = None
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0 and angle == 0 and square == 0:
                open_index = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and angle == 0 and square == 0:
                return open_index, i  # type: ignore[return-value]
        elif ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
    return None


def _split_name_and_return_type(before: str) -> tuple[str, str]:
    """Split ``before`` (text preceding the param list) into name + return type.

    Special-cases operators (``bool operator==`` → name ``operator==``);
    otherwise the last whitespace token is the name.  ``before`` may be
    empty (bare ``(args)`` string) → both empty.
    """
    before = before.strip()
    if not before:
        return "", ""
    op = _OPERATOR_RE.search(before)
    if op:
        return before[op.start():].strip(), before[:op.start()].strip()
    tokens = before.split()
    return tokens[-1], " ".join(tokens[:-1])


def split_declaration(text: str) -> SignatureParts:
    """Decompose a C++ declaration string into SignatureParts.

    Handles the full matrix: full declarations (with and without leading
    specifiers), ctors/dtors/operators, pure-virtual ``= 0`` /
    ``= default`` markers, degraded as-built argsstrings (``() const
    override``), and declarations with no parameter list at all
    (``operator==``).
    """
    raw = text.strip()
    parts = SignatureParts(raw=raw)
    if not raw:
        return parts

    leading, rest = _strip_leading_specifiers(raw)
    parts.leading = leading

    parens = _find_parens(rest)
    if parens is None:
        # No parameter list: a bare operator or a type-only string.
        name, return_type = _split_name_and_return_type(rest)
        parts.name, parts.return_type = name, return_type
        return parts

    open_index, close_index = parens
    name, return_type = _split_name_and_return_type(rest[:open_index])
    parts.name, parts.return_type = name, return_type
    parts.params = split_argsstring(rest[open_index + 1:close_index])
    parts.qualifiers = rest[close_index + 1:].strip()
    parts.body_hint = bool(_BODY_MARKER_RE.search(parts.qualifiers))
    return parts


def split_argsstring(argsstring: str) -> list[dict]:
    """Split an argsstring param list into ``[{"name", "type", "default"}]``.

    Accepts ``"(int x, double y=1.0)"``, ``"(std::unique_ptr<Migration>)"``
    (no names — degraded), ``"()"`` / ``""`` (empty), and even a bare
    param list without parens (degraded ctor argstrings such as
    ``"Database &db"``).  Comma splitting honors parens / angle brackets
    / square brackets so nested templates survive.
    """
    s = argsstring.strip()
    if not s:
        return []
    parens = _find_parens(s)
    if parens is not None and parens[0] == 0:
        # Leading paren: the param list is the inner content; trailing
        # qualifiers ("() const override") are dropped.
        inner = s[parens[0] + 1:parens[1]]
    else:
        # Degraded bare param list without parens ("Database &db").
        inner = s.lstrip("(")
    if not inner.strip():
        return []
    return [_parse_param(segment) for segment in _split_top_level(inner)]


def _split_top_level(text: str) -> list[str]:
    """Split on top-level commas, honoring (), <>, and [] nesting."""
    parts: list[str] = []
    depth = angle = square = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
        elif ch == "," and depth == 0 and angle == 0 and square == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def _find_top_level_eq(segment: str) -> int | None:
    """Index of the first top-level ``=`` (default-value separator)."""
    depth = angle = square = 0
    for i, ch in enumerate(segment):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
        elif ch == "=" and depth == 0 and angle == 0 and square == 0:
            return i
    return None


def _parse_param(segment: str) -> dict:
    """Parse one param segment into ``{"name", "type", "default"}``.

    Phase 1 name/type split preserves the original spacing (``Database &
    database`` → type ``"Database &"``):

    - a trailing pure identifier (``pLogger``) or ref/ptr-prefixed
      identifier (``&db``) separated by whitespace is the name;
    - anything else (``Transaction&``, ``const char*``, ``int arr[10]``)
      degrades to ``name=""``, whole segment as type.
    """
    seg = re.sub(r"\s+", " ", segment.strip())
    if not seg:
        return {"type": "", "name": "", "default": ""}

    default = ""
    eq = _find_top_level_eq(seg)
    if eq is not None:
        default = seg[eq + 1:].strip()
        seg = seg[:eq].strip()

    # The trailing identifier is the NAME iff a type precedes it
    # (``Database &database`` → name ``database``, type ``Database &``;
    # ``Transaction&`` / ``bool`` → no name).  Preserves original spacing.
    name_match = re.search(r"([A-Za-z_]\w*)$", seg)
    if name_match:
        type_candidate = seg[:name_match.start()].rstrip()
        if type_candidate:
            return {
                "type": type_candidate,
                "name": name_match.group(1),
                "default": default,
            }
    return {"type": seg, "name": "", "default": default}


def reconstruct_declaration(
    type_signature: str, name: str, argsstring: str, *, flags: dict | None = None
) -> str:
    """Reconstruct a declaration from return-type-only encoding (R3 rule 2).

    ``type_signature + " " + name + "(params)"`` with flag-driven
    qualifiers (``is_virtual`` → ``virtual``, ``is_const`` → trailing
    ``const``, …) applied **only when** the argsstring doesn't already
    carry the keyword (strings authoritative, flags hints — D8).

    Degraded argsstrings without parens (``"Database &db"``) are
    wrapped: ``MigrationManager(Database &db)``.
    """
    ts = type_signature.strip()
    name = name.strip()
    args = argsstring.strip()

    if args.startswith("("):
        signature = f"{name}{args}"
    elif args:
        signature = f"{name}({args})"
    else:
        signature = f"{name}()"

    leading = [
        keyword
        for field, keyword in _LEADING_FLAG_KEYWORDS.items()
        if flags and flags.get(field) and keyword not in signature
    ]
    if flags and flags.get("is_const") and "const" not in signature:
        signature = f"{signature} const"

    return " ".join(part for part in [*leading, ts, signature] if part)


def out_of_line_definition(
    definition: str, argsstring: str, scope_prefix: str
) -> str:
    """Derive a ``.cpp`` definition from as-built ``definition + argsstring``.

    Strips *scope_prefix* (the namespace path the file template re-opens)
    from the fully-scoped *definition* to avoid double-scoping, then
    appends the argsstring.  The prefix may appear after the return type
    (``"bool cpp_sqlite::DataAccessObject< T >::isInitialized"``) — the
    **last** occurrence is stripped so return types that share the prefix
    survive (``"cpp_sqlite::Result cpp_sqlite::Foo::get()"`` keeps the
    return type).  A space is inserted only when the argsstring lacks a
    leading ``(``.

    Example: ``"bool cpp_sqlite::DataAccessObject< T >::isInitialized"``
    with scope ``"cpp_sqlite::"`` →
    ``"bool DataAccessObject< T >::isInitialized() const override"``.
    """
    defn = definition.strip()
    prefix = scope_prefix.strip()
    if prefix:
        last = defn.rfind(prefix)
        if last != -1:
            defn = defn[:last] + defn[last + len(prefix):]
    defn = defn.strip()
    args = argsstring.strip()
    if not args:
        return defn
    if args.startswith("("):
        return f"{defn}{args}"
    return f"{defn} {args}"


def compute_guard(path: str) -> str:
    """Include guard from a file path.

    ``"include/cpp_sqlite/DataAccessObject.hpp"`` →
    ``"INCLUDE_CPP_SQLITE_DATAACCESSOBJECT_HPP"`` — uppercase, runs of
    non-alphanumerics collapse to a single ``_``.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", path.strip()).strip("_")
    return cleaned.upper()


__all__ = [
    "SignatureParts",
    "is_full_declaration",
    "split_declaration",
    "split_argsstring",
    "reconstruct_declaration",
    "out_of_line_definition",
    "compute_guard",
]
