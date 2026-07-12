"""Tests for DesignAgent — the OO design pipeline port.

Tests the agent's context loading, message building, result
extraction, and dispatcher wiring.  Uses mocked Neo4j model
objects — no running Neo4j required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from codegraph_agents.config import AgentConfig
from codegraph_agents.state import AgentState


# ── Helpers ──────────────────────────────────────────────────────


def _mock_hlr_tree(
    hlr_uid: str = "hlr-001",
    hlr_desc: str = "A test HLR",
    notional: list[dict] | None = None,
    design_compounds: list[dict] | None = None,
) -> dict:
    """Build a mock hlr_subtree context dict."""
    hlr = MagicMock()
    hlr.uid = hlr_uid
    hlr.description = hlr_desc
    hlr.name = "TestHLR"
    return {
        "hlr": hlr,
        "llrs": [],
        "notional_verifications": notional or [],
        "design_compounds": design_compounds or [],
    }


def _make_state_with_tool_output(
    tool_name: str,
    output: dict,
) -> AgentState:
    """Build an AgentState with a ToolMessage from *tool_name*."""
    return {
        "messages": [
            HumanMessage(content="do it"),
            ToolMessage(
                content=json.dumps(output),
                tool_call_id="tc-1",
                name=tool_name,
            ),
        ],
        "agent_name": "design_oo",
        "phase": "done",
        "turn_count": 5,
        "error_count": 0,
    }


# ── Dispatcher wiring ────────────────────────────────────────────


class TestDesignAgentInit:
    """Tests for agent construction and dispatcher setup."""

    def test_name_is_design_oo(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        assert agent.name == "design_oo"

    def test_context_needs_include_all_resolvers(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        assert "hlr_subtree" in agent.context_needs
        assert "component_namespace" in agent.context_needs
        assert "prior_design_compounds" in agent.context_needs
        assert "sibling_namespaces" in agent.context_needs

    def test_final_tool_is_commit(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        assert agent.final_tool_name == "commit_design_and_verifications"

    def test_dispatcher_is_composite(self) -> None:
        from codegraph_agents.design import DesignAgent
        from codegraph_agents.design.agent import _CompositeDispatcher

        agent = DesignAgent()
        assert isinstance(agent.dispatcher, _CompositeDispatcher)

    def test_dispatcher_has_tool_schemas(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        schemas = agent.dispatcher.all_tool_schemas
        assert len(schemas) > 0

        names = {s.get("name", s.get("function", {}).get("name", ""))
                 for s in schemas}
        assert "validate_design" in names
        assert "import_compound" in names
        assert "check_class_name" in names
        assert "produce_oo_design" in names
        assert "check_design_smells" in names
        assert "draft_verifications" in names
        assert "commit_design_and_verifications" in names


# ── Context loading ──────────────────────────────────────────────


class TestDesignAgentLoadContext:
    """Tests for context loading with dispatcher seeding."""

    def test_seeds_dispatcher_from_context(self) -> None:
        """load_context() resolves context AND seeds DesignToolDispatcher."""
        from codegraph_agents.design import DesignAgent

        dc = {"qualified_name": "ns::ExistingClass", "name": "ExistingClass", "kind": "class"}

        with patch(
            "codegraph_agents.context.ContextProvider.resolve"
        ) as mock_resolve:
            mock_resolve.side_effect = lambda need, config: {
                "hlr_subtree": _mock_hlr_tree(
                    design_compounds=[dc],
                ),
                "component_namespace": "climate",
                "prior_design_compounds": [],
                "sibling_namespaces": ["ui", "archgen"],
            }.get(need)

            agent = DesignAgent()
            ctx = agent.load_context()

            assert agent._design_disp.component_namespace == "climate"
            assert agent._design_disp.sibling_namespaces == ["ui", "archgen"]
            # context_graph should have been seeded
            entries = list(agent._design_disp.context_graph._all_entries())
            assert len(entries) == 1

    def test_empty_context_does_not_break(self) -> None:
        """Loads cleanly when all context is empty."""
        from codegraph_agents.design import DesignAgent

        with patch(
            "codegraph_agents.context.ContextProvider.resolve"
        ) as mock_resolve:
            mock_resolve.side_effect = lambda need, config: {
                "hlr_subtree": _mock_hlr_tree(),
                "component_namespace": "",
                "prior_design_compounds": [],
                "sibling_namespaces": [],
            }.get(need)

            agent = DesignAgent()
            ctx = agent.load_context()

            assert agent._design_disp.component_namespace == ""
            assert agent._design_disp.sibling_namespaces == []


# ── Initial message building ─────────────────────────────────────


class TestDesignAgentBuildMessages:
    """Tests for build_initial_messages()."""

    def test_builds_message_with_hlr_description(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "hlr_subtree": _mock_hlr_tree(
                hlr_desc="Design a thermostat component",
            ),
            "component_namespace": "",
            "prior_design_compounds": [],
            "sibling_namespaces": [],
        }

        messages = agent.build_initial_messages(agent._context)
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert "Design a thermostat component" in str(messages[0].content)
        assert "Notional verification stubs" not in str(messages[0].content)

    def test_includes_notional_verifications(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "hlr_subtree": _mock_hlr_tree(
                hlr_desc="Design a widget",
                notional=[
                    {
                        "test_uid": "test-001",
                        "test_name": "happy_path",
                        "description": "Happy path scenario",
                        "steps": [
                            {
                                "description": "call do_thing()",
                                "callee_qualified_name": "ns::Svc::do_thing",
                            },
                        ],
                        "assertions": [
                            {
                                "subject_qualified_name": "ns::Svc::status",
                                "operator": "==",
                                "expected_value": "OK",
                            },
                        ],
                    },
                ],
            ),
            "component_namespace": "",
            "prior_design_compounds": [],
            "sibling_namespaces": [],
        }

        messages = agent.build_initial_messages(agent._context)
        content = str(messages[0].content)

        assert "Notional verification stubs" in content
        assert "happy_path" in content
        assert "Happy path scenario" in content
        assert "call do_thing()" in content
        assert "ns::Svc::do_thing" in content
        assert "ns::Svc::status == OK" in content

    def test_includes_namespace_hint(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "hlr_subtree": _mock_hlr_tree(),
            "component_namespace": "climate",
            "prior_design_compounds": [],
            "sibling_namespaces": [],
        }

        messages = agent.build_initial_messages(agent._context)
        content = str(messages[0].content)

        assert "`climate`" in content
        assert "scoped to this namespace" in content

    def test_steps_without_callee_still_shown(self) -> None:
        """Steps without callee_qualified_name are shown without → arrow."""
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "hlr_subtree": _mock_hlr_tree(
                hlr_desc="Test",
                notional=[
                    {
                        "test_uid": "t1",
                        "test_name": "test_case",
                        "description": "A test",
                        "steps": [
                            {"description": "setup", "callee_qualified_name": ""},
                        ],
                        "assertions": [],
                    },
                ],
            ),
            "component_namespace": "",
            "prior_design_compounds": [],
            "sibling_namespaces": [],
        }

        messages = agent.build_initial_messages(agent._context)
        content = str(messages[0].content)

        assert "setup" in content
        # No → should appear after "setup"
        assert "setup →" not in content


# ── Result extraction ────────────────────────────────────────────


class TestDesignAgentBuildResult:
    """Tests for build_result()."""

    def test_extracts_design_and_verifications(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        state = _make_state_with_tool_output(
            "commit_design_and_verifications",
            {
                "design": [{"qualified_name": "ns::MyClass", "type": "ClassNode"}],
                "verifications": {"llr-001": [{"method": "automated"}]},
            },
        )

        result = agent.build_result(state)

        assert len(result.design) == 1
        assert result.design[0]["qualified_name"] == "ns::MyClass"
        assert result.verifications == {"llr-001": [{"method": "automated"}]}
        assert result.errors == []

    def test_no_commit_output_returns_errors(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        state = {
            "messages": [HumanMessage(content="hi")],
            "agent_name": "design_oo",
            "phase": "done",
            "turn_count": 1,
            "error_count": 0,
        }

        result = agent.build_result(state)
        assert result.design == []
        assert result.verifications == {}
        assert len(result.errors) >= 1

    def test_no_design_in_commit(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        state = _make_state_with_tool_output(
            "commit_design_and_verifications",
            {"verifications": {}},
        )

        result = agent.build_result(state)
        assert result.design == []
        assert "No design nodes" in result.errors[0]

    def test_no_verifications_in_commit(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        state = _make_state_with_tool_output(
            "commit_design_and_verifications",
            {"design": [{"qualified_name": "ns::Cls"}]},
        )

        result = agent.build_result(state)
        assert len(result.design) == 1
        assert "No verifications" in result.errors[0]

    def test_extracts_from_correct_tool_only(self) -> None:
        """Other ToolMessages are ignored — only commit_design_and_verifications is read."""
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        state = {
            "messages": [
                HumanMessage(content="go"),
                ToolMessage(
                    content=json.dumps({"stored": True}),
                    tool_call_id="tc-1",
                    name="produce_oo_design",
                ),
                ToolMessage(
                    content=json.dumps({
                        "design": [{"qualified_name": "ns::Real"}],
                        "verifications": {"llr-1": [{"method": "auto"}]},
                    }),
                    tool_call_id="tc-2",
                    name="commit_design_and_verifications",
                ),
            ],
            "agent_name": "design_oo",
            "phase": "done",
            "turn_count": 10,
            "error_count": 0,
        }

        result = agent.build_result(state)
        assert result.design[0]["qualified_name"] == "ns::Real"
        assert result.verifications == {"llr-1": [{"method": "auto"}]}


# ── run_with_reconciliation ──────────────────────────────────────


class TestRunWithReconciliation:
    """Tests for run_with_reconciliation()."""

    def test_raises_without_hlr_uid(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent(AgentConfig(hlr_uid=""))
        with pytest.raises(ValueError, match="hlr_uid"):
            agent.run_with_reconciliation()

    def test_no_design_skips_reconciliation(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent(AgentConfig(hlr_uid="abc123def456"))

        with patch.object(agent, "run") as mock_run:
            mock_run.return_value = agent.build_result(
                _make_state_with_tool_output(
                    "commit_design_and_verifications",
                    {"design": [], "verifications": {}},
                )
            )

            result = agent.run_with_reconciliation()

            assert result["nodes_updated"] == 0
            assert result["nodes_created"] == 0
            assert "No design nodes" in str(result["errors"])


# ── _format_system_prompt ────────────────────────────────────────


class TestFormatSystemPrompt:
    """Tests for system prompt formatting via base class."""

    def test_includes_namespace_and_existing_classes(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "specializations_section": "",
            "as_built_section": "",
            "namespace_section": "The required namespace: `climate`\nOther: ui",
            "existing_classes_section": "### class: `ns::OldClass`",
            "intercomponent_section": "",
        }

        prompt = agent._format_system_prompt()

        assert "climate" in prompt
        assert "ui" in prompt
        assert "OldClass" in prompt
        assert "commit_design_and_verifications" in prompt
        assert "FORMAT-CONTRACT" in prompt

    def test_no_context_sections_when_empty(self) -> None:
        from codegraph_agents.design import DesignAgent

        agent = DesignAgent()
        agent._context = {
            "specializations_section": "",
            "as_built_section": "",
            "namespace_section": "",
            "existing_classes_section": "",
            "intercomponent_section": "",
        }

        prompt = agent._format_system_prompt()

        assert "commit_design_and_verifications" in prompt
        assert "FORMAT-CONTRACT" in prompt


# ── Composite dispatcher ─────────────────────────────────────────


class TestCompositeDispatcher:
    """Tests for _CompositeDispatcher."""

    def test_routes_to_verification_dispatcher(self) -> None:
        from codegraph_agents.design.agent import _CompositeDispatcher

        design = MagicMock()
        design._handlers = {"validate_design": MagicMock()}
        design.all_tool_schemas = [{"name": "validate_design"}]

        verif = MagicMock()
        verif._handlers = {"draft_verifications": MagicMock()}
        verif.all_tool_schemas = [{"name": "draft_verifications"}]
        verif.dispatch.return_value = '{"valid": true}'

        comp = _CompositeDispatcher(design, verif)
        result = comp.dispatch("draft_verifications", {"verifications": {}})

        verif.dispatch.assert_called_once()
        assert '"valid": true' in result

    def test_routes_to_design_dispatcher(self) -> None:
        from codegraph_agents.design.agent import _CompositeDispatcher

        design = MagicMock()
        design._handlers = {"validate_design": MagicMock()}
        design.all_tool_schemas = [{"name": "validate_design"}]
        design.dispatch.return_value = '{"valid": true}'

        verif = MagicMock()
        verif._handlers = {"draft_verifications": MagicMock()}
        verif.all_tool_schemas = [{"name": "draft_verifications"}]

        comp = _CompositeDispatcher(design, verif)
        result = comp.dispatch("validate_design", {"nodes": []})

        design.dispatch.assert_called_once()
        verif.dispatch.assert_not_called()

    def test_combined_schemas(self) -> None:
        from codegraph_agents.design.agent import _CompositeDispatcher

        design = MagicMock()
        design.all_tool_schemas = [{"name": "a"}, {"name": "b"}]
        design._handlers = {}

        verif = MagicMock()
        verif.all_tool_schemas = [{"name": "c"}]
        verif._handlers = {}

        comp = _CompositeDispatcher(design, verif)
        schemas = comp.all_tool_schemas

        assert len(schemas) == 3
        assert schemas[0]["name"] == "a"
        assert schemas[2]["name"] == "c"
