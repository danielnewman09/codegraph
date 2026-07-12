"""Tests for ContextProvider — declarative context resolution."""

from __future__ import annotations

import pytest

from codegraph_agents.context import ContextProvider
from codegraph_agents.config import AgentConfig


class TestContextProvider:
    """Tests for ContextProvider registration, lookup, and error handling."""

    def test_builtin_resolvers_registered(self) -> None:
        """Built-in resolvers are available after import."""
        resolvers = sorted(ContextProvider._resolvers.keys())
        assert "hlr_subtree" in resolvers
        assert "component_namespace" in resolvers
        assert "prior_design_compounds" in resolvers
        assert "sibling_namespaces" in resolvers

    def test_register_custom_resolver(self) -> None:
        """Custom resolvers can be registered."""
        def my_resolver(config: AgentConfig) -> str:
            return f"resolved-{config.hlr_uid}"

        ContextProvider.register("my_custom_need", my_resolver)
        try:
            result = ContextProvider.resolve(
                "my_custom_need",
                AgentConfig(hlr_uid="test-uid"),
            )
            assert result == "resolved-test-uid"
        finally:
            # Clean up
            del ContextProvider._resolvers["my_custom_need"]

    def test_register_duplicate_raises(self) -> None:
        """Registering a duplicate name raises ValueError."""
        ContextProvider.register("dup_test", lambda _: "ok")
        try:
            with pytest.raises(ValueError, match="already registered"):
                ContextProvider.register("dup_test", lambda _: "nope")
        finally:
            del ContextProvider._resolvers["dup_test"]

    def test_resolve_unknown_raises(self) -> None:
        """Resolving an unregistered need raises ValueError."""
        with pytest.raises(ValueError, match="Unknown context need"):
            ContextProvider.resolve(
                "nonexistent_need",
                AgentConfig(),
            )

    def test_resolve_returns_resolver_value(self) -> None:
        """Resolve returns whatever the resolver returns."""
        ContextProvider.register("int_need", lambda _: 42)
        try:
            result = ContextProvider.resolve("int_need", AgentConfig())
            assert result == 42
        finally:
            del ContextProvider._resolvers["int_need"]

    def test_component_namespace_from_config(self) -> None:
        """component_namespace resolver returns config value if set."""
        result = ContextProvider.resolve(
            "component_namespace",
            AgentConfig(component_namespace="archgen"),
        )
        assert result == "archgen"

    def test_prior_design_compounds_handles_no_neo4j(self) -> None:
        """prior_design_compounds returns empty list when Neo4j unavailable."""
        result = ContextProvider.resolve(
            "prior_design_compounds",
            AgentConfig(run_id="nonexistent"),
        )
        assert isinstance(result, list)
        assert result == []

    def test_sibling_namespaces_handles_no_neo4j(self) -> None:
        """sibling_namespaces returns empty list when Neo4j unavailable."""
        result = ContextProvider.resolve(
            "sibling_namespaces",
            AgentConfig(run_id="nonexistent"),
        )
        assert isinstance(result, list)
        assert result == []
