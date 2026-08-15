# Plans, Tickets, and Work Coordination

**Status:** Living intent  
**Established:** 2026-08-15

## Role

In Codegraph, plans and tickets are ephemeral coordination objects. They gather,
connect, sequence, and scope durable engineering artifacts for a particular
piece of work. They help an engineer and an LLM agree on what to do now, but do
not become another permanent documentation authority.

A plan or ticket may connect:

- applicable intent and requirements;
- design entities and decisions;
- relevant memories and constraints;
- implementation components and symbols;
- tests and acceptance evidence;
- synchronization findings, risks, and unresolved questions.

### `DI-WRK-001` — Ephemeral by design

Plans and tickets shall exist for the lifetime of active work and may be closed,
archived, compacted, or discarded afterward. Their content should not need to
be checked into Git to preserve the engineering truth of the codebase.

### `DI-WRK-002` — Durable artifacts remain authoritative

A plan or ticket references durable artifacts; it does not replace them. If a
plan introduces a lasting requirement, constraint, design decision, correction,
or test intent, that information should be written to the corresponding durable
artifact or structured memory.

### `DI-WRK-003` — Connection and projection

A plan or ticket should primarily formalize a bounded projection of existing
graph knowledge plus proposed work. Where practical, it should reference stable
artifact identities rather than duplicate their full contents.

### `DI-WRK-004` — Reconstructable context

The useful context of a plan should be reconstructable from its target,
referenced artifact identities, current graph state, and explicit work-specific
decisions. A stale prose snapshot should not become the only record of why work
was undertaken.

### `DI-WRK-005` — Work-specific state may remain transient

Ordering, assignment, temporary checklists, intermediate notes, retries, and
session-level execution details may remain transient unless they reveal durable
engineering knowledge or are needed as verification provenance.

### `DI-WRK-006` — Promotion at the boundary

Before a plan or ticket is closed, the workflow should identify information
that deserves promotion into a durable artifact. Closure should not discard a
new architectural decision, user correction, unresolved risk, requirement
change, or verification finding merely because it originated in ephemeral work.

### `DI-WRK-007` — Completion through reconciliation

A plan or ticket is not complete only because its checklist is exhausted. Its
result should be indexed and reconciled, its verification evidence recorded,
and its durable outputs connected to the artifacts that motivated the work.

### `DI-WRK-008` — Datastore, not repository corpus

Plans and tickets may be represented in the operational datastore so they can
be queried, updated, and displayed in the explorer. They should not normally be
committed as plan or ticket files in the source repository.

## Lifecycle

```text
need or finding
      ↓
ephemeral ticket
      ↓
bounded plan and linked context
      ↓
execution, indexing, and verification
      ↓
promote durable knowledge
      ↓
close or compact ephemeral coordination state
```

The retained engineering record is the updated set of requirements, designs,
decisions, memories, implementation, tests, relationships, and evidence—not
the ticket narrative itself.

