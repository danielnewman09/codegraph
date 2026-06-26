"""Persistence layer for mined requirements.

Persists HLR/LLR nodes and their relationships into Neo4j.  Follows the
data model established by ``codegraph_requirements``::

    HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
    HLR -[:COMPOSES]-> CompoundNode (design link)

Uses the neomodel ORM (``HLR``/``LLR`` models) for node creation and
raw Cypher for edge creation.

Usage::

    from codegraph_mine.persistence import persist_mined_requirements

    result = persist_mined_requirements(
        compound_node=class_node,
        mined_reqs=mined_requirements,
    )
    print(f"Created {result.llr_count} LLRs")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neomodel import db

from codegraph_requirements.models.requirement import HLR, LLR
from codegraph_mine.schemas import MinedRequirements
from codegraph_mine.base import MineResult

log = logging.getLogger(__name__)


@dataclass
class PersistResult:
    """Result of persisting mined requirements.

    Attributes:
        hlr_description: The HLR text that was persisted.
        llr_count: Number of LLRs created/updated.
        test_count: Number of test → LLR links created.
    """

    hlr_description: str = ""
    llr_count: int = 0
    test_count: int = 0


def persist_mined_requirements(
    compound,
    mined: MinedRequirements,
    *,
    source: str = "codegraph",
    tag: str = "as-built",
) -> MineResult:
    """Persist mined HLR and LLR nodes linked to their verifier tests.

    Creates (or updates, if ``compound_name`` matches) one HLR node and
    one LLR node per mined requirement.  Each LLR is connected to its
    verifier TestNodes via ``COMPOSES`` edges.

    This uses raw Cypher MERGE operations so that the same tests can
    participate in multiple LLRs and the same compound can be re-mined.

    Args:
        compound: The CompoundNode (ClassNode, InterfaceNode, etc.) that
            the requirements describe.
        mined: Parsed :class:`MinedRequirements` from the LLM.
        source: Source provenance for new nodes (default ``"codegraph"``).
        tag: Provenance tag for new nodes (default ``"as-built"``).

    Returns:
        A :class:`MineResult` with counts.
    """
    from neomodel import db

    compound_name = getattr(compound, "qualified_name", "")
    if not compound_name:
        return MineResult(
            compound_name="(unknown)",
            error="Compound has no qualified_name",
        )

    try:
        # 1. Create/update the HLR node
        hlr_node = _upsert_hlr(compound_name, mined.hlr_description, source, tag)

        # 2. For each mined LLR, create the LLR node and link to tests
        llr_count = 0
        test_count = 0

        for llr_data in mined.llrs:
            llr_node = _upsert_llr(
                hlr_node, compound_name, llr_data, source, tag
            )
            if llr_node:
                llr_count += 1
                linked = _link_llr_to_tests(llr_node, llr_data.verified_by)
                test_count += linked

                # 3. Optionally link HLR to the compound
                _link_hlr_to_compound(hlr_node, compound)

        return MineResult(
            compound_name=compound_name,
            hlr_description=mined.hlr_description,
            llr_count=llr_count,
            test_count=test_count,
        )

    except Exception as exc:
        log.exception("persist_mined_requirements failed for %s", compound_name)
        return MineResult(
            compound_name=compound_name,
            error=str(exc),
        )


# ══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════


def _make_hlr_name(compound_name: str) -> str:
    """Derive a short name for the HLR from the compound (e.g. ClassNode)."""
    short = compound_name.rsplit(".", 1)[-1]
    return f"Requirements for {short}"


def _make_llr_name(compound_name: str, index: int) -> str:
    """Derive a short name for an LLR."""
    short = compound_name.rsplit(".", 1)[-1]
    return f"{short} LLR-{index + 1}"


def _upsert_hlr(
    compound_name: str,
    description: str,
    source: str,
    tag: str,
):
    """Create or update an HLR node for a compound.

    Uses MERGE on (name) to avoid creating duplicate HLRs for the
    same compound on re-runs.
    """
    from codegraph_requirements.models.requirement import HLR

    name = _make_hlr_name(compound_name)

    # Try to find existing
    existing = HLR.nodes.get_or_none(name=name, source=source)

    if existing:
        existing.description = description
        existing.tags = list(set((existing.tags or []) + [tag]))
        existing.save()
        return existing

    hlr = HLR(
        name=name,
        description=description,
        tags=[tag],
        source=source,
    )
    hlr.save()
    return hlr


def _upsert_llr(
    hlr,
    compound_name: str,
    llr_data,
    source: str,
    tag: str,
):
    """Create an LLR node and connect it to its parent HLR.

    Returns None if ``llr_data`` is not a ``MinedLLR`` or has no
    description.
    """
    from codegraph_requirements.models.requirement import LLR

    if not llr_data.description:
        return None

    # Determine index for naming (brute-force: count existing LLRs + 1)
    existing_count = len(hlr.llrs.all())

    name = _make_llr_name(compound_name, existing_count)

    llr = LLR(
        name=name,
        description=llr_data.description,
        tags=[tag],
        source=source,
    )
    llr.save()

    # Connect HLR → LLR
    _create_edge(hlr, llr, "COMPOSES")

    return llr


def _link_llr_to_tests(llr, test_qnames: list[str]) -> int:
    """Connect an LLR to its verifier TestNodes via COMPOSES.

    Returns the number of successful links.
    """
    from codegraph.models.test import TestNode

    linked = 0
    for qn in test_qnames:
        try:
            test_node = TestNode.nodes.get_or_none(qualified_name=qn)
            if test_node is None:
                log.debug(
                    "_link_llr_to_tests: TestNode not found: %s", qn
                )
                continue
            _create_edge(llr, test_node, "COMPOSES")
            linked += 1
        except Exception as exc:
            log.warning(
                "_link_llr_to_tests: failed for %s → %s: %s",
                getattr(llr, "name", "?"), qn, exc,
            )
    return linked


def _link_hlr_to_compound(hlr, compound) -> bool:
    """Create an HLR → CompoundNode COMPOSES edge (design link).

    This allows the design graph to show which classes implement
    which HLRs.
    """
    try:
        _create_edge(hlr, compound, "COMPOSES")
        return True
    except Exception as exc:
        log.debug(
            "_link_hlr_to_compound: failed for %s → %s: %s",
            getattr(hlr, "name", "?"),
            getattr(compound, "qualified_name", "?"),
            exc,
        )
        return False


def _create_edge(source, target, edge_type: str) -> bool:
    """Create an edge between two saved nodes using raw Cypher MERGE."""
    try:
        query = (
            f"MATCH (s), (t) "
            f"WHERE elementId(s) = $source_id AND elementId(t) = $target_id "
            f"MERGE (s)-[:{edge_type}]->(t)"
        )
        db.cypher_query(
            query,
            {
                "source_id": db.parse_element_id(source.element_id),
                "target_id": db.parse_element_id(target.element_id),
            },
        )
        return True
    except Exception as exc:
        log.warning("Failed to create %s edge: %s", edge_type, exc)
        return False
