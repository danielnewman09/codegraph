"""Tests for built-in context resolvers.

Tests the data transformation logic of each resolver by mocking
the GraphRepository layer.  No running Neo4j required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codegraph_agents.config import AgentConfig


# ── Helpers: mock model objects ────────────────────────────────


def _mock_hlr(uid: str = "hlr-001", **attrs) -> MagicMock:
    """Build a mock HLR node with default attributes."""
    defaults: dict[str, object] = {"uid": uid}
    defaults.update(attrs)
    return MagicMock(**defaults)


def _mock_llr(uid: str = "llr-001") -> MagicMock:
    """Build a mock LLR node."""
    llr = MagicMock()
    llr.uid = uid
    return llr


def _mock_test(
    uid: str = "test-001",
    name: str = "test_scenario",
    description: str = "Verify something",
) -> MagicMock:
    """Build a mock test node."""
    test = MagicMock()
    test.uid = uid
    test.name = name
    test.description = description
    return test


def _mock_step(description: str = "do something", callee: str = "") -> MagicMock:
    """Build a mock test step."""
    step = MagicMock()
    step.description = description
    step.callee_qualified_name = callee
    return step


def _mock_assertion(
    subject: str = "Namespace::Class::member",
    operator: str = "==",
    expected: str = "42",
) -> MagicMock:
    """Build a mock assertion."""
    a = MagicMock()
    a.subject_qualified_name = subject
    a.operator = operator
    a.expected_value = expected
    return a


def _mock_design_compound(
    qualified_name: str = "ns::MyClass",
    name: str = "MyClass",
    kind: str = "class",
) -> MagicMock:
    """Build a mock design compound node."""
    dc = MagicMock()
    dc.qualified_name = qualified_name
    dc.name = name
    dc.kind = kind
    return dc


def _mock_component(namespace: str = "archgen") -> MagicMock:
    """Build a mock component node."""
    comp = MagicMock()
    comp.namespace = namespace
    return comp


def _setup_repo_compose_map(
    repo_mock: MagicMock,
    *,
    llrs_for: dict[MagicMock, list[MagicMock]] | None = None,
    tests_for: dict[MagicMock, list[MagicMock]] | None = None,
    steps_for: dict[MagicMock, list[MagicMock]] | None = None,
    assertions_for: dict[MagicMock, list[MagicMock]] | None = None,
    design_compounds_for: dict[MagicMock, list[MagicMock]] | None = None,
    components_for: dict[MagicMock, list[MagicMock]] | None = None,
    all_hlrs: list[MagicMock] | None = None,
) -> None:
    """Configure a repo mock to return children based on parent identity.

    Each ``*_for`` dict maps a parent mock → list of child mocks.
    ``all_hlrs`` sets the return value of ``find_all_by_kind("hlr")``.
    """

    def _composed_children(node, child_type):
        type_name = getattr(child_type, "__name__", str(child_type))
        if type_name in ("LLR", "HlrNode"):
            return (llrs_for or {}).get(node, [])
        if type_name == "TestNode":
            return (tests_for or {}).get(node, [])
        if type_name == "TestStepNode":
            return (steps_for or {}).get(node, [])
        if type_name == "AssertionNode":
            return (assertions_for or {}).get(node, [])
        if type_name == "CompoundNode":
            return (design_compounds_for or {}).get(node, [])
        return []

    repo_mock.composed_children.side_effect = _composed_children

    def _incoming_composers(node, composer_type):
        type_name = getattr(composer_type, "__name__", str(composer_type))
        if type_name == "Component":
            return (components_for or {}).get(node, [])
        return []

    repo_mock.incoming_composers.side_effect = _incoming_composers
    repo_mock.find_all_by_kind.return_value = all_hlrs or []


# ── _resolve_hlr_subtree ───────────────────────────────────────


class TestResolveHlrSubtree:
    """Tests for the mandatory HLR subtree resolver."""

    def test_hlr_not_found_raises(self) -> None:
        """Raises ValueError when HLR doesn't exist in Neo4j."""
        from codegraph_agents.context import ContextProvider

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = None

            with pytest.raises(ValueError, match="not found"):
                ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="missing"),
                )

    def test_hlr_with_no_llrs(self) -> None:
        """Returns empty llrs and notional when HLR has no children."""
        from codegraph_agents.context import ContextProvider

        hlr = _mock_hlr()
        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(repo_mock)

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        assert result["hlr"] is hlr
        assert result["llrs"] == []
        assert result["notional_verifications"] == []
        assert result["design_compounds"] == []

    def test_hlr_with_llrs_and_tests(self) -> None:
        """Transforms LLR → tests → steps/assertions into notional dicts."""
        from codegraph_agents.context import ContextProvider

        step1 = _mock_step("call do_thing()", callee="ns::Svc::do_thing")
        step2 = _mock_step("verify result")
        assertion1 = _mock_assertion("ns::Svc::status", "==", "OK")
        test1 = _mock_test(
            uid="test-001",
            name="happy_path",
            description="Happy path test",
        )

        llr1 = _mock_llr("llr-001")
        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    llrs_for={hlr: [llr1]},
                    tests_for={llr1: [test1]},
                    steps_for={test1: [step1, step2]},
                    assertions_for={test1: [assertion1]},
                )

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        notional = result["notional_verifications"]
        assert len(notional) == 1
        t = notional[0]
        assert t["test_uid"] == "test-001"
        assert t["test_name"] == "happy_path"
        assert t["description"] == "Happy path test"
        assert len(t["steps"]) == 2
        assert t["steps"][0]["description"] == "call do_thing()"
        assert t["steps"][0]["callee_qualified_name"] == "ns::Svc::do_thing"
        assert t["steps"][1]["description"] == "verify result"
        assert t["steps"][1]["callee_qualified_name"] == ""
        assert len(t["assertions"]) == 1
        assert t["assertions"][0]["subject_qualified_name"] == "ns::Svc::status"
        assert t["assertions"][0]["operator"] == "=="
        assert t["assertions"][0]["expected_value"] == "OK"

    def test_hlr_with_design_compounds(self) -> None:
        """Extracts design compound metadata."""
        from codegraph_agents.context import ContextProvider

        dc1 = _mock_design_compound("archgen::Diagram", "Diagram", "class")
        dc2 = _mock_design_compound("archgen::ErrorState", "ErrorState", "enum")

        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    design_compounds_for={hlr: [dc1, dc2]},
                )

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        compounds = result["design_compounds"]
        assert len(compounds) == 2
        assert compounds[0] == {
            "qualified_name": "archgen::Diagram",
            "name": "Diagram",
            "kind": "class",
        }
        assert compounds[1] == {
            "qualified_name": "archgen::ErrorState",
            "name": "ErrorState",
            "kind": "enum",
        }

    def test_test_with_no_steps_or_assertions(self) -> None:
        """Test with empty steps/assertions produces empty lists."""
        from codegraph_agents.context import ContextProvider

        test1 = _mock_test(
            uid="test-empty",
            name="empty_test",
            description="No steps or assertions",
        )
        llr1 = _mock_llr()
        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    llrs_for={hlr: [llr1]},
                    tests_for={llr1: [test1]},
                    steps_for={test1: []},
                    assertions_for={test1: []},
                )

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        t = result["notional_verifications"][0]
        assert t["steps"] == []
        assert t["assertions"] == []

    def test_none_attributes_default_to_empty_strings(self) -> None:
        """None values in Neo4j become empty strings."""
        from codegraph_agents.context import ContextProvider

        step = MagicMock(description=None, callee_qualified_name=None)
        assertion = MagicMock(
            subject_qualified_name=None,
            operator=None,
            expected_value=None,
        )
        test = _mock_test(uid="test-nulls", name=None, description=None)
        llr = _mock_llr()
        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    llrs_for={hlr: [llr]},
                    tests_for={llr: [test]},
                    steps_for={test: [step]},
                    assertions_for={test: [assertion]},
                )

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        t = result["notional_verifications"][0]
        assert t["test_name"] == ""
        assert t["description"] == ""
        assert t["steps"][0]["description"] == ""
        assert t["steps"][0]["callee_qualified_name"] == ""
        assert t["assertions"][0]["subject_qualified_name"] == ""
        assert t["assertions"][0]["operator"] == ""
        assert t["assertions"][0]["expected_value"] == ""

    def test_multiple_llrs(self) -> None:
        """Multiple LLRs under one HLR all appear in notional_verifications."""
        from codegraph_agents.context import ContextProvider

        test_a = _mock_test(uid="t-a", name="test A")
        test_b = _mock_test(uid="t-b", name="test B")
        llr_a = _mock_llr("llr-a")
        llr_b = _mock_llr("llr-b")
        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    llrs_for={hlr: [llr_a, llr_b]},
                    tests_for={llr_a: [test_a], llr_b: [test_b]},
                    steps_for={test_a: [], test_b: []},
                    assertions_for={test_a: [], test_b: []},
                )

                result = ContextProvider.resolve(
                    "hlr_subtree",
                    AgentConfig(hlr_uid="hlr-001"),
                )

        notional = result["notional_verifications"]
        assert len(notional) == 2
        assert {t["test_uid"] for t in notional} == {"t-a", "t-b"}


# ── _resolve_component_namespace ────────────────────────────────


class TestResolveComponentNamespace:
    """Tests for the optional component namespace resolver."""

    def test_returns_config_value_directly(self) -> None:
        """Returns config.component_namespace when set — no Neo4j call."""
        from codegraph_agents.context import ContextProvider

        result = ContextProvider.resolve(
            "component_namespace",
            AgentConfig(component_namespace="custom_ns"),
        )
        assert result == "custom_ns"

    def test_resolves_from_hlr_component(self) -> None:
        """Queries HLR's component for namespace when config value is empty."""
        from codegraph_agents.context import ContextProvider

        comp = _mock_component("archgen")
        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    components_for={hlr: [comp]},
                )

                result = ContextProvider.resolve(
                    "component_namespace",
                    AgentConfig(hlr_uid="hlr-001"),
                )
        assert result == "archgen"

    def test_hlr_not_found_returns_empty(self) -> None:
        """Returns empty string when HLR is not in Neo4j."""
        from codegraph_agents.context import ContextProvider

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = None

            result = ContextProvider.resolve(
                "component_namespace",
                AgentConfig(hlr_uid="missing"),
            )
        assert result == ""

    def test_hlr_has_no_component_returns_empty(self) -> None:
        """Returns empty string when HLR has no component relationship."""
        from codegraph_agents.context import ContextProvider

        hlr = _mock_hlr()

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    components_for={hlr: []},
                )

                result = ContextProvider.resolve(
                    "component_namespace",
                    AgentConfig(hlr_uid="hlr-001"),
                )
        assert result == ""


# ── _resolve_prior_design_compounds ─────────────────────────────


class TestResolvePriorDesignCompounds:
    """Tests for cross-HLR design compound awareness."""

    def test_excludes_current_hlr(self) -> None:
        """Does not include design compounds from the HLR being processed."""
        from codegraph_agents.context import ContextProvider

        dc = _mock_design_compound("ns::Other", "Other")
        other_hlr = _mock_hlr(uid="hlr-other")
        current_hlr = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current_hlr
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current_hlr, other_hlr],
                    design_compounds_for={other_hlr: [dc], current_hlr: []},
                )

                result = ContextProvider.resolve(
                    "prior_design_compounds",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert len(result) == 1
        assert result[0]["qualified_name"] == "ns::Other"

    def test_skips_hlrs_without_design_compounds(self) -> None:
        """HLRs without design compounds are skipped."""
        from codegraph_agents.context import ContextProvider

        hlr_without = _mock_hlr(uid="hlr-no-dc")
        dc = _mock_design_compound("ns::HasOne", "HasOne")
        hlr_with = _mock_hlr(uid="hlr-with")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current, hlr_without, hlr_with],
                    design_compounds_for={
                        hlr_with: [dc],
                        hlr_without: [],
                        current: [],
                    },
                )

                result = ContextProvider.resolve(
                    "prior_design_compounds",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert len(result) == 1
        assert result[0]["qualified_name"] == "ns::HasOne"

    def test_empty_when_no_other_hlrs(self) -> None:
        """Returns empty list when only the current HLR exists."""
        from codegraph_agents.context import ContextProvider

        current = _mock_hlr(uid="only-hlr")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current],
                    design_compounds_for={current: []},
                )

                result = ContextProvider.resolve(
                    "prior_design_compounds",
                    AgentConfig(hlr_uid="only-hlr"),
                )

        assert result == []


# ── _resolve_sibling_namespaces ─────────────────────────────────


class TestResolveSiblingNamespaces:
    """Tests for sibling component namespace discovery."""

    def test_collects_unique_namespaces(self) -> None:
        """Collects unique namespaces from sibling HLRs' components."""
        from codegraph_agents.context import ContextProvider

        comp_a = _mock_component("archgen")
        hlr_a = _mock_hlr(uid="hlr-a")
        comp_b = _mock_component("climate")
        hlr_b = _mock_hlr(uid="hlr-b")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current, hlr_a, hlr_b],
                    components_for={
                        hlr_a: [comp_a],
                        hlr_b: [comp_b],
                        current: [],
                    },
                )

                result = ContextProvider.resolve(
                    "sibling_namespaces",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert sorted(result) == ["archgen", "climate"]

    def test_deduplicates_same_namespace(self) -> None:
        """Multiple HLRs in the same namespace produce one entry."""
        from codegraph_agents.context import ContextProvider

        comp1 = _mock_component("shared_ns")
        hlr1 = _mock_hlr(uid="hlr-1")
        comp2 = _mock_component("shared_ns")
        hlr2 = _mock_hlr(uid="hlr-2")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current, hlr1, hlr2],
                    components_for={
                        hlr1: [comp1],
                        hlr2: [comp2],
                        current: [],
                    },
                )

                result = ContextProvider.resolve(
                    "sibling_namespaces",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert result == ["shared_ns"]

    def test_excludes_current_hlr(self) -> None:
        """Does not include the current HLR's own namespace."""
        from codegraph_agents.context import ContextProvider

        comp = _mock_component("current_ns")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current],
                    components_for={current: [comp]},
                )

                result = ContextProvider.resolve(
                    "sibling_namespaces",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert result == []

    def test_skips_hlrs_without_component(self) -> None:
        """HLRs with no component relationship are skipped."""
        from codegraph_agents.context import ContextProvider

        hlr_no_comp = _mock_hlr(uid="hlr-no-comp")
        comp = _mock_component("archgen")
        hlr_with_comp = _mock_hlr(uid="hlr-with")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current, hlr_no_comp, hlr_with_comp],
                    components_for={
                        hlr_with_comp: [comp],
                        hlr_no_comp: [],
                        current: [],
                    },
                )

                result = ContextProvider.resolve(
                    "sibling_namespaces",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert result == ["archgen"]

    def test_empty_namespace_filtered(self) -> None:
        """Components with empty namespace strings are filtered out."""
        from codegraph_agents.context import ContextProvider

        comp_empty = _mock_component("")
        hlr_empty = _mock_hlr(uid="hlr-empty")
        comp_real = _mock_component("real_ns")
        hlr_real = _mock_hlr(uid="hlr-real")
        current = _mock_hlr(uid="hlr-current")

        with patch(
            "codegraph_requirements.models.HLR"
        ) as mock_hlr_model:
            mock_hlr_model.nodes.get_or_none.return_value = current
            with patch(
                "codegraph_agents.context.builtins.repo"
            ) as repo_mock:
                _setup_repo_compose_map(
                    repo_mock,
                    all_hlrs=[current, hlr_empty, hlr_real],
                    components_for={
                        hlr_empty: [comp_empty],
                        hlr_real: [comp_real],
                        current: [],
                    },
                )

                result = ContextProvider.resolve(
                    "sibling_namespaces",
                    AgentConfig(hlr_uid="hlr-current"),
                )

        assert result == ["real_ns"]
