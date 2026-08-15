# Synchronization and Round-Trip Fidelity

**Status:** Living intent  
**Established:** 2026-08-15

## Core loop

```text
selected intent and design
          ↓
generation plan and context
          ↓
generated or modified artifacts
          ↓
build, parse, and index
          ↓
identity and relationship reconciliation
          ↓
tests and verification evidence
          ↓
reviewed graph state
```

### `DI-SYNC-001` — Generation is transactional in meaning

Generation shall be treated as a proposed graph-to-repository change followed
by repository-to-graph reconciliation. Rendering files alone is not successful
completion.

### `DI-SYNC-002` — Identity preservation

When a generated entity realizes an existing planned entity, re-indexing should
preserve or deterministically recover that correspondence. Formatting changes
or a new session should not create a second logical artifact unnecessarily.

### `DI-SYNC-003` — Relationship preservation

Round-trip checks should cover ownership, composition, types, dependencies,
requirements, tests, and other intended relationships—not only symbol names.

### `DI-SYNC-004` — Reconciliation categories

Reconciliation should distinguish at least:

- intended and realized;
- intended but missing;
- realized but unexpected;
- matched but structurally changed;
- ambiguous correspondence;
- verification passed, failed, missing, or stale;
- generated output subsequently modified by an engineer.

### `DI-SYNC-005` — Reconciliation evidence persists

The inputs, outputs, tool versions, mappings, differences, and verification
results of a reconciliation should be durable enough to explain the current
synchronization claim later.

### `DI-SYNC-006` — Idempotent repetition

Running an unchanged generation and indexing workflow repeatedly should
converge on the same artifacts and graph identities rather than accumulate
duplicates or produce irrelevant diffs.

### `DI-SYNC-007` — Partial fidelity is visible

Language or parser limitations should produce explicit fidelity gaps. A
successful parse does not by itself establish semantic round-trip fidelity.

### `DI-SYNC-008` — Drift detection is part of delivery

Drift assessment shall be a normal phase of feature delivery after the
as-built implementation is re-indexed. It should not depend on a later audit or
on an engineer noticing that independently maintained artifacts have diverged.

### `DI-SYNC-009` — Drift is classified before resolution

Detected drift should be evaluated against the motivating requirements,
approved design, test plan, and implementation plan. The workflow should
distinguish an implementation defect from an intentional design evolution, an
invalid or incomplete design assumption, and a decision requiring engineer
judgment.

## Evaluation dimensions

Round-trip fidelity should eventually be measured across:

- entity identity;
- containment and ownership;
- signatures and types;
- source location and generated ownership;
- dependency and call relationships;
- requirement and test traceability;
- behavior demonstrated by verification evidence.
