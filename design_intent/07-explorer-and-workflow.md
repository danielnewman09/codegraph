# Explorer and Engineer Workflow

**Status:** Living intent  
**Established:** 2026-08-15

## Explorer role

The explorer is intended to become the engineer's primary comprehension and
navigation surface over the continuously reconciled engineering model. It
should favor actionable component projections over raw graph complexity.

### `DI-EXP-001` — Component-centered navigation

An engineer should be able to select a component and view its purpose, current
design, implementation, dependencies, requirements, tests, decisions, memories,
and synchronization state from one coherent entry point.

### `DI-EXP-002` — Current design documentation

Displayed design documentation should be derived from or reconciled with the
same indexed entities that describe the implementation. The interface should
show freshness and fidelity rather than claiming that generated documentation
is inherently current.

### `DI-EXP-003` — Evidence beside claims

Claims that a component satisfies a requirement or matches its design should be
presented with navigable implementation, tests, reconciliation results, and
other evidence.

### `DI-EXP-004` — Differences and unknowns are prominent

Missing artifacts, drift, stale evidence, ambiguous mappings, unresolved
decisions, and parser fidelity limitations should be visible in the normal
workflow rather than hidden in specialist reports.

### `DI-EXP-005` — Bounded decision context

The explorer should construct a concise context package for a selected task and
allow the engineer to inspect what will be supplied to an LLM before work is
directed.

### `DI-EXP-006` — Next-work guidance

The explorer should help identify what to build next using explicit signals:
unrealized requirements, missing tests, failed or stale evidence,
synchronization gaps, unresolved decisions, and declared priorities.

Plans and tickets may be created from these signals to coordinate a particular
piece of work. They should remain navigable from the durable artifacts they
connect without becoming another repository documentation corpus.

## Intended workflow

1. Navigate to a component, requirement, or finding.
2. Review its bounded intent, design, implementation, tests, and evidence.
3. Inspect differences, uncertainty, and applicable durable memories.
4. Define or approve the intended change and acceptance criteria.
5. Construct and inspect the LLM context and generation plan.
6. Generate or modify code, tests, and deliberate design artifacts.
7. Build, test, parse, and index the changed repository.
8. Reconcile planned and observed graph state.
9. Classify drift as an implementation issue, design iteration, requirement or
   test-plan issue, or an engineer-level decision.
10. Promote durable learning into scoped memory and review the delta and
    evidence before accepting the new state.

### `DI-EXP-007` — Progressive disclosure

The default view should be understandable at a glance, with relationships and
evidence available on demand. The interface should not require an engineer to
retain an exhaustive graph or generated document in working memory.
