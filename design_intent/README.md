# Codegraph Design Intent

**Status:** Living intent  
**Established:** 2026-08-15

This folder records the durable product and architectural intent of Codegraph.
It explains why the system exists, what guarantees it should provide, and how
its major artifacts should relate. It is deliberately separate from feature
requirements and implementation designs:

- **Design intent** defines enduring outcomes, principles, and invariants.
- **Requirements** define specific, verifiable behavior.
- **Designs** describe proposed or implemented technical solutions.
- **The indexed graph** records the identities and relationships that connect
  intent, requirements, designs, implementation, tests, and evidence.

These documents are authoritative for direction, but they are not claims that
every described capability is already implemented. Requirements and tests must
make those claims concrete.

## North star

Codegraph is a continuously reconciled engineering workspace in which an
informed engineer can safely direct an LLM over the lifetime of a codebase.
Every important engineering artifact has durable identity, explicit
relationships, and observable synchronization state.

The system should help prevent:

1. unnecessary regeneration of artifacts across sessions;
2. silent drift among requirements, design, implementation, tests, and intent;
3. growth of code and documentation beyond what an engineer can reasonably
   understand and retain.

## Documents

1. [Vision and outcomes](01-vision-and-outcomes.md)
2. [Engineering principles](02-engineering-principles.md)
3. [Artifacts, authority, and traceability](03-artifacts-and-traceability.md)
4. [Synchronization and round-trip fidelity](04-synchronization-and-round-trip.md)
5. [LLM context, memory, and generation](05-context-memory-and-generation.md)
6. [Requirements and verification](06-requirements-and-verification.md)
7. [Explorer and engineer workflow](07-explorer-and-workflow.md)
8. [Plans, tickets, and work coordination](08-plans-tickets-and-coordination.md)
9. [Feature lifecycle and drift detection](09-feature-lifecycle-and-drift.md)
10. [Integrated indexing subsystem](11-integrated-indexing-subsystem.md)
11. [Transparent canonical identity](12-transparent-canonical-identity.md)

## Current-state assessments

- [2026-08-15 gap assessment and cpp-sqlite validation path](10-current-state-gap-assessment.md)

## Statement identifiers

Normative intent statements use stable identifiers such as `DI-SYNC-001`.
Identifiers should not be reused when a statement is removed. Requirements,
design documents, graph nodes, and tests may cite these identifiers to make
their motivation explicit.

## Maintenance

Change these documents when product intent changes, not merely when an
implementation changes. Material changes should identify affected
requirements, designs, and verification evidence. Generated summaries may be
derived from this corpus, but should not silently replace it.
