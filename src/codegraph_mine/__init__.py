"""LLM-based requirement mining from codegraph test evidence.

Mines high-level requirements (HLRs) and low-level requirements (LLRs)
from existing test nodes in the codegraph knowledge graph.  Operates
class-by-class: for each compound with tests, gathers all test context
and sends it to an LLM to infer requirements.

Usage::

    from codegraph_mine import LLRMiner

    miner = LLRMiner()
    results = miner.mine_all(tag="as-built")
    print(f"Mined {results.total_llrs} LLRs across {results.total_compounds} compounds")

    # Or mine a single compound:
    from codegraph.models.compound import ClassNode
    node = ClassNode.nodes.get(
        qualified_name="codegraph.models.compound.ClassNode"
    )
    result = miner.mine_one(node)
    print(f"Mined {result.llr_count} LLRs")

Graph output::

    HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
    HLR -[:COMPOSES]-> CompoundNode

Environment:
    Requires the ``llm-caller`` package and its configuration via
    ``LLM_API_KEY``, ``LLM_BASE_URL``, ``LLM_MODEL``, ``LLM_BACKEND``.
    Requires ``NEO4J_URI``, ``NEO4J_USER``, ``NEO4J_PASSWORD`` for
    Neo4j connectivity (loaded from ``.env`` if present).
"""

# ── Load .env BEFORE any codegraph imports ─────────────────────────────
# When the CLI entry point imports this package, __init__.py executes
# BEFORE __main__.py.  We must load .env here so that
# codegraph.persistence.config sees the correct NEO4J_* env vars when
# it is first imported (transitively, via neomodel models).
import os
from pathlib import Path as _Path

_dotenv_path = _Path.cwd() / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(_dotenv_path)
    except ImportError:
        pass
# ────────────────────────────────────────────────────────────────────────

from codegraph_mine.base import MineResult, MineSummary, RequirementMiner
from codegraph_mine.llr_miner import LLRMiner
from codegraph_mine.composite_miner import CompositeHLRMiner
from codegraph_mine.component_miner import ComponentMiner
from codegraph_mine.schemas import MinedLLR, MinedRequirements, MinedCompositeHLR, MinedComponent, MinedComponents
from codegraph_mine.persistence import persist_mined_requirements, persist_composite_hlr, persist_mined_components
from codegraph_mine.report import generate_report


def mining_available() -> bool:
    """Return True if the environment is configured for LLM mining.

    Checks that ``llm_caller`` is importable and that ``LLM_API_KEY``
    is set.
    """
    try:
        import llm_caller  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("LLM_API_KEY"))


__all__ = [
    "MineResult",
    "MineSummary",
    "RequirementMiner",
    "LLRMiner",
    "CompositeHLRMiner",
    "ComponentMiner",
    "MinedLLR",
    "MinedRequirements",
    "MinedCompositeHLR",
    "MinedComponent",
    "MinedComponents",
    "persist_mined_requirements",
    "persist_composite_hlr",
    "persist_mined_components",
    "generate_report",
    "mining_available",
]
