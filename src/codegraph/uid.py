"""Deterministic unique-id computation for codegraph nodes.

Computes a content-derived SHA-1 hash from each node's identity fields,
so that the same logical symbol in different codebases produces the same
``uid`` — enabling cross-codebase edge resolution without translation
tables or name-matching heuristics.

Identity input per node type (declared via ``_identity_fields``):
    - Functions / methods: ``qualified_name`` + normalised ``argsstring``
      (parameter names stripped, types/pointers/references retained).
    - Classes / interfaces / enums / unions / concepts / modules /
      namespaces / enum-values / attributes / defines: ``qualified_name``
      alone.
    - Files: ``path`` (canonical file path).
    - Parameters: ``member_refid`` + ``position``.
    - Implementations: ``qualified_name`` (matches the parent member's
      ``qualified_name``).
    - Literals: ``qualified_name`` (e.g. ``"literal::30"``).

The hash is stored in the ``uid`` ``UniqueIdProperty`` column on every
node, set automatically by the ``CodeGraphNode.save()`` hook.  Callers
never need to compute or pass ``uid`` — it is derived in the background
from fields the caller already provides.
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["compute_uid", "normalize_argsstring"]

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


# ── UID computation ─────────────────────────────────────────────────────


def compute_uid(*parts: str) -> str:
    """Compute a deterministic SHA-1 hash from identity-field values.

    Joins the parts with a NUL byte separator (which cannot appear in
    code identifiers) to prevent concatenation collisions, then returns
    the 40-character hex digest.

    The *first* part is the primary identity field (e.g.
    ``qualified_name``, ``path``, ``member_refid``).  If it is empty,
    returns an empty string — signalling the caller to fall back to the
    auto-generated random ``uid``.  This prevents collisions between
    nodes that were constructed without a proper identity (e.g. in
    tests).

    Args:
        *parts: The identity field values in declared order.  The first
            part is the primary identity and must be non-empty.

    Returns:
        A 40-character hex string, or ``""`` if the first part is empty.
    """
    if not parts or not parts[0]:
        return ""
    input_str = "\x00".join(parts)
    return hashlib.sha1(input_str.encode("utf-8")).hexdigest()