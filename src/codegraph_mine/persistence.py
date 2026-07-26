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

from codegraph.backends import get_backend

from codegraph_requirements.models.requirement import HLR, LLR
from codegraph_mine.schemas import MinedRequirements, MinedCompositeHLR, MinedComponents
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
    from codegraph.backends import get_backend

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
    from codegraph.persistence.repository import GraphRepository
    existing_count = len(GraphRepository.composed_children(hlr, LLR))

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
    """Create an edge between two saved nodes using the active backend."""
    from codegraph.backends import get_backend
    try:
        get_backend().connect(source, target, edge_type)
        return True
    except Exception as exc:
        log.warning("Failed to create %s edge: %s", edge_type, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════
# Composite HLR persistence
# ══════════════════════════════════════════════════════════════════════════


def _make_composite_hlr_name(namespace_name: str) -> str:
    """Derive a short name for a composite HLR from a namespace name."""
    # Handle both dotted (Python) and ::-separated (C++) qualified names
    if "::" in namespace_name:
        short = namespace_name.rsplit("::", 1)[-1]
    else:
        short = namespace_name.rsplit(".", 1)[-1]
    return f"Composite Requirements for {short}"


def persist_composite_hlr(
    namespace,
    mined: MinedCompositeHLR,
    *,
    source: str = "codegraph",
    tag: str = "as-built",
) -> MineResult:
    """Persist a composite/technical HLR linked to its child HLRs.

    Creates (or updates) one composite HLR node with the ``"composite"``
    tag, then connects it to each child HLR via ``COMPOSES`` edges.
    Also links the composite HLR to the NamespaceNode via a ``COMPOSES``
    design link.

    Graph output::

        CompositeHLR -[:COMPOSES]-> ChildHLR -[:COMPOSES]-> LLR ...
        CompositeHLR -[:COMPOSES]-> NamespaceNode

    Args:
        namespace: The NamespaceNode that defines the cluster boundary.
        mined: Parsed :class:`MinedCompositeHLR` from the LLM.
        source: Source provenance for new nodes.
        tag: Provenance tag for new nodes (``"as-built"`` by default).

    Returns:
        A :class:`MineResult` with counts.
    """
    namespace_name = getattr(namespace, "qualified_name", "")
    if not namespace_name:
        return MineResult(
            compound_name="(unknown)",
            error="Namespace has no qualified_name",
        )

    try:
        # 1. Create/update the composite HLR node
        hlr_node = _upsert_composite_hlr(
            namespace_name, mined.description, source, tag
        )

        # 2. Link to each child HLR by name
        child_count = 0
        for child_name in mined.child_hlr_names:
            linked = _link_composite_to_child_hlr(
                hlr_node, child_name, tag
            )
            if linked:
                child_count += 1

        # 3. Link composite HLR to the NamespaceNode (design link)
        _create_edge(hlr_node, namespace, "COMPOSES")

        return MineResult(
            compound_name=namespace_name,
            hlr_description=mined.description,
            llr_count=child_count,
            test_count=0,
        )

    except Exception as exc:
        log.exception(
            "persist_composite_hlr failed for %s", namespace_name
        )
        return MineResult(
            compound_name=namespace_name,
            error=str(exc),
        )


def _upsert_composite_hlr(
    namespace_name: str,
    description: str,
    source: str,
    tag: str,
):
    """Create or update a composite HLR node for a namespace.

    Uses MERGE on (name) to avoid creating duplicate composite HLRs
    for the same namespace on re-runs.  Composite HLRs carry the
    ``"composite"`` tag alongside the standard provenance tag.
    """
    from codegraph_requirements.models.requirement import HLR

    name = _make_composite_hlr_name(namespace_name)

    existing = HLR.nodes.get_or_none(name=name, source=source)

    if existing:
        existing.description = description
        existing.tags = list(
            set((existing.tags or []) + [tag, "composite"])
        )
        existing.save()
        return existing

    hlr = HLR(
        name=name,
        description=description,
        tags=[tag, "composite"],
        source=source,
    )
    hlr.save()
    return hlr


def _link_composite_to_child_hlr(
    composite_hlr,
    child_name: str,
    tag: str,
) -> bool:
    """Connect a composite HLR to a child HLR via COMPOSES.

    Looks up the child HLR by name and creates a COMPOSES edge from
    the composite to the child.  Tries exact match first, then falls
    back to prefix match (stripping trailing description text).

    Returns True if the link was created, False if the child HLR
    was not found.
    """
    from codegraph_requirements.models.requirement import HLR

    try:
        # Try exact match first
        child_hlr = HLR.nodes.get_or_none(name=child_name)

        # Fallback: strip trailing description (LLM may append it)
        if child_hlr is None and ': ' in child_name:
            prefix = child_name.split(': ', 1)[0]
            child_hlr = HLR.nodes.get_or_none(name=prefix)
            if child_hlr:
                log.debug(
                    "_link_composite_to_child_hlr: matched by prefix '%s' → '%s'",
                    child_name, prefix,
                )

        if child_hlr is None:
            log.debug(
                "_link_composite_to_child_hlr: HLR not found: %s",
                child_name,
            )
            return False
        _create_edge(composite_hlr, child_hlr, "COMPOSES")
        return True
    except Exception as exc:
        log.warning(
            "_link_composite_to_child_hlr: failed for %s → %s: %s",
            getattr(composite_hlr, "name", "?"),
            child_name,
            exc,
        )
        return False


# ══════════════════════════════════════════════════════════════════════════
# Component mining persistence
# ══════════════════════════════════════════════════════════════════════════


def persist_mined_components(
    mined: MinedComponents,
    *,
    source: str = "codegraph",
    tag: str = "as-built",
) -> MineResult:
    """Persist a set of mined Components linked to their assigned HLRs.

    Creates (or updates) one Component node per mined component, then
    connects each Component to its assigned HLRs via ``COMPOSES`` edges.
    Also links Components to the ProjectMeta singleton and to their
    primary NamespaceNode via ``GROUPS``.

    **Exclusivity guarantee**: each HLR is linked to at most one
    Component.  Duplicate assignments in the LLM output are detected
    pre-persist (first assignment wins, subsequent ones are dropped
    with a warning).  At link time, any existing ``COMPOSES`` edge from
    another Component to the same HLR is removed.  After persisting, a
    verification query confirms no HLR has >1 Component.

    Graph output::

        ProjectMeta -[:COMPOSES]-> Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR ...
        Component -[:GROUPS]-> NamespaceNode

    Args:
        mined: Parsed :class:`MinedComponents` from the LLM.
        source: Source provenance for new nodes.
        tag: Provenance tag for new nodes (``"as-built"`` by default).

    Returns:
        A :class:`MineResult` with aggregate counts and any
        exclusivity warnings in ``warnings``.
    """
    from codegraph_project.models.component import Component
    from codegraph_project.models.project import ProjectMeta
    from codegraph_requirements.models.requirement import HLR

    try:
        project = ProjectMeta.get_singleton()

        # --- Pre-process: deduplicate HLR assignments ---
        warnings: list[str] = []
        deduped_components = _deduplicate_hlr_assignments(mined, warnings=warnings)

        component_count = 0
        hlr_link_count = 0

        for comp_data in deduped_components:
            # 1. Create or update the Component node
            comp_node = _upsert_component(
                comp_data.name,
                comp_data.description,
                comp_data.namespace,
                source,
                tag,
            )
            component_count += 1

            # 2. Link Component to the ProjectMeta
            _create_edge(project, comp_node, "COMPOSES")

            # 3. Link Component to its assigned HLRs (exclusive)
            for hlr_name in comp_data.hlr_names:
                linked = _link_component_to_hlr_exclusive(comp_node, hlr_name)
                if linked:
                    hlr_link_count += 1

            # 4. Link Component to its primary NamespaceNode via GROUPS
            if comp_data.namespace:
                _link_component_to_namespace(comp_node, comp_data.namespace)

        # --- Post-persist verification ---
        violations = _verify_component_hlr_exclusivity()
        if violations:
            for v in violations:
                warnings.append(v)

        return MineResult(
            compound_name="project",
            hlr_description=f"{component_count} Components mined",
            llr_count=component_count,
            test_count=hlr_link_count,
            warnings=warnings,
        )

    except Exception as exc:
        log.exception("persist_mined_components failed")
        return MineResult(
            compound_name="project",
            error=str(exc),
        )


def _upsert_component(
    name: str,
    description: str,
    namespace: str,
    source: str,
    tag: str,
):
    """Create or update a Component node.

    Uses MERGE on (name, source) to avoid duplicate Components on
    re-runs.  Mined Components carry the ``"mined"`` tag alongside the
    standard provenance tag.
    """
    from codegraph_project.models.component import Component

    existing = Component.nodes.get_or_none(name=name, source=source)

    if existing:
        existing.description = description
        existing.namespace = namespace
        existing.tags = list(
            set((existing.tags or []) + [tag, "mined"])
        )
        existing.save()
        return existing

    comp = Component(
        name=name,
        description=description,
        namespace=namespace,
        tags=[tag, "mined"],
        source=source,
    )
    comp.save()
    return comp


def _link_component_to_hlr(component, hlr_name: str) -> bool:
    """Connect a Component to an HLR via COMPOSES (non-exclusive).

    Tries exact name match first, then falls back to prefix match
    (stripping any trailing description after ': ' that the LLM may
    have inadvertently included).

    Returns True if the link was created, False if the HLR was not found.
    """
    from codegraph_requirements.models.requirement import HLR

    try:
        # Try exact match first
        hlr = HLR.nodes.get_or_none(name=hlr_name)

        # Fallback: strip trailing description (LLM sometimes appends it)
        if hlr is None and ': ' in hlr_name:
            prefix = hlr_name.split(': ', 1)[0]
            hlr = HLR.nodes.get_or_none(name=prefix)
            if hlr:
                log.debug(
                    "_link_component_to_hlr: matched by prefix '%s' → '%s'",
                    hlr_name, prefix,
                )

        if hlr is None:
            log.debug(
                "_link_component_to_hlr: HLR not found: %s", hlr_name
            )
            return False
        _create_edge(component, hlr, "COMPOSES")
        return True
    except Exception as exc:
        log.warning(
            "_link_component_to_hlr: failed for %s → %s: %s",
            getattr(component, "name", "?"),
            hlr_name,
            exc,
        )
        return False


def _link_component_to_hlr_exclusive(component, hlr_name: str) -> bool:
    """Connect a Component to an HLR, ensuring 1:1 exclusivity.

    Before creating the COMPOSES edge, removes any existing COMPOSES
    edges from *any* Component to the target HLR.  This guarantees
    that each HLR is assigned to at most one Component at all times.

    Returns True if the link was created, False if the HLR was not found.
    """
    from codegraph_requirements.models.requirement import HLR

    try:
        # Try exact match first
        hlr = HLR.nodes.get_or_none(name=hlr_name)

        # Fallback: strip trailing description (LLM sometimes appends it)
        if hlr is None and ': ' in hlr_name:
            prefix = hlr_name.split(': ', 1)[0]
            hlr = HLR.nodes.get_or_none(name=prefix)
            if hlr:
                log.debug(
                    "_link_component_to_hlr_exclusive: matched by prefix '%s' → '%s'",
                    hlr_name, prefix,
                )

        if hlr is None:
            log.debug(
                "_link_component_to_hlr_exclusive: HLR not found: %s", hlr_name
            )
            return False

        # Remove existing COMPOSES edges from any Component to this HLR
        get_backend().execute_raw(
            """
            MATCH (old:Component)-[r:COMPOSES]->(h:HLR)
            WHERE elementId(h) = $hlr_id
            DELETE r
            """,
            {"hlr_id": db.parse_element_id(hlr.element_id)},
        )

        _create_edge(component, hlr, "COMPOSES")
        return True
    except Exception as exc:
        log.warning(
            "_link_component_to_hlr_exclusive: failed for %s → %s: %s",
            getattr(component, "name", "?"),
            hlr_name,
            exc,
        )
        return False


def _deduplicate_hlr_assignments(
    mined: MinedComponents,
    *,
    warnings: list[str],
) -> list[MinedComponent]:
    """Detect and resolve HLRs assigned to multiple Components.

    If the same HLR name appears in more than one Component's
    ``hlr_names``, only the first assignment is kept.  Subsequent
    occurrences are removed and a warning is appended to *warnings*.

    Returns a new list of :class:`MinedComponent` with deduplicated
    ``hlr_names``.
    """
    seen: dict[str, str] = {}  # hlr_name -> component_name that owns it
    deduped: list[MinedComponent] = []

    for comp in mined.components:
        unique_hlrs: list[str] = []
        for hlr_name in comp.hlr_names:
            if hlr_name in seen:
                warnings.append(
                    f"HLR '{hlr_name}' assigned to multiple Components: "
                    f"'{seen[hlr_name]}' and '{comp.name}'. "
                    f"Keeping assignment to '{seen[hlr_name]}' only."
                )
            else:
                seen[hlr_name] = comp.name
                unique_hlrs.append(hlr_name)
        deduped.append(comp.model_copy(update={"hlr_names": unique_hlrs}))

    return deduped


def _verify_component_hlr_exclusivity() -> list[str]:
    """Verify no HLR is linked to more than one Component via COMPOSES.

    Runs a Cypher query to detect any HLR with >1 incoming COMPOSES
    edge from a Component.  Returns a list of violation messages
    (empty if all clear).
    """
    try:
        results, _ = get_backend().execute_raw(
            """
            MATCH (c:Component)-[:COMPOSES]->(h:HLR)
            WITH h, collect(c.name) AS comps
            WHERE size(comps) > 1
            RETURN h.name AS hlr_name, comps
            """
        )
        violations = []
        for row in results:
            hlr_name = row[0]
            comps = row[1]
            violations.append(
                f"EXCLUSIVITY VIOLATION: HLR '{hlr_name}' is linked to "
                f"{len(comps)} Components: {comps}"
            )
        return violations
    except Exception as exc:
        log.warning("_verify_component_hlr_exclusivity: query failed: %s", exc)
        return [f"Verification query failed: {exc}"]


def _link_component_to_namespace(component, namespace_qn: str) -> bool:
    """Connect a Component to a NamespaceNode via GROUPS.

    Returns True if the link was created, False if the namespace
    was not found.
    """
    from codegraph.models.namespace import NamespaceNode

    try:
        ns = NamespaceNode.nodes.get_or_none(qualified_name=namespace_qn)
        if ns is None:
            log.debug(
                "_link_component_to_namespace: NamespaceNode not found: %s",
                namespace_qn,
            )
            return False
        _create_edge(component, ns, "GROUPS")
        return True
    except Exception as exc:
        log.warning(
            "_link_component_to_namespace: failed for %s → %s: %s",
            getattr(component, "name", "?"),
            namespace_qn,
            exc,
        )
        return False
