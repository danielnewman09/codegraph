# Artifacts, Authority, and Traceability

**Status:** Living intent  
**Established:** 2026-08-15

## Artifact classes

Codegraph coordinates several kinds of engineering information:

- design intent and principles;
- requirements and acceptance criteria;
- architectural designs and decisions;
- implementation symbols and source files;
- tests, test intent, results, and other verification evidence;
- durable memories such as constraints, corrections, and rejected alternatives;
- ephemeral coordination views such as plans and tickets;
- generated projections such as diagrams, summaries, dashboards, and context
  packs.

### `DI-ART-001` — Repository-authored sources

Reviewable, deliberately authored artifacts should live in the repository when
practical. This includes requirements, source code, tests, and durable design
decisions. Their files make authorship, review, and version history visible.

### `DI-ART-002` — Graph-backed correspondence

The datastore shall index canonical artifact identities and the relationships
among them. It acts as a synchronized structural projection, not an opaque
replacement for repository artifacts.

### `DI-ART-003` — Derived artifacts

PlantUML, JSON exports, Markdown views, HTML visualizations, reports, and LLM
context packs may be derived from the indexed model. A derived artifact should
identify its inputs and synchronization point when it could otherwise be
mistaken for an independently maintained authority.

### `DI-ART-004` — Traceability path

For a scoped component, the system should support traversal in both directions
among:

```text
intent → requirement → design → implementation → test → evidence
```

The model may contain many-to-many relationships and intermediate decisions;
the linear form describes the minimum conceptual path, not a rigid hierarchy.

### `DI-ART-005` — Relationship semantics

Traceability edges should communicate meaning such as `MOTIVATES`, `SATISFIES`,
`REALIZES`, `VERIFIES`, `CONSTRAINS`, `SUPERSEDES`, or `CONTRADICTS`. A generic
association should not be used when a more informative relation is known.

### `DI-ART-006` — Independent status

Artifact existence, linkage, synchronization, and verification are distinct
states. For example, an implementation may be linked to a requirement but not
yet verified, or a test may exist but be stale relative to the implementation.

### `DI-ART-007` — Coordination is not authority

Plans and tickets may connect and sequence durable artifacts, but they are not
canonical statements of product intent, design, or system behavior. Durable
knowledge discovered during execution should be promoted to the appropriate
requirement, design, decision, memory, implementation, or test artifact.

## Authority rules

When representations disagree, Codegraph should surface the disagreement and
the provenance of each representation. It should not silently choose the most
recently indexed copy as authoritative. Resolution may require a declared
artifact authority, a reconciliation policy, or an engineer decision.
