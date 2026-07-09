"""Memory lifecycle tools — drift detection and validation.

Tools for:
  - validate_memories(node) — cross-reference design-tagged memories
    against as-built code
  - detect_drift(source) — find memories whose linked code nodes changed
  - confidence_decay(node) — drop confidence when code changed
  - find_orphan_decisions(source) — decisions whose target code was deleted
  - tag_gap_report(source) — summary of unvalidated decisions
"""

from codegraph_memory.lifecycle.validate import validate_memories, tag_gap_report
from codegraph_memory.lifecycle.drift import (
    detect_drift,
    confidence_decay,
    find_orphan_decisions,
)

__all__ = [
    "validate_memories",
    "tag_gap_report",
    "detect_drift",
    "confidence_decay",
    "find_orphan_decisions",
]