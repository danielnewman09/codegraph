"""Declarative context loading for agents.

Provides :class:`ContextProvider` — a registry that maps string
keys (e.g. ``"hlr_subtree"``) to resolver functions.  Agents
declare their needs in :attr:`~codegraph_agents.base.BaseAgent.context_needs`
and the provider resolves them from Neo4j before the agent runs.

Built-in resolvers live in :mod:`codegraph_agents.context.builtins`.
Custom resolvers can be registered by applications::

    from codegraph_agents.context import ContextProvider

    def my_resolver(config: AgentConfig) -> Any:
        ...

    ContextProvider.register("my_custom_need", my_resolver)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("codegraph_agents.context")


class ContextProvider:
    """Resolve declarative context needs from Neo4j.

    Each "context need" is a string key that maps to a resolver
    function taking an :class:`~codegraph_agents.config.AgentConfig`
    and returning a context value.  Resolvers are registered at
    module load time.
    """

    _resolvers: dict[str, Callable[..., Any]] = {}

    @classmethod
    def register(
        cls, name: str, resolver: Callable[..., Any]
    ) -> None:
        """Register a resolver for a context need.

        Args:
            name: The context need string
                (e.g. ``"hlr_subtree"``).
            resolver: Callable that takes an
                :class:`~codegraph_agents.config.AgentConfig`
                and returns the resolved context value.

        Raises:
            ValueError: If *name* is already registered.
        """
        if name in cls._resolvers:
            raise ValueError(
                f"Context need '{name}' is already registered"
            )
        cls._resolvers[name] = resolver

    @classmethod
    def resolve(cls, need: str, config: Any) -> Any:
        """Resolve a single context need.

        Args:
            need: The context need string.
            config: The agent configuration
                (:class:`~codegraph_agents.config.AgentConfig`).

        Returns:
            The resolver's return value.

        Raises:
            ValueError: If *need* is not registered.
        """
        resolver = cls._resolvers.get(need)
        if resolver is None:
            raise ValueError(
                f"Unknown context need: '{need}'. "
                f"Available: {sorted(cls._resolvers.keys())}"
            )
        return resolver(config)


# Import built-in resolvers so they self-register
from codegraph_agents.context import builtins  # noqa: E402, F401
