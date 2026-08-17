"""Active identity-scope resolution for the model layer.

Canonical keys need a resolved scope (fixed architectural decision 3:
scope is never inferred from filesystem, database path, parser name, or
tag).  This module provides the in-process mechanism by which an
indexing run (or a library consumer) declares the scope under which
nodes compute their canonical keys::

    from codegraph.identity.context import identity_scope, get_identity_scope

    with identity_scope(IdentityScope.repository("codegraph-suite", "codegraph")):
        node.save()          # node.canonical_key is now computed at save

    scope = get_identity_scope()   # None outside any with-block

The scope is a :class:`contextvars.ContextVar` so concurrent indexing
workers (the parser's ThreadPoolExecutor) each see their own scope
without cross-talk.  A node saved with *no* active scope keeps an empty
``canonical_key`` — reading it never invents a scope or silently writes
a key (WP2.1 contract).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from codegraph.identity.scope import IdentityScope

__all__ = [
    "get_identity_scope",
    "identity_scope",
    "resolve_scope",
    "set_identity_scope",
]

#: The active identity scope for the current context (thread/task).
_scope_context: ContextVar[IdentityScope | None] = ContextVar(
    "identity_scope", default=None
)


def set_identity_scope(scope: IdentityScope | None) -> None:
    """Set the active identity scope for the current context.

    ``None`` clears it — nodes saved afterwards keep an empty
    ``canonical_key`` (they are not silently re-scoped).
    """
    _scope_context.set(scope)


def get_identity_scope() -> IdentityScope | None:
    """Return the active identity scope, or None outside a scope block."""
    return _scope_context.get()


def resolve_scope(explicit: IdentityScope | None = None) -> IdentityScope | None:
    """Resolve a scope: an explicit argument wins, else the active one."""
    if explicit is not None:
        return explicit
    return _scope_context.get()


@contextmanager
def identity_scope(scope: IdentityScope) -> Iterator[None]:
    """Run a block with *scope* as the active identity scope.

    Restores the previous scope on exit, so blocks can nest.
    """
    token = _scope_context.set(scope)
    try:
        yield
    finally:
        _scope_context.reset(token)
