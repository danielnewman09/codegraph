"""IdentityScope — the validated scope of a canonical identity.

Scope is a *fixed architectural decision* (decision 3 of the Priority 2
plan): every identity specification declares a scope kind —

- ``project``: artifacts owned by the logical project;
- ``repository``: artifacts belonging to one indexed repository;
- ``ecosystem``: globally shared external vocabulary, only where
  explicitly justified.

Repository scope is the pair ``(project_id, repository_id)`` spelled as
``project_id/repository_id``.  Project scope is just ``project_id``.

Scope is never inferred from a filesystem location, database path,
plugin installation path, parser name, or workflow tag.  The
authoritative source is ``.codegraph-project.toml``
(``[project].id`` + ``[[repositories]].name``); the factories here
accept already-resolved values so non-MCP callers pass the same explicit
scope.
"""

from __future__ import annotations

import re

__all__ = [
    "IdentityScope",
    "IdentityScopeError",
    "SCOPE_KINDS",
    "PROJECT",
    "REPOSITORY",
    "ECOSYSTEM",
]

PROJECT = "project"
REPOSITORY = "repository"
ECOSYSTEM = "ecosystem"

SCOPE_KINDS = frozenset({PROJECT, REPOSITORY, ECOSYSTEM})

#: Control characters and anything else that could destabilise an ID.
_INVALID_SCOPE_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class IdentityScopeError(ValueError):
    """Raised when a scope is empty, relative, path-derived, or unstable."""


class IdentityScope:
    """An immutable, validated (scope_kind, scope_id) pair.

    Attributes:
        scope_kind: One of ``project``, ``repository``, ``ecosystem``.
        scope_id: The stable scope identifier, e.g. ``codegraph-suite``
            (project) or ``codegraph-suite/codegraph`` (repository).
    """

    __slots__ = ("scope_kind", "scope_id")

    def __init__(self, scope_kind: str, scope_id: str) -> None:
        if scope_kind not in SCOPE_KINDS:
            raise IdentityScopeError(
                f"unknown scope kind {scope_kind!r}; expected one of "
                f"{sorted(SCOPE_KINDS)}"
            )
        if not isinstance(scope_id, str):
            raise IdentityScopeError(
                f"scope_id must be a str, got {type(scope_id).__name__}"
            )
        if scope_id != scope_id.strip():
            raise IdentityScopeError(
                f"scope_id must not have leading/trailing whitespace: {scope_id!r}"
            )
        scope_id = scope_id.strip()
        if not scope_id:
            raise IdentityScopeError("scope_id must not be empty")
        if _INVALID_SCOPE_CHARS.search(scope_id):
            raise IdentityScopeError(
                f"scope_id must not contain control characters: {scope_id!r}"
            )
        if scope_id.startswith("/") or scope_id.endswith("/"):
            raise IdentityScopeError(
                f"scope_id must not be an absolute or trailing-slash path: {scope_id!r}"
            )
        components = scope_id.split("/")
        if any(comp in (".", "..") for comp in components):
            raise IdentityScopeError(
                f"scope_id must not contain '.' or '..' components: {scope_id!r}"
            )
        if not any(ch.isalnum() for ch in scope_id):
            raise IdentityScopeError(
                f"scope_id must contain at least one alphanumeric character: {scope_id!r}"
            )
        self.scope_kind = scope_kind
        self.scope_id = scope_id

    # ── Factories ──────────────────────────────────────────────────

    @classmethod
    def project(cls, project_id: str) -> "IdentityScope":
        """Build a project scope from a resolved ``project.id``."""
        return cls(PROJECT, project_id)

    @classmethod
    def repository(
        cls, project_id: str, repository_id: str
    ) -> "IdentityScope":
        """Build a repository scope from resolved project + repository IDs.

        The resulting ``scope_id`` is ``project_id/repository_id`` — the
        pair is what makes a symbol unique across repositories that share
        qualified names.
        """
        if not project_id:
            raise IdentityScopeError("project_id must not be empty")
        if not repository_id:
            raise IdentityScopeError("repository_id must not be empty")
        return cls(REPOSITORY, f"{project_id}/{repository_id}")

    # ── Accessors ─────────────────────────────────────────────────

    @property
    def project_id(self) -> str | None:
        """The project portion of the scope, if expressible.

        For a repository scope this is the first path component.
        """
        if self.scope_kind == PROJECT:
            return self.scope_id
        if self.scope_kind == REPOSITORY and "/" in self.scope_id:
            return self.scope_id.split("/", 1)[0]
        return None

    @property
    def repository_id(self) -> str | None:
        """The repository portion of a repository scope, or None."""
        if self.scope_kind == REPOSITORY and "/" in self.scope_id:
            return self.scope_id.split("/", 1)[1]
        return None

    # ── Protocol support ──────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IdentityScope):
            return NotImplemented
        return (
            self.scope_kind == other.scope_kind and self.scope_id == other.scope_id
        )

    def __hash__(self) -> int:
        return hash((self.scope_kind, self.scope_id))

    def __repr__(self) -> str:
        return f"IdentityScope({self.scope_kind!r}, {self.scope_id!r})"
