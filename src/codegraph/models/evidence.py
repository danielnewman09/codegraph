"""Execution evidence node model — :ExecutionEvidence label in Neo4j.

Records that a build or a test run *actually executed* and what happened.
A parsed ``TestNode`` proves a test exists; an ``ExecutionEvidenceNode``
proves it passed against a specific build, environment, and revision
(Priority 5, WP5.4: "a test exists" is not "this test passed").

Frozen vocabulary (``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``):

    ExecutionEvidenceNode -[:EVIDENCES]->  TestNode | ClassNode
    test execution evidence -[:DEPENDS_ON]-> build execution evidence

Edges are carried as ``LayerGraph`` references rather than neomodel
relationship managers — the same pure-Python path the WP5.3 memories use —
so evidence joins any slice graph without a backend attachment.

Evidence is *reviewed data*: the capture script
(``scripts/capture_transaction_slice_evidence.py``) is the only supported
author, and ordinary test runs validate the committed records instead of
rebuilding or rewriting timestamps.
"""

from __future__ import annotations

from codegraph.models.descriptors import (
    DateTimeProperty,
    Property,
)
from codegraph.models.tags import CodeGraphNode

#: The frozen evidence categories (WP5.4 "Minimum model").
EVIDENCE_TYPES: tuple[str, ...] = ("build", "test")

#: The frozen outcomes.
EVIDENCE_STATUSES: tuple[str, ...] = ("passed", "failed", "error")


class ExecutionEvidenceNode(CodeGraphNode):
    """One recorded execution of a build or a test binary.

    Attributes:
        qualified_name: Human-readable identifier, unique inside the
            identity scope (indexed).
        kind: Always ``"execution_evidence"``.
        evidence_type: ``"build"`` or ``"test"``.
        status: ``"passed"``, ``"failed"``, or ``"error"``.
        command: The exact command line that was executed.
        exit_code: Process exit code (0 for a successful run).
        executed_at: UTC start time of the execution.
        duration_seconds: Wall-clock duration when the runner reported one.
        environment: Structured toolchain/environment summary
            (platform, compiler, dependency manager and versions).
        revision: VCS revision or content digest of the sources the
            artifact was produced from — what the evidence is *about*.
        output_digest: ``algorithm:hex`` digest of the captured combined
            output, so the reviewed log cannot drift silently.
        log_path: Repository-relative path of the retained full log.
        tags: Provenance tags (e.g. ``"requirements"``, ``"evidence"``).
        source: Name of the project the evidence belongs to.
    """

    # --- Identity ---
    qualified_name = Property(
        str, default="", index=True,
        help_text="Human-readable identifier, unique within the identity "
                  "scope (e.g. 'evidence:cpp-sqlite-release-build').",
    )
    kind = Property(str, default="execution_evidence")

    # --- Identity fields: one evidence record per name in scope ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Outcome ---
    evidence_type = Property(
        str, default="",
        help_text="'build' or 'test' — what was executed.",
    )
    status = Property(
        str, default="",
        help_text="'passed', 'failed', or 'error' — how it ended.",
    )
    command = Property(
        str, default="",
        help_text="Exact command line that was executed.",
    )
    exit_code = Property(
        int, default=-1,
        help_text="Process exit code (0 for a successful run).",
    )

    # --- Temporal ---
    executed_at = DateTimeProperty(
        help_text="UTC start time of the execution.",
    )
    duration_seconds = Property(
        float, default=0.0,
        help_text="Wall-clock duration in seconds when measured.",
    )

    # --- Context the evidence was produced in ---
    environment = Property(
        list, default=list,
        help_text="Structured toolchain/environment summary as "
                  "'key=value' entries (platform, compiler, conan/cmake "
                  "versions, build type).",
    )
    revision = Property(
        str, default="",
        help_text="VCS revision or content digest of the sources the "
                  "artifact was produced from.",
    )
    output_digest = Property(
        str, default="",
        help_text="'algorithm:hex' digest of the captured combined output.",
    )
    log_path = Property(
        str, default="",
        help_text="Repository-relative path of the retained full log.",
    )

    # --- Provenance ---
    tags = Property(list, default=[])

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name",
        "kind",
        "evidence_type",
        "status",
        "command",
        "exit_code",
        "executed_at",
        "duration_seconds",
        "environment",
        "revision",
        "output_digest",
        "log_path",
        "tags",
        "source",
    }
