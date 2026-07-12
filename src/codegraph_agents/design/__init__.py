"""Design agent package.

Exports:
- :class:`DesignAgent` — OO design pipeline with LangGraph checkpointing
- :class:`DesignResult` — result dataclass (design nodes + verifications)
"""

from codegraph_agents.design.agent import DesignAgent, DesignResult

__all__ = ["DesignAgent", "DesignResult"]
