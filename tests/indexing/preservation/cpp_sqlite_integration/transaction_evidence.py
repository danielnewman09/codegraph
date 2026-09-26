"""WP5.4 — execution evidence for the Transaction slice.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

Execution evidence distinguishes "a test exists" (a parsed ``TestNode``)
from "this test passed against this build".  The records are *data*: the
capture script ``scripts/capture_transaction_slice_evidence.py`` is the only
supported author of
``fixtures/cpp-sqlite/transaction_slice/evidence.toml``
(:func:`load_evidence_definitions` reads it), and ordinary test runs validate
the committed records against the retained logs — they never rebuild, rewrite
timestamps, or access the network (plan step 6).

The evidence joins the slice the way the WP5.3 memories do: materialized as
an ordinary :class:`~codegraph.models.evidence.ExecutionEvidenceNode` entry of
the slice's own ``LayerGraph`` under the slice's canonical identity scope, so
the flat portable document (WP5.2) carries it with no second snapshot format.

Frozen vocabulary (plan "Frozen relationship vocabulary")::

    ExecutionEvidenceNode -[:EVIDENCES]-> TestNode | ClassNode
    test execution evidence -[:DEPENDS_ON]-> build execution evidence
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.evidence import EVIDENCE_STATUSES, ExecutionEvidenceNode

from .transaction_memories import (
    SLICE_KEY_PREFIX,
    SLICE_SCOPE,
    iter_entries,
    node_index,
)
from .transaction_slice import TEST_QNS, TRANSACTION_CLASS_QN

_HERE = Path(__file__).resolve().parent

#: The repository-reviewed evidence input (WP5.4 step 4).
EVIDENCE_INPUT = (
    _HERE.parent / "fixtures" / "cpp-sqlite" / "transaction_slice"
    / "evidence.toml"
)

#: The codegraph repository root — ``log_path`` values are relative to it.
CODEGRAPH_ROOT = _HERE.parents[3]

#: The frozen evidence records, by type (WP5.4 "Minimum model").
FROZEN_EVIDENCE_TYPES: tuple[str, ...] = ("build", "test")

#: The fields the reviewed input must carry for every record.
REQUIRED_FIELDS: tuple[str, ...] = (
    "evidence_type", "qualified_name", "status", "command", "exit_code",
    "executed_at", "duration_seconds", "environment", "revision",
    "output_digest", "log_path", "tags", "source",
)

#: The class the build evidence must certify (frozen by the plan's
#: ``EVIDENCES -> ClassNode`` for the tested binary).
BUILD_EVIDENCES_CLASS = TRANSACTION_CLASS_QN

#: The five real tests the filtered run certified.
TEST_EVIDENCES_TESTS: tuple[str, ...] = tuple(
    TEST_QNS[name] for name in (
        "TransactionCommit",
        "TransactionRollback",
        "TransactionAutoRollbackOnDestruction",
        "NestedTransactionWithSavepoints",
        "NestedTransactionRollbackInner",
    )
)

#: The gtest filter the test record's command must carry — exactly the five
#: frozen tests, so "covering all five tests" cannot quietly widen.
FROZEN_GTEST_FILTER = ":".join(
    f"DatabaseTest.{name}" for name in (
        "TransactionCommit",
        "TransactionRollback",
        "TransactionAutoRollbackOnDestruction",
        "NestedTransactionWithSavepoints",
        "NestedTransactionRollbackInner",
    )
)


class EvidenceFixtureError(AssertionError):
    """The reviewed evidence input or its resolution is inconsistent."""


@dataclass(frozen=True)
class EvidenceDefinition:
    """One reviewed evidence record, exactly as authored (no derived fields)."""

    type: str  # evidence_type: "build" | "test"
    qualified_name: str
    status: str  # "passed" | "failed" | "error" — as authored
    command: str
    exit_code: int
    executed_at: datetime
    duration_seconds: float
    environment: tuple[str, ...]
    revision: str
    output_digest: str
    log_path: str
    tags: tuple[str, ...]
    source: str
    evidences: tuple[str, ...]  # EVIDENCES targets (class qname / test qnames)
    depends_on: str | None  # DEPENDS_ON target (build evidence qname)


# ---------------------------------------------------------------------------
# Load — reviewed data only
# ---------------------------------------------------------------------------


def load_evidence_definitions(
    path: Path = EVIDENCE_INPUT,
) -> tuple[EvidenceDefinition, ...]:
    """Read the captured evidence records in file order.

    Raises:
        EvidenceFixtureError: if the input is missing, malformed, lacks a
            required field, repeats an identity, or carries an evidence type
            outside the frozen ``build``/``test`` pair.
    """
    if not path.is_file():
        raise EvidenceFixtureError(f"missing evidence input: {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("evidence")
    if not isinstance(entries, list) or not entries:
        raise EvidenceFixtureError(f"{path}: expected a non-empty [[evidence]] list")

    definitions: list[EvidenceDefinition] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{path.name}[{index}]"
        missing = [key for key in REQUIRED_FIELDS if key not in entry]
        if missing:
            raise EvidenceFixtureError(f"{where}: missing {', '.join(missing)}")
        evidence_type = entry["evidence_type"]
        if evidence_type not in FROZEN_EVIDENCE_TYPES:
            raise EvidenceFixtureError(
                f"{where}: unknown type {evidence_type!r}; expected one of "
                f"{list(FROZEN_EVIDENCE_TYPES)}"
            )
        qualified_name = entry["qualified_name"]
        if qualified_name in seen:
            raise EvidenceFixtureError(f"{where}: duplicate {qualified_name!r}")
        seen.add(qualified_name)
        try:
            executed_at = datetime.fromisoformat(entry["executed_at"])
        except ValueError as exc:
            raise EvidenceFixtureError(
                f"{where}: executed_at is not ISO-8601: {entry['executed_at']!r}"
            ) from exc
        if executed_at.tzinfo is None:
            raise EvidenceFixtureError(f"{where}: executed_at has no timezone")
        if not entry["revision"].strip():
            raise EvidenceFixtureError(f"{where}: empty revision")
        if not entry["output_digest"].startswith("sha256:"):
            raise EvidenceFixtureError(f"{where}: output_digest must be sha256:")
        status = entry["status"]
        if status not in EVIDENCE_STATUSES:
            raise EvidenceFixtureError(
                f"{where}: unknown status {status!r}; expected one of "
                f"{list(EVIDENCE_STATUSES)}"
            )
        # An outcome must agree with the exit code it reports — a "passed"
        # record with a non-zero exit is a fixture defect, never a rounding.
        if (status == "passed") != (int(entry["exit_code"]) == 0):
            raise EvidenceFixtureError(
                f"{where}: status {status!r} contradicts exit_code "
                f"{entry['exit_code']}"
            )
        definitions.append(EvidenceDefinition(
            type=evidence_type,
            qualified_name=qualified_name,
            status=status,
            command=entry["command"],
            exit_code=int(entry["exit_code"]),
            executed_at=executed_at,
            duration_seconds=float(entry["duration_seconds"]),
            environment=tuple(entry["environment"]),
            revision=entry["revision"],
            output_digest=entry["output_digest"],
            log_path=entry["log_path"],
            tags=tuple(entry["tags"]),
            source=entry["source"],
            evidences=tuple(entry.get("evidences", ())),
            depends_on=entry.get("depends_on"),
        ))

    types = tuple(definition.type for definition in definitions)
    if sorted(types) != sorted(FROZEN_EVIDENCE_TYPES):
        raise EvidenceFixtureError(
            f"{path.name}: expected the frozen evidence types "
            f"{sorted(FROZEN_EVIDENCE_TYPES)}, got {sorted(types)}"
        )
    return tuple(definitions)


def read_log(definition: EvidenceDefinition) -> bytes:
    """The retained log bytes for *definition* (repo-relative path)."""
    path = CODEGRAPH_ROOT / definition.log_path
    if not path.is_file():
        raise EvidenceFixtureError(f"retained log missing: {path}")
    return path.read_bytes()


def log_digest(definition: EvidenceDefinition) -> str:
    """Recompute ``sha256:…`` over the retained log and return it."""
    return "sha256:" + hashlib.sha256(read_log(definition)).hexdigest()


# ---------------------------------------------------------------------------
# Materialize — framework identity, graph endpoints
# ---------------------------------------------------------------------------


def _materialize_node(definition: EvidenceDefinition) -> ExecutionEvidenceNode:
    """Build the evidence node and give it its framework-computed key."""
    node = ExecutionEvidenceNode(
        qualified_name=definition.qualified_name,
        evidence_type=definition.type,
        status=definition.status,
        command=definition.command,
        exit_code=definition.exit_code,
        executed_at=definition.executed_at,
        duration_seconds=definition.duration_seconds,
        environment=list(definition.environment),
        revision=definition.revision,
        output_digest=definition.output_digest,
        log_path=definition.log_path,
        tags=list(definition.tags),
        source=definition.source,
    )
    node.canonical_key = node.resolve_canonical_key(scope=SLICE_SCOPE)
    recomputed = node.resolve_canonical_key(scope=SLICE_SCOPE)
    if recomputed != node.canonical_key:
        raise EvidenceFixtureError(
            f"{definition.qualified_name}: canonical key "
            f"{node.canonical_key!r} does not recompute from the node's own "
            f"fields ({recomputed!r})"
        )
    if not node.canonical_key.startswith(SLICE_KEY_PREFIX):
        raise EvidenceFixtureError(
            f"{definition.qualified_name}: key {node.canonical_key!r} is "
            f"outside the slice scope {SLICE_KEY_PREFIX!r}"
        )
    return node


def materialize_evidence(
    definitions: Sequence[EvidenceDefinition],
    graph: LayerGraph,
) -> tuple[dict[str, CompositeEntry], tuple[tuple[str, str, str], ...]]:
    """Materialize *definitions* against the code/test nodes of *graph*.

    Returns:
        ``(entries, evidence_edges)``: ``entries`` maps each canonical key to
        its :class:`CompositeEntry` (targets already attached) and
        ``evidence_edges`` lists ``(relation_type, source_key, target_key)``
        for every ``EVIDENCES`` and ``DEPENDS_ON`` edge.

    Raises:
        EvidenceFixtureError: if an ``EVIDENCES`` target is not in the slice
            graph, or a ``DEPENDS_ON`` target is not one of the reviewed
            evidence records — an authored typo must fail loudly rather than
            look like a graph with fewer edges.
    """
    by_qname = node_index(graph)

    entries: dict[str, CompositeEntry] = {}
    keys_by_qname: dict[str, str] = {}
    pending: list[tuple[CompositeEntry, str]] = []
    evidence_edges: list[tuple[str, str, str]] = []

    for definition in definitions:
        node = _materialize_node(definition)
        entry = CompositeEntry(node=node)
        for target_qname in definition.evidences:
            target = by_qname.get(target_qname)
            if target is None:
                raise EvidenceFixtureError(
                    f"{definition.qualified_name}: EVIDENCES target "
                    f"{target_qname!r} is not in the slice graph"
                )
            entry.references.append(
                ("EVIDENCES", target.node.canonical_key,
                 type(target.node).__name__)
            )
            evidence_edges.append(
                ("EVIDENCES", node.canonical_key, target.node.canonical_key)
            )
        entries[node.canonical_key] = entry
        keys_by_qname[definition.qualified_name] = node.canonical_key
        if definition.depends_on is not None:
            pending.append((entry, definition.depends_on))

    for entry, target_qname in pending:
        target_key = keys_by_qname.get(target_qname)
        if target_key is None:
            raise EvidenceFixtureError(
                f"{entry.node.qualified_name}: DEPENDS_ON target "
                f"{target_qname!r} is not one of the reviewed evidence records"
            )
        entry.references.append(
            ("DEPENDS_ON", target_key, type(entries[target_key].node).__name__)
        )
        evidence_edges.append(
            ("DEPENDS_ON", entry.node.canonical_key, target_key)
        )

    return entries, tuple(evidence_edges)


def slice_graph_with_evidence(
    graph: LayerGraph,
    definitions: Sequence[EvidenceDefinition],
) -> tuple[LayerGraph, tuple[tuple[str, str, str], ...]]:
    """The slice graph plus the materialized evidence entries.

    Returns ``(combined, evidence_edges)`` — ``materialize_evidence``'s edge
    report is kept because WP5.6's report needs it, while the combined graph
    uses the same non-mutating merge path as the memories: the evidence
    becomes an ordinary entry of a graph with the same tags and shape, so the
    flat document and its fixpoint guarantees apply unchanged.
    """
    entries, evidence_edges = materialize_evidence(definitions, graph)
    combined = LayerGraph(
        tags=graph.tags,
        entries=dict(graph.entries),
        known_keys=graph.known_keys,
    )
    combined.merge(LayerGraph(tags=graph.tags, entries=entries))
    return combined, evidence_edges


def iter_evidence_nodes(graph: LayerGraph) -> Iterator[ExecutionEvidenceNode]:
    for entry in iter_entries(graph):
        if isinstance(entry.node, ExecutionEvidenceNode):
            yield entry.node
