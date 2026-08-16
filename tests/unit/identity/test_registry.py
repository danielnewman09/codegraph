"""Work Packages 0.1, 0.2 and 1.3 — identity registry audit, matrix,
resolution, and canonical signatures.

- the audit passes: every concrete registered type has exactly one
  identity spec, categories are unique, fields are declared, and
  intermediate types are exempt;
- the v1 identity matrix covers all 36 registered entries;
- keys are deterministic, transparent, versioned, reversible, strictly
  canonical, and collision-safe;
- canonical callable signatures keep overload sets distinct.
"""

from __future__ import annotations

import pytest

from codegraph.identity import (
    CanonicalIdentity,
    IdentityError,
    IdentityScope,
    audit_registry,
    resolve_identity_for,
    short_label,
    spec_for,
)
from codegraph.identity.encoding import KeyFormatError
from codegraph.identity.registry import (
    EXEMPT_ABSTRACT,
    _build_specs,
    computed_providers,
)
from codegraph.identity.scope import IdentityScopeError
from codegraph.identity.signature import (
    CallableSignature,
    build_callable_signature,
    canonical_signature,
)

# ══════════════════════════════════════════════════════════════════════════
# WP 0.1 — registry audit
# ══════════════════════════════════════════════════════════════════════════


class TestRegistryAudit:
    def test_audit_is_clean(self) -> None:
        problems = audit_registry()
        assert problems == [], "\n".join(problems)

    def test_all_36_registered_entries_covered(self) -> None:
        from codegraph.models.tags import CodeGraphNode

        # Import every model package (the audit does, but be explicit).
        import codegraph.models  # noqa: F401
        import codegraph_project.models  # noqa: F401
        import codegraph_memory.models  # noqa: F401
        import codegraph_requirements.models  # noqa: F401

        registered = {
            name: cls
            for name, cls in CodeGraphNode._registry.items()
            if cls.__module__.startswith("codegraph")
        }
        assert len(registered) == 36, sorted(registered)

        specs = _build_specs()
        concrete = set(registered) - set(EXEMPT_ABSTRACT)
        assert set(specs) == {registered[n] for n in concrete}

    def test_no_type_has_identity_without_spec_or_exemption(self) -> None:
        problems = audit_registry()
        assert not any("has no canonical identity spec" in p for p in problems)

    def test_intermediate_types_are_exempt_not_persistable(self) -> None:
        specs = _build_specs()
        assert EXEMPT_ABSTRACT == {"CompoundNode", "MemberNode", "MemoryNode"}
        from codegraph.models.tags import CodeGraphNode

        exempt_classes = {
            CodeGraphNode._registry[name] for name in EXEMPT_ABSTRACT
        }
        assert not (exempt_classes & set(specs))

    def test_every_spec_field_is_property_or_provider(self) -> None:
        problems = audit_registry()
        assert not any("neither a" in p for p in problems)

    def test_categories_are_unique_among_concrete_types(self) -> None:
        problems = audit_registry()
        assert not any("maps to both" in p for p in problems)


# ══════════════════════════════════════════════════════════════════════════
# WP 0.2 — identity matrix
# ══════════════════════════════════════════════════════════════════════════


class TestIdentityMatrix:
    """The v1 matrix, frozen.  Changes require a new key version."""

    def test_matrix_rows(self) -> None:
        specs = {s.model_type.__name__: s for s in _build_specs().values()}

        # Plan table rows (Work package 0.2 initial contracts).
        expected = {
            "ProjectMeta": ("project", ("singleton",)),
            "Component": ("project", ("qualified_name",)),
            "Dependency": ("project", ("manager_name", "qualified_name")),
            "Language": ("project", ("qualified_name", "version")),
            "NamespaceNode": ("repository", ("qualified_name",)),
            "ModuleNode": ("repository", ("qualified_name",)),
            "ClassNode": ("repository", ("qualified_name",)),
            "InterfaceNode": ("repository", ("qualified_name",)),
            "EnumNode": ("repository", ("qualified_name",)),
            "UnionNode": ("repository", ("qualified_name",)),
            "ConceptNode": ("repository", ("qualified_name",)),
            "MethodNode": ("repository", ("qualified_name", "canonical_signature")),
            "FunctionNode": ("repository", ("qualified_name", "canonical_signature")),
            "AttributeNode": ("repository", ("qualified_name",)),
            "EnumValueNode": ("repository", ("qualified_name",)),
            "DefineNode": ("repository", ("qualified_name",)),
            "FileNode": ("repository", ("normalized_repository_path",)),
            "ParameterNode": ("repository", ("parent_callable_key", "position")),
            "ImplementationNode": ("repository", ("parent_callable_key", "kind")),
            "SourceFragmentNode": ("repository", ("file_key", "start_line", "end_line")),
            "LiteralNode": ("repository", ("qualified_name",)),
            "TestNode": ("repository", ("parent_key", "qualified_name")),
            "TestFixtureNode": ("repository", ("parent_key", "qualified_name")),
            "TestStepNode": ("repository", ("parent_key", "qualified_name")),
            "AssertionNode": ("repository", ("parent_key", "qualified_name")),
            "HLR": ("project", ("qualified_name",)),
            "LLR": ("project", ("parent_hlr_key", "qualified_name")),
            "DecisionNode": ("project", ("qualified_name",)),
            "ConstraintNode": ("project", ("qualified_name",)),
            "RationaleNode": ("project", ("qualified_name",)),
            "AssumptionNode": ("project", ("qualified_name",)),
            "InsightNode": ("project", ("qualified_name",)),
            "TradeoffNode": ("project", ("qualified_name",)),
        }
        assert set(specs) == set(expected), (
            f"matrix drift: {sorted(set(specs) ^ set(expected))}"
        )
        for name, (scope_kind, fields) in expected.items():
            spec = specs[name]
            assert (spec.scope_kind, spec.fields) == (scope_kind, fields), name

    def test_categories_are_stable_names(self) -> None:
        for spec in _build_specs().values():
            assert not spec.category.endswith("Node")
            assert spec.category == spec.category.lower()
            assert " " not in spec.category and ":" not in spec.category

    def test_documentation_artifact_matches_registry(self) -> None:
        """The committed matrix doc regenerates from this registry.

        The doc (``docs/specs/2026-08-16-canonical-identity-matrix.md``)
        is generated by ``tools/generate_identity_matrix.py``; this test
        re-derives its table rows and compares, so the two cannot drift.
        """
        import re
        from pathlib import Path

        doc_path = (
            Path(__file__).resolve().parents[3]
            / "docs" / "specs" / "2026-08-16-canonical-identity-matrix.md"
        )
        if not doc_path.exists():
            pytest.fail("identity matrix doc missing — run tools/generate_identity_matrix.py")

        text = doc_path.read_text(encoding="utf-8")
        # Rows look like: | ClassNode | class | repository | qualified_name |
        rows = {}
        for match in re.finditer(
            r"^\|\s*`?(\w+)`?\s*\|\s*([a-z-]+)\s*\|\s*(project|repository|ecosystem)\s*\|\s*(.+?)\s*\|",
            text,
            re.MULTILINE,
        ):
            name, category, scope_kind, fields_raw = match.groups()
            fields = tuple(
                f.strip().strip("`") for f in fields_raw.split(",") if f.strip()
            )
            rows[name] = (category, scope_kind, fields)

        specs = {s.model_type.__name__: s for s in _build_specs().values()}
        assert rows == {
            name: (spec.category, spec.scope_kind, spec.fields)
            for name, spec in specs.items()
        }, "matrix doc out of sync — regenerate with tools/generate_identity_matrix.py"


# ══════════════════════════════════════════════════════════════════════════
# Resolution
# ══════════════════════════════════════════════════════════════════════════


class TestResolution:
    def test_class_identity(self) -> None:
        from codegraph.models import ClassNode

        node = ClassNode(name="LayerGraph", qualified_name="codegraph.graph.LayerGraph",
                         source="codegraph")
        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        ident = resolve_identity_for(node, scope)
        assert ident.category == "class"
        assert ident.key() == (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:class:"
            "qualified_name=codegraph.graph.LayerGraph"
        )

    def test_deterministic_and_reversible(self) -> None:
        from codegraph.models import ClassNode

        node = ClassNode(name="LayerGraph", qualified_name="codegraph.graph.LayerGraph",
                         source="codegraph")
        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        k1 = resolve_identity_for(node, scope).key()
        k2 = resolve_identity_for(node, scope).key()
        assert k1 == k2
        assert CanonicalIdentity.from_key(k1).key() == k1

    def test_design_and_as_built_share_logical_key(self) -> None:
        """Decision 1: same entity, different tags → same canonical key."""
        from codegraph.models import ClassNode

        design = ClassNode(name="MigrationManager",
                           qualified_name="cpp_sqlite::MigrationManager",
                           source="markdown-import", tags=["design"])
        as_built = ClassNode(name="MigrationManager",
                             qualified_name="cpp_sqlite::MigrationManager",
                             source="cpp-sqlite", tags=["as-built"])
        scope = IdentityScope.repository("cpp-suite", "cpp-sqlite")
        assert (
            resolve_identity_for(design, scope).key()
            == resolve_identity_for(as_built, scope).key()
        )

    def test_different_repositories_do_not_collide(self) -> None:
        from codegraph.models import ClassNode

        node = ClassNode(name="Widget", qualified_name="app::Widget", source="a")
        a = resolve_identity_for(node, IdentityScope.repository("p", "repo-a")).key()
        b = resolve_identity_for(node, IdentityScope.repository("p", "repo-b")).key()
        assert a != b

    def test_project_scope_for_memory_and_requirements(self) -> None:
        from codegraph_memory.models.decision import DecisionNode
        from codegraph_requirements.models.requirement import HLR

        scope = IdentityScope.project("codegraph-suite")
        decision = DecisionNode(name="db-choice", qualified_name="memory::db-choice",
                                source="codegraph", content="use sqlite")
        hlr = HLR(name="HLR-1", qualified_name="Architecture Diagram Generator",
                  source="codegraph")
        d = resolve_identity_for(decision, scope)
        h = resolve_identity_for(hlr, scope)
        assert d.category == "memory-decision"
        assert h.category == "requirement-hlr"
        assert d.scope.scope_kind == "project"
        assert h.scope.scope_kind == "project"
        assert d.scope.scope_id == "codegraph-suite"

    def test_type_without_spec_raises(self) -> None:
        class Unregistered:
            pass

        with pytest.raises(IdentityError, match="no canonical identity spec"):
            resolve_identity_for(Unregistered(), IdentityScope.project("p"))

    def test_parameter_requires_parent_context(self) -> None:
        from codegraph.models import ParameterNode

        node = ParameterNode(name="data", position=0, member_refid="m1",
                             type_signature="int", source="proj")
        scope = IdentityScope.repository("p", "repo")
        with pytest.raises(IdentityError, match="parent"):
            resolve_identity_for(node, scope)


# ══════════════════════════════════════════════════════════════════════════
# CanonicalIdentity strict decoding
# ══════════════════════════════════════════════════════════════════════════


class TestCanonicalIdentityDecode:
    def _key(self, *, category="class", fields=None, scope="proj/repo"):
        from codegraph.identity.encoding import encode_key

        return encode_key("repository", scope, category,
                          fields or [("qualified_name", "ns::Type")])

    def test_valid_key_decodes(self) -> None:
        ident = CanonicalIdentity.from_key(self._key())
        assert ident.category == "class"
        assert ident.values == (("qualified_name", "ns::Type"),)

    def test_unknown_category_rejected(self) -> None:
        with pytest.raises(IdentityError, match="unknown artifact category"):
            CanonicalIdentity.from_key(self._key(category="gadget"))

    def test_invalid_scope_kind_rejected(self) -> None:
        from codegraph.identity.encoding import encode_key

        key = encode_key("galaxy", "proj/repo", "class",
                         [("qualified_name", "ns::Type")])
        with pytest.raises(IdentityScopeError, match="unknown scope kind"):
            CanonicalIdentity.from_key(key)

    def test_reordered_fields_rejected(self) -> None:
        key = self._key(fields=[("qualified_name", "ns::Type")])
        reordered = key.replace("qualified_name=ns::Type", "qualified_name=ns::Type")
        # Build a genuinely reordered pair for a two-field category.
        from codegraph.identity.encoding import encode_key

        two = encode_key("project", "proj", "language",
                         [("version", "3.12"), ("qualified_name", "Python")])
        with pytest.raises(KeyFormatError, match="registered order"):
            CanonicalIdentity.from_key(two)
        assert reordered  # keep reference to avoid unused-var lint

    def test_extra_field_rejected(self) -> None:
        from codegraph.identity.encoding import encode_key

        key = encode_key("repository", "proj/repo", "class",
                         [("qualified_name", "ns::Type"), ("name", "Type")])
        with pytest.raises(KeyFormatError, match="registered order"):
            CanonicalIdentity.from_key(key)

    def test_missing_field_rejected(self) -> None:
        key = "cg:v1:repository:proj%2Frepo:class:"
        with pytest.raises(KeyFormatError):
            CanonicalIdentity.from_key(key)

    def test_short_label(self) -> None:
        ident = CanonicalIdentity.from_key(self._key())
        assert ident.short_label() == "class:ns::Type"
        assert short_label(ident) == "class:ns::Type"
        assert short_label("not-a-key") == "not-a-key"


# ══════════════════════════════════════════════════════════════════════════
# WP 1.3 — canonical callable signatures
# ══════════════════════════════════════════════════════════════════════════


def _method(**kwargs) -> object:
    from codegraph.models import MethodNode

    defaults = dict(name="run", qualified_name="ns::Widget::run",
                    argsstring="()", type_signature="void", source="proj")
    defaults.update(kwargs)
    return MethodNode(**defaults)


class TestCallableSignature:
    def test_params_normalized_types_only(self) -> None:
        sig = build_callable_signature(_method(
            argsstring="(int count, const std::string& name, Engine* engine)"
        ))
        assert sig.parameters == ("int", "const std::string&", "Engine*")
        assert sig.canonical().endswith("|(int,const std::string&,Engine*)")

    def test_defaults_stripped(self) -> None:
        sig = build_callable_signature(_method(
            argsstring="(int a = 0, std::shared_ptr< spdlog::logger > pLogger=nullptr)"
        ))
        assert sig.parameters == ("int", "std::shared_ptr<spdlog::logger>")

    def test_trailing_qualifiers_identity(self) -> None:
        base = build_callable_signature(_method(argsstring="()"))
        const = build_callable_signature(_method(argsstring="() const"))
        ref = build_callable_signature(_method(argsstring="() const &"))
        rref = build_callable_signature(_method(argsstring="() && noexcept"))
        assert const.qualifiers == ("const",)
        assert ref.qualifiers == ("const", "&")
        assert rref.qualifiers == ("&&", "noexcept")
        forms = {base.canonical(), const.canonical(), ref.canonical(), rref.canonical()}
        assert len(forms) == 4

    def test_qualifier_order_canonical_regardless_of_source_order(self) -> None:
        a = build_callable_signature(_method(argsstring="() & const noexcept"))
        b = build_callable_signature(_method(argsstring="() const noexcept &"))
        assert a.canonical() == b.canonical()
        assert a.qualifiers == ("const", "&", "noexcept")

    def test_override_final_pure_are_not_identity(self) -> None:
        a = build_callable_signature(_method(argsstring="() const override"))
        b = build_callable_signature(_method(argsstring="() const = 0"))
        c = build_callable_signature(_method(argsstring="() const"))
        assert a.canonical() == c.canonical()
        assert b.canonical() == c.canonical()

    def test_static_vs_instance_distinct(self) -> None:
        inst = build_callable_signature(_method(argsstring="()"))
        stat = build_callable_signature(_method(argsstring="()", is_static=True))
        assert inst.static is False and stat.static is True
        assert inst.canonical() != stat.canonical()

    def test_template_parameters_identity(self) -> None:
        plain = build_callable_signature(_method(argsstring="()"))
        templated = build_callable_signature(_method(
            argsstring="()",
            template_declarations=["typename T"],
        ))
        constrained = build_callable_signature(_method(
            argsstring="()",
            template_declarations=["ValidTransferObject T"],
        ))
        # typename/class interchangeable
        alt = build_callable_signature(_method(
            argsstring="()",
            template_declarations=["class T"],
        ))
        assert templated.canonical() == alt.canonical()
        assert templated.canonical() != plain.canonical()
        assert constrained.canonical() != templated.canonical()

    def test_roles(self) -> None:
        ctor = build_callable_signature(_method(
            name="Widget", qualified_name="ns::Widget::Widget", argsstring="()"
        ))
        dtor = build_callable_signature(_method(
            name="~Widget", qualified_name="ns::Widget::~Widget", argsstring="()"
        ))
        op = build_callable_signature(_method(
            name="operator==", qualified_name="ns::Widget::operator==", argsstring="(const Widget&)"
        ))
        conv = build_callable_signature(_method(
            name="operator bool", qualified_name="ns::Widget::operator bool", argsstring="() const"
        ))
        assert ctor.role == "constructor"
        assert dtor.role == "destructor"
        assert op.role == "operator"
        assert conv.role == "conversion"
        assert len({ctor.canonical(), dtor.canonical(), op.canonical(), conv.canonical()}) == 4

    def test_variadic(self) -> None:
        sig = build_callable_signature(_method(argsstring="(const char* fmt, ...)"))
        assert sig.variadic is True
        assert sig.canonical().endswith("|...")

    def test_adversarial_near_collisions(self) -> None:
        pairs = [
            ("(int* p)", "(int p)"),
            ("(const int& a)", "(int& a)"),
            ("()", "() const"),
            ("()", "() &"),
            ("()", "() &&"),
            ("()", "() noexcept"),
            ("(T& data)", "(const T& data)"),
            ("(T data)", "(T* data)"),
            ("(int a)", "(long a)"),
            ("(const int a)", "(int const a)"),
        ]
        for a, b in pairs:
            sa = build_callable_signature(_method(argsstring=a))
            sb = build_callable_signature(_method(argsstring=b))
            assert sa.canonical() != sb.canonical(), (a, b)

    def test_overloads_stay_distinct_in_keys(self) -> None:
        scope = IdentityScope.repository("p", "repo")
        variants = ["()", "(int)", "(int, int)", "() const", "() &&", "(T&)"]
        keys = {
            resolve_identity_for(
                _method(argsstring=v), scope
            ).key()
            for v in variants
        }
        assert len(keys) == len(variants)

    def test_callable_signature_object_has_single_canonical_form(self) -> None:
        sig = CallableSignature(parameters=("int",), qualifiers=("const",))
        assert sig.canonical() == str(sig)
        assert "|" in sig.canonical()

    def test_canonical_signature_provider_registered(self) -> None:
        assert "canonical_signature" in computed_providers
        sig = canonical_signature(_method(argsstring="(int)"))
        assert sig == "lang:cpp|(int)"
