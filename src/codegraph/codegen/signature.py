"""Signature reconciliation + include-guard computation (R3).

Phase 1 v1 rendering is passthrough of stored strings (D4), but the
context contract still needs a *minimal declarator parser*:

1. detect which encoding a ``type_signature`` uses:
   - **full declaration** (design, committed fixture; spec D8):
     ``"virtual int getVersion() const = 0"`` — contains ``(`` or starts
     with a qualifier;
   - **split** (as-built, and the regenerated design fixture):
     ``type_signature`` = return type only, ``argsstring`` = params +
     trailing qualifiers;
2. split a declaration into ``SignatureParts`` (return_type, name,
   params, qualifiers) for the member context contract;
3. derive the out-of-line ``Type::`` definition for ``.cpp`` files
   (as-built ``definition + argsstring`` with the ``Scope::`` prefix
   stripped, then re-prefixed with the *actual* file nesting context);
4. compute include guards from a file path.

Contract: strings are authoritative, flags are hints (D8).  Templates
render ``declaration`` — never ``return_type + " " + name``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignatureParts:
    """Decomposed C++ declaration.

    Attributes:
        return_type: Return type text (``""`` for ctors/dtors/operators).
        name: Function/member name.
        params: ``[{"name", "type", "default"}]`` — parsed from the
            argsstring (R6), position-ordered.
        qualifiers: Trailing qualifiers (``const``, ``override``,
            ``noexcept``, ``= 0``, ``= default``, …) in original order.
        body_hint: ``True`` when the declaration indicates a body exists
            (``= default``, ``= delete``, ``{}``).
        raw: The original declaration text.
    """

    return_type: str = ""
    name: str = ""
    params: list[dict] = field(default_factory=list)
    qualifiers: str = ""
    body_hint: bool = False
    raw: str = ""


def is_full_declaration(type_signature: str) -> bool:
    """True when *type_signature* is a complete declaration (R3 rule 1).

    Full-declaration encoding: contains ``(`` (a parameter list) or
    starts with a leading qualifier (``virtual``, ``explicit``,
    ``static``, ``constexpr``, ``inline``, ``template``).
    """
    raise NotImplementedError("is_full_declaration: Phase 1 render slice")


def split_declaration(text: str) -> SignatureParts:
    """Decompose a C++ declaration string into SignatureParts.

    Test matrix (pinned by ``tests/codegen/test_signature.py``):
    ``'virtual int getVersion() const = 0'``,
    ``'MigrationResult apply()'``,
    ``'MigrationManager(cpp_sqlite::Database& db)'``,
    ``'~Migration() = default'``, ``'operator=='``,
    as-built ``'() const override'``-style argsstrings, and the degraded
    ctor argstring ``'MigrationManager(Database &db)'``.
    """
    raise NotImplementedError("split_declaration: Phase 1 render slice")


def split_argsstring(argsstring: str) -> list[dict]:
    """Split an argsstring param list into ``[{"name", "type", "default"}]``.

    Top-level comma split honoring parens/brackets/angle brackets and
    default values (R6).  Empty or degraded argsstrings yield ``[]``.
    """
    raise NotImplementedError("split_argsstring: Phase 1 render slice")


def reconstruct_declaration(
    type_signature: str, name: str, argsstring: str, *, flags=None
) -> str:
    """Reconstruct a declaration from split encoding (R3 rule 2).

    ``type_signature + " " + name + argsstring``, with flag-driven
    qualifiers (``is_virtual`` → ``virtual``, …) prepended **only when**
    ``argsstring`` doesn't already carry them.
    """
    raise NotImplementedError("reconstruct_declaration: Phase 1 render slice")


def out_of_line_definition(
    definition: str, argsstring: str, scope_prefix: str
) -> str:
    """Derive a ``.cpp`` definition from as-built ``definition + argsstring``.

    Strips the ``Scope::`` prefix baked into *definition* (avoiding
    double-scoping against the file's namespace nesting) and re-prefixes
    with *scope_prefix* (the actual nesting context the file template
    uses).  R3 rule 3.
    """
    raise NotImplementedError("out_of_line_definition: Phase 1 render slice")


def compute_guard(path: str) -> str:
    """Include guard from a file path.

    ``"include/cpp_sqlite/DataAccessObject.hpp"`` →
    ``"INCLUDE_CPP_SQLITE_DATAACCESSOBJECT_HPP"`` (uppercase, non-alnum
    → ``_``; the spec's FileContext contract example).
    """
    raise NotImplementedError("compute_guard: Phase 1 render slice")


__all__ = [
    "SignatureParts",
    "is_full_declaration",
    "split_declaration",
    "split_argsstring",
    "reconstruct_declaration",
    "out_of_line_definition",
    "compute_guard",
]
