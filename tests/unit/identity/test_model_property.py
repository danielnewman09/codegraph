"""Work Package 2.1 — the model ``canonical_key`` property.

- ``canonical_key`` is a declared, immutable, indexed property on every
  persistable node, kept beside the legacy ``uid``;
- new nodes under an active identity scope compute both fields at save;
- legacy/unscoped nodes keep an empty ``canonical_key`` — reading never
  invents a scope or silently writes a key;
- ``primary_key()`` returns the canonical key when present, else uid;
- ``legacy_uid`` is the neutral name for the legacy identifier;
- ``_uid_value()`` remains only as a compatibility shim;
- ``update()`` rejects ``canonical_key`` mutation;
- the active scope is a ContextVar (concurrent indexing safety).
"""

from __future__ import annotations

import threading

import pytest

from codegraph.identity import (
    IdentityError,
    IdentityScope,
    identity_scope,
)
from codegraph.identity.context import get_identity_scope, set_identity_scope
from codegraph.models import ClassNode, NamespaceNode, ParameterNode

SCOPE = IdentityScope.repository("codegraph-suite", "codegraph")
REPO_SCOPE = IdentityScope.repository("codegraph-suite", "codegraph")


class TestCanonicalKeyProperty:
    def test_declared_on_base(self) -> None:
        from codegraph.models.descriptors import Property, PropertyRegistry

        prop = PropertyRegistry.properties_of(ClassNode)["canonical_key"]
        assert isinstance(prop, Property)
        assert prop.index is True

    def test_unscoped_save_raises(self) -> None:
        """WP A: canonical identity is mandatory — saving without a
        scope raises IdentityError instead of persisting an empty key."""
        node = ClassNode(name="Widget", qualified_name="app::Widget", source="test")
        set_identity_scope(None)
        from codegraph.identity import IdentityError

        with pytest.raises(IdentityError, match="no canonical key"):
            node.save()

    def test_parent_relative_save_without_context_raises(self) -> None:
        """Parent-relative children are keyed by explicit parent context,
        never invented at save."""
        from codegraph.models import ParameterNode

        param = ParameterNode(name="x", qualified_name="f(int)", position=0,
                              member_refid="r1", type="int", source="test")
        with identity_scope(SCOPE):
            from codegraph.identity import IdentityError

            with pytest.raises(IdentityError, match="parent-relative"):
                param.save()

    def test_scoped_save_computes_both_fields(self) -> None:
        node = ClassNode(name="Widget", qualified_name="app::Widget", source="test")
        with identity_scope(SCOPE):
            node.save()
        assert node.canonical_key.startswith("cg:v1:repository:codegraph-suite%2Fcodegraph:class:")
        assert node.canonical_key == node.primary_key()

    def test_key_is_deterministic_across_saves(self) -> None:
        with identity_scope(SCOPE):
            a = ClassNode(name="W", qualified_name="app::W", source="test").save()
            b = ClassNode(name="W", qualified_name="app::W", source="test").save()
        assert a.canonical_key == b.canonical_key

    def test_design_and_as_built_nodes_share_key(self) -> None:
        with identity_scope(SCOPE):
            design = ClassNode(name="M", qualified_name="app::M",
                               source="design", tags=["design"]).save()
            as_built = ClassNode(name="M", qualified_name="app::M",
                                 source="app", tags=["as-built"]).save()
        assert design.canonical_key == as_built.canonical_key


class TestPrimaryKey:
    def test_primary_key_is_canonical_key(self) -> None:
        with identity_scope(SCOPE):
            node = ClassNode(name="W", qualified_name="app::W", source="t").save()
        assert node.primary_key() == node.canonical_key

    def test_primary_key_empty_without_scope(self) -> None:
        """WP A: one meaning — the primary key is the canonical key; an
        unscoped node simply has none (no uid fallback)."""
        set_identity_scope(None)
        node = ClassNode(name="W", qualified_name="app::W", source="t")
        assert node.canonical_key == ""
        assert node.primary_key() == ""


class TestResolveCanonicalKey:
    def test_explicit_scope(self) -> None:
        node = ClassNode(name="W", qualified_name="app::W", source="t")
        assert node.resolve_canonical_key(SCOPE) == (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:class:"
            "qualified_name=app%3A%3AW"
        )
        assert node.canonical_key == ""  # never stored by the explicit path

    def test_active_scope_default(self) -> None:
        node = ClassNode(name="W", qualified_name="app::W", source="t")
        with identity_scope(SCOPE):
            assert node.resolve_canonical_key() == node.resolve_canonical_key(SCOPE)

    def test_no_scope_raises(self) -> None:
        set_identity_scope(None)
        node = ClassNode(name="W", qualified_name="app::W", source="t")
        with pytest.raises(IdentityError, match="no identity scope"):
            node.resolve_canonical_key()

    def test_parent_relative_child_needs_parents(self) -> None:
        p = ParameterNode(name="id", position=0, member_refid="m",
                          type_signature="int", source="t")
        with pytest.raises(IdentityError, match="requires a parent"):
            p.resolve_canonical_key(SCOPE)
        from codegraph.models import MethodNode

        parent = MethodNode(name="f", qualified_name="app::f",
                            argsstring="()", type_signature="void", source="t")
        key = p.resolve_canonical_key(SCOPE, parents={"parent_callable_key": parent})
        assert "parameter" in key


class TestImmutability:
    def test_update_rejects_canonical_key(self) -> None:
        with identity_scope(SCOPE):
            node = ClassNode(name="W", qualified_name="app::W", source="t").save()
        with pytest.raises(ValueError, match="canonical_key"):
            node.update(canonical_key="forged")

    def test_direct_assignment_not_blocked_but_flagged(self) -> None:
        # Direct assignment is a property write (allowed at construction);
        # the guard is the update() identity-immutability contract.
        node = ClassNode(name="W", qualified_name="app::W", source="t")
        node.canonical_key = "explicit"
        assert node.canonical_key == "explicit"


class TestScopeContext:
    def test_contextvar_isolation_across_threads(self) -> None:
        results: list[tuple[int, str]] = []

        def worker(index: int) -> None:
            set_identity_scope(IdentityScope.repository("proj", f"repo-{index}"))
            n = NamespaceNode(name=f"ns{index}", qualified_name="app::ns", source="x")
            n._ensure_canonical_key()
            results.append((index, n.canonical_key))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len({key for _, key in results}) == 4

    def test_nested_scope_restores_previous(self) -> None:
        outer = IdentityScope.repository("p", "a")
        inner = IdentityScope.repository("p", "b")
        with identity_scope(outer):
            assert get_identity_scope() == outer
            with identity_scope(inner):
                assert get_identity_scope() == inner
            assert get_identity_scope() == outer
        assert get_identity_scope() is None

    def test_clear_scope(self) -> None:
        with identity_scope(SCOPE):
            set_identity_scope(None)
            assert get_identity_scope() is None
