"""Canonical callable signatures for identity computation.

The Priority 1 typed model carries the raw callable surface
(``argsstring``, ``type_signature``, ``is_static``, ``is_const``,
``template_declarations``, ...).  This module turns that surface into a
*single canonical serialized form* used by the ``canonical_signature``
identity field — one authoritative contract, independent of
``normalize_argsstring``'s uid-hash-only role.

Identity-relevant (encoded in the canonical form):

- parameter *types* without parameter names or default values;
- ordered template parameters and constraints;
- method cv-qualifiers (``const``/``volatile``) and ref-qualifiers
  (``&``/``&&``) and ``noexcept`` identity semantics;
- static versus instance callable distinction;
- constructor / destructor / operator / conversion roles;
- variadic parameter lists;
- language identifier (canonicalization rules differ per language).

Not identity-relevant (kept as structured metadata only, never in the
canonical string): ``virtual``, ``explicit``, ``constexpr``,
``override``, ``final``, and ``= 0``/``= default``/``= delete`` suffixes
— none of these change which callable an overload set distinguishes.

The canonical form is a flat string so it can be percent-encoded into a
``cg:v1`` key field like any other identity value::

    lang:cpp|template:[ValidTransferObject T]|(T&)|const|noexcept|...

Ordering is fixed and deterministic.

TODO: This should be generalized - not hard-coded as cpp-specific stuff
      in this repository. for example, doxygen-index should have much of 
      the same logic.
      
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Argsstring normalisation (moved from codegraph.uid in the
# canonical-only cutover; the identity module owns its signature
# contract and never imports a uid module).
# ── Argsstring normalisation ────────────────────────────────────────────

# C++ type keywords — when the last token of a parameter declaration is
# one of these, it is part of the *type*, not a parameter name, and must
# not be stripped.
_CPP_TYPE_KEYWORDS: frozenset[str] = frozenset({
    "int", "char", "short", "long", "float", "double", "void", "bool",
    "unsigned", "signed", "auto", "wchar_t", "char16_t", "char32_t",
    "const", "volatile", "struct", "class", "enum", "union",
})

# Python implicit parameters that carry no type information.
_PY_DROP_PARAMS: frozenset[str] = frozenset({"self", "cls"})


def _split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split *s* on *sep* at the top nesting level only.

    Respects ``<>``, ``()``, ``[]`` and ``{}`` nesting so that template
    arguments (``vector<int, string>``) and function-pointer params are
    not split prematurely.

    Args:
        s: The string to split.
        sep: The separator character (default ``","``).

    Returns:
        A list of substrings.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _strip_cpp_param_name(param: str) -> str:
    """Strip the trailing parameter name from a C++ parameter declaration.

    Retains the full type including pointers (``*``), references (``&``),
    and qualifiers (``const``, ``volatile``).  Strips the parameter's
    *name* and any default value (``= ...``).

    Examples::
        "int a"             → "int"
        "const std::string& name" → "const std::string&"
        "Engine* engine"    → "Engine*"
        "unsigned int"      → "unsigned int"  (no name to strip)
        "int a = 0"         → "int"

    If the param appears to have no name (just a type), it is returned
    unchanged.
    """
    param = param.strip()
    if not param:
        return ""

    # Strip default value: everything after the first top-level '='
    eq_parts = _split_top_level(param, "=")
    param = eq_parts[0].strip()
    if not param:
        return ""

    # If the whole param IS a type keyword, keep it.
    if param in _CPP_TYPE_KEYWORDS:
        return param

    # Strip trailing array brackets: "int [10]" → "int"
    param = re.sub(r"\s*\[\s*\d*\s*\]\s*$", "", param).strip()
    if not param:
        return ""

    # Strip trailing param name: an identifier preceded by whitespace
    # or * / &.  The identifier must NOT be a type keyword.
    #
    # The separator group captures the whitespace and/or pointer-ref
    # operators between the type and the name.  We extract the * / &
    # from it (they belong to the type) and discard the whitespace.
    m = re.match(r"^(.+?)(\s+|\s*[\*&]+\s*)([a-zA-Z_]\w*)\s*$", param)
    if m and m.group(3) not in _CPP_TYPE_KEYWORDS:
        type_part = m.group(1).rstrip()
        separator = m.group(2)
        ptr_ref = "".join(c for c in separator if c in "*&")
        if ptr_ref:
            return type_part + ptr_ref if type_part else ptr_ref
        return type_part

    return param


def _normalize_py_param(param: str) -> str:
    """Strip a Python parameter to its type annotation.

    Drops ``self``/``cls`` entirely.  For annotated parameters
    (``name: type``), returns the type.  For unannotated parameters,
    returns ``"Any"`` as a placeholder — the caller is expected to
    enforce type annotations, but the normaliser degrades gracefully.

    Examples::
        "self"               → ""   (dropped)
        "cls"                → ""   (dropped)
        "a: int"             → "int"
        "b: str"             → "str"
        "engine: Engine"     → "Engine"
        "x: float = 0.0"     → "float"
        "unannotated"        → "Any"
    """
    param = param.strip()
    if not param:
        return ""

    # Strip default value
    eq_parts = _split_top_level(param, "=")
    param = eq_parts[0].strip()

    # Drop self/cls
    base = param.split(":")[0].strip()
    if base in _PY_DROP_PARAMS:
        return ""

    # Split on first top-level ':' to separate name from annotation
    colon_parts = _split_top_level(param, ":")
    if len(colon_parts) >= 2:
        return colon_parts[1].strip()

    # No annotation → placeholder (enforcement is a loader concern)
    return "Any"


def normalize_argsstring(argsstring: str) -> str:
    """Normalise an argsstring to a canonical, type-only signature.

    Parameter *names* are stripped; *types* are retained including C++
    pointers (``*``), references (``&``), and qualifiers (``const``),
    and Python type annotations.  Default values are removed.

    Handles both C++ (Doxygen) and Python syntaxes heuristically: if a
    parameter contains ``:`` (Python annotation syntax), it is treated
    as Python; otherwise C++.

    Examples::

        # C++
        "(int a, int b)"                  → "(int,int)"
        "(const std::string& name)"       → "(const std::string&)"
        "(Engine* engine, int count)"     → "(Engine*,int)"
        "()"                              → "()"

        # Python
        "(self, a: int, b: str)"          → "(int,str)"
        "(cls, x: float)"                 → "(float)"
        "(a: Engine, b: int = 0)"          → "(Engine,int)"

    Args:
        argsstring: The raw argsstring from the source (Doxygen, Sphinx,
            etc.).

    Returns:
        The normalised signature string, e.g. ``"(int,int)"``.
    """
    inner = argsstring.strip()

    # Strip outer parentheses
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()
    elif inner.startswith("("):
        inner = inner[1:].strip()

    if not inner:
        return "()"

    # Detect Python vs C++: Python annotations use a single ':' (not '::').
    # C++ qualified names contain '::' (double colon).  A single colon
    # not part of '::', or the presence of 'self'/'cls', indicates Python.
    is_python = bool(re.search(r"(?<!:):(?!:)", inner)) or bool(
        re.search(r"\b(self|cls)\b", inner)
    )

    raw_params = _split_top_level(inner, ",")

    normalised_parts: list[str] = []
    for raw in raw_params:
        raw = raw.strip()
        if not raw:
            continue
        if is_python:
            n = _normalize_py_param(raw)
        else:
            n = _strip_cpp_param_name(raw)
        if n:
            normalised_parts.append(n)

    return "(" + ",".join(normalised_parts) + ")"


__all__ = [
    "CallableSignature",
    "build_callable_signature",
    "canonical_signature",
    "is_conversion_operator",
    "normalize_type_spacing",
]

#: Canonical emission order for trailing callable qualifiers.
_QUALIFIER_ORDER = {
    "volatile": 0,
    "const": 1,
    "&": 2,
    "&&": 3,
    "noexcept": 4,
}

_WS_RUN = re.compile(r"\s+")


def normalize_type_spacing(text: str) -> str:
    """Collapse a type to its canonical spelling.

    Doxygen emits template types with spacing artifacts
    (``std::shared_ptr< spdlog::logger >``, ``Database &``).  Canonical
    identity treats these as the same type, so whitespace runs collapse
    to one space, template brackets hug their contents (``<``/``>``
    lose surrounding spaces; nested ``> >`` merges to ``>>``), and
    pointer/ref symbols hug the preceding token (``X &`` → ``X&``,
    ``X *`` → ``X*``, ``X &&`` → ``X&&``).  This is the identity
    module's own contract — it deliberately does not depend on the
    codegen helpers (WP1.3) and is the shared contract for consumers
    such as the codegen fixpoint comparator (WP5.4).
    """
    s = _WS_RUN.sub(" ", text).strip()
    s = re.sub(r"\s*<\s*", "<", s)
    s = re.sub(r"\s*>\s*", ">", s)
    s = s.replace("> >", ">>")
    s = re.sub(r"\s+([&*])", r"\1", s)
    return s


_normalize_type_spacing = normalize_type_spacing

#: Trailing tokens that participate in overload identity.
_IDENTITY_TRAILING = frozenset(_QUALIFIER_ORDER)

#: Trailing tokens that are source decoration, not identity.
_NON_IDENTITY_TRAILING = frozenset(
    {"override", "final", "=0", "=default", "=delete"}
)

_TEMPLATE_KEYWORDS = ("typename ", "class ")


def _split_argsstring(argsstring: str) -> tuple[str, str]:
    """Split an argsstring into ``(param_list, trailing)``.

    The param list is the text between the first top-level ``(`` and its
    matching ``)``; ``trailing`` is everything after that closing paren.
    Returns ``("", "")`` when there is no paren group.
    """
    args = argsstring.strip()
    if not args or not args.startswith("("):
        # Degenerate spelling with no parens (e.g. a bare name): the
        # whole thing is a param list with no qualifiers.
        return args, ""
    depth = 0
    for i, ch in enumerate(args):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return args[1:i], args[i + 1 :].strip()
    # Unbalanced — treat the whole string as a param list; the caller's
    # normalizer degrades gracefully.
    return args, ""


def _canonical_trailing(trailing: str) -> tuple[str, ...]:
    """Extract identity-relevant trailing qualifiers in canonical order.

    Accepts source spellings like ``const noexcept &``, ``& const``,
    ``noexcept``, ``= 0``, ``override``; emits only identity tokens in
    fixed order: ``volatile``, ``const``, ``&``, ``&&``, ``noexcept``.
    """
    tokens: list[str] = []
    for tok in trailing.split():
        tok = tok.replace(" ", "")
        if tok in _NON_IDENTITY_TRAILING or tok == "=":
            continue
        if tok in _IDENTITY_TRAILING:
            tokens.append(tok)
        # Any other token (e.g. throw(...) text, attribute spellings) is
        # dropped — it is source decoration, not overload identity.
    return tuple(sorted(set(tokens), key=lambda t: _QUALIFIER_ORDER[t]))


def _normalize_template_decl(decl: str) -> str:
    """Normalize one template-parameter declaration.

    ``typename``/``class`` keywords are interchangeable and stripped;
    the constraint and the parameter name are retained, so
    ``ValidTransferObject T`` stays distinct from ``T``.
    """
    d = decl.strip()
    for kw in _TEMPLATE_KEYWORDS:
        if d.startswith(kw):
            d = d[len(kw) :].strip()
            break
    return d


def is_conversion_operator(name: str) -> bool:
    """True when *name* is a conversion operator (``operator bool``)."""
    return name.startswith("operator ") or name == "operator"


def _role_of(node: object, name: str) -> str:
    """Classify a callable's role from its name and qualified name."""
    if name.startswith("~"):
        return "destructor"
    if name.startswith("operator"):
        return "conversion" if is_conversion_operator(name) else "operator"
    qn = str(getattr(node, "qualified_name", "") or "")
    base = qn.split("(", 1)[0].strip()
    segments = [s for s in base.split("::") if s]
    if len(segments) >= 2 and segments[-1] == name and segments[-2] == name:
        return "constructor"
    return ""


@dataclass(frozen=True)
class CallableSignature:
    """Structured canonical callable identity.

    Attributes:
        language: Language identifier (``cpp``, ``python``).  Included
            in the canonical form because canonicalization rules differ.
        parameters: Type-only parameter list, names and defaults
            stripped (C++ pointer/ref/qualifiers retained).
        template_parameters: Ordered normalized template declarations
            with constraints.
        qualifiers: Canonical-ordered cv/ref/noexcept qualifiers.
        static: Whether this is a static (instance-independent) callable.
        role: ``""``, ``constructor``, ``destructor``, ``operator``,
            or ``conversion``.
        variadic: Whether the parameter list is variadic (``...``).
    """

    language: str = "cpp"
    parameters: tuple[str, ...] = ()
    template_parameters: tuple[str, ...] = ()
    qualifiers: tuple[str, ...] = ()
    static: bool = False
    role: str = ""
    variadic: bool = False

    def canonical(self) -> str:
        """Return the single canonical serialized form."""
        parts = [f"lang:{self.language}"]
        if self.role:
            parts.append(self.role)
        if self.static:
            parts.append("static")
        if self.template_parameters:
            parts.append(
                "template:[" + ",".join(self.template_parameters) + "]"
            )
        parts.append("(" + ",".join(self.parameters) + ")")
        if self.qualifiers:
            parts.append(";".join(self.qualifiers))
        if self.variadic:
            parts.append("...")
        return "|".join(parts)

    def __str__(self) -> str:
        return self.canonical()


def build_callable_signature(
    node: object, *, language: str = "cpp"
) -> CallableSignature:
    """Build a :class:`CallableSignature` from a MethodNode/FunctionNode.

    The node's own fields are the only input — no backend query, so
    signatures can be computed before relationships are persisted.
    """
    argsstring = str(getattr(node, "argsstring", "") or "")
    param_list, trailing = _split_argsstring(argsstring)

    variadic = "..." in param_list
    if param_list.strip():
        normalized = normalize_argsstring(f"({param_list})")
        inner = normalized[1:-1] if normalized.startswith("(") else normalized
        parameters = tuple(
            _normalize_type_spacing(p)
            for p in _split_top_level(inner)
            if p.strip()
        ) if inner else ()
    else:
        parameters = ()

    raw_templates = getattr(node, "template_declarations", None) or []
    template_parameters = tuple(
        _normalize_template_decl(d) for d in raw_templates if str(d).strip()
    )

    name = str(getattr(node, "name", "") or "")

    return CallableSignature(
        language=language,
        parameters=parameters,
        template_parameters=template_parameters,
        qualifiers=_canonical_trailing(trailing),
        static=bool(getattr(node, "is_static", False)),
        role=_role_of(node, name),
        variadic=variadic,
    )


def canonical_signature(node: object, *, language: str = "cpp") -> str:
    """Identity provider: the canonical serialized signature of a node.

    This is the function registered as the ``canonical_signature``
    computed identity field.
    """
    return build_callable_signature(node, language=language).canonical()
