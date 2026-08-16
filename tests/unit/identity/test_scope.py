"""Work Package 1.2 — IdentityScope value object tests.

The scope must reject empty, relative, path-derived, or unstable scope
IDs, and repository scope must be the pair (project_id, repository_id).
"""

from __future__ import annotations

import pytest

from codegraph.identity.scope import (
    ECOSYSTEM,
    PROJECT,
    REPOSITORY,
    IdentityScope,
    IdentityScopeError,
)


class TestScopeValidation:
    @pytest.mark.parametrize(
        "scope_kind, scope_id",
        [
            ("project", ""),
            ("repository", ""),
            ("ecosystem", ""),
            ("project", "   "),
            ("project", "\t"),
            ("project", " leading"),
            ("project", "trailing "),
            ("project", "/abs/path"),
            ("project", "trailing/"),
            ("project", "./relative"),
            ("project", "a/../b"),
            ("project", "."),
            ("project", ".."),
            ("project", "proj/."),
            ("project", "proj/.."),
            ("project", "proj/../other"),
            ("project", "\x00nul"),
            ("project", "!!!"),  # no alphanumerics
        ],
    )
    def test_rejects_invalid(self, scope_kind: str, scope_id: str) -> None:
        with pytest.raises(IdentityScopeError):
            IdentityScope(scope_kind, scope_id)

    def test_rejects_unknown_scope_kind(self) -> None:
        with pytest.raises(IdentityScopeError, match="unknown scope kind"):
            IdentityScope("galaxy", "proj")

    def test_rejects_non_string_scope_id(self) -> None:
        with pytest.raises(IdentityScopeError, match="must be a str"):
            IdentityScope("project", 42)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "scope_kind, scope_id",
        [
            ("project", "codegraph-suite"),
            ("repository", "codegraph-suite/codegraph"),
            ("ecosystem", "cppreference"),
            ("project", "codegraph-suite-2.0"),
        ],
    )
    def test_accepts_valid(self, scope_kind: str, scope_id: str) -> None:
        scope = IdentityScope(scope_kind, scope_id)
        assert scope.scope_kind == scope_kind
        assert scope.scope_id == scope_id


class TestScopeFactories:
    def test_project_factory(self) -> None:
        scope = IdentityScope.project("codegraph-suite")
        assert scope.scope_kind == PROJECT
        assert scope.scope_id == "codegraph-suite"
        assert scope.project_id == "codegraph-suite"
        assert scope.repository_id is None

    def test_repository_factory_pairs_ids(self) -> None:
        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        assert scope.scope_kind == REPOSITORY
        assert scope.scope_id == "codegraph-suite/codegraph"
        assert scope.project_id == "codegraph-suite"
        assert scope.repository_id == "codegraph"

    def test_repository_factory_rejects_empty_components(self) -> None:
        with pytest.raises(IdentityScopeError):
            IdentityScope.repository("", "codegraph")
        with pytest.raises(IdentityScopeError):
            IdentityScope.repository("codegraph-suite", "")

    def test_ecosystem_allowed(self) -> None:
        scope = IdentityScope(ECOSYSTEM, "cppreference")
        assert scope.scope_kind == ECOSYSTEM


class TestScopeProtocol:
    def test_equality_and_hash(self) -> None:
        a = IdentityScope.repository("codegraph-suite", "codegraph")
        b = IdentityScope.repository("codegraph-suite", "codegraph")
        c = IdentityScope.repository("codegraph-suite", "codegraph-mcp")
        assert a == b
        assert hash(a) == hash(b)
        assert a != c
        assert len({a, b, c}) == 2

    def test_scope_id_must_be_canonical_spelling(self) -> None:
        # Leading/trailing whitespace is an unstable spelling — rejected.
        with pytest.raises(IdentityScopeError, match="whitespace"):
            IdentityScope("project", " proj ")
