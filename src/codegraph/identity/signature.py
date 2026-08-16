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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codegraph.uid import normalize_argsstring, _split_top_level

__all__ = [
    "CallableSignature",
    "build_callable_signature",
    "canonical_signature",
    "is_conversion_operator",
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


def _normalize_type_spacing(text: str) -> str:
    """Collapse a type to its canonical spelling.

    Doxygen emits template types with spacing artifacts
    (``std::shared_ptr< spdlog::logger >``).  Canonical identity treats
    these as the same type, so whitespace runs collapse to one space and
    template brackets hug their contents (``<``/``>`` lose surrounding
    spaces; nested ``> >`` merges to ``>>``).  This is the identity
    module's own contract — it deliberately does not depend on the
    codegen helpers.
    """
    s = _WS_RUN.sub(" ", text).strip()
    s = re.sub(r"\s*<\s*", "<", s)
    s = re.sub(r"\s*>\s*", ">", s)
    s = s.replace("> >", ">>")
    return s

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
