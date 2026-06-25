"""LLM-based description enrichment for codegraph nodes.

Uses ``llm-caller`` to enrich fields on Neo4j nodes.  The
:class:`GraphEnricher` abstract base class provides the
fetch→prompt→call→parse→save pipeline.  Subclasses like
:class:`TestEnricher` define type-specific behaviour (which
relationships to traverse, how to build prompts).

Usage::

    from codegraph_enrich import TestEnricher

    enricher = TestEnricher()
    summary = enricher.enrich_one(test_node)
    print(summary.total_enriched)

    # Enrich every test with the "as-built" tag:
    results = enricher.enrich_all(tag="as-built")

Environment:
    Requires the ``llm-caller`` package and its configuration via
    ``LLM_API_KEY``, ``LLM_BASE_URL``, ``LLM_MODEL``, ``LLM_BACKEND``.
"""

import os

from codegraph_enrich.base import EnrichmentResult, EnrichmentSummary, GraphEnricher
from codegraph_enrich.test_enricher import TestEnricher


def enrichment_available() -> bool:
    """Return True if the environment is configured for LLM enrichment.

    Checks that ``llm_caller`` is importable and that ``LLM_API_KEY``
    is set.
    """
    try:
        import llm_caller  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("LLM_API_KEY"))


__all__ = [
    "EnrichmentResult",
    "EnrichmentSummary",
    "GraphEnricher",
    "TestEnricher",
    "enrichment_available",
]
