"""Round-trip verification — export → parse → uid-diff (D7, two-tier).

Tier 1 (Phase 1) — compound-level identity subset
    ``design_uids ⊆ as_built_uids`` for qname-only identity
    (classes/structs/enums/unions/interfaces/concepts + namespaces).
    Compounds have no argsstring in their identity, so this is exact.

Tier 2 (Phase 2) — exact method uids
    Requires argsstring normalization (``canonical_argsstring``) before
    hashing; report drift, don't assert.

The ``verify`` CLI subcommand (``codegraph-codegen verify``) runs the
loop: codegen a design graph → write tree → doxygen-index parse → load
as-built → compare.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerifyReport:
    """Result of a round-trip uid diff.

    Attributes:
        tier: ``1`` or ``2``.
        missing_compounds: Design compound uids absent from as-built
            (Tier-1 drift — asserted empty in the round-trip test).
        drift_methods: Method-level uids that differ (Tier-2 drift,
            reported, not asserted).
        marker_checked: Count of provenance-marker cross-checks (R7).
    """

    tier: int = 1
    missing_compounds: list[str] = field(default_factory=list)
    drift_methods: list[str] = field(default_factory=list)
    marker_checked: int = 0


def verify(design_graph, as_built_graph, tier: int = 1) -> VerifyReport:
    """Diff *design_graph* against *as_built_graph* by uid.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError("verify: Phase 1 render slice")


__all__ = ["VerifyReport", "verify"]
