# Feature Lifecycle and Drift Detection

**Status:** Living intent  
**Established:** 2026-08-15

## Purpose

Feature delivery in Codegraph is a closed-loop learning process. Requirements,
design, test intent, implementation, and observed as-built structure are
successive, connected representations of the feature. Comparing them is part
of building the feature—not a separate maintenance activity.

## Lifecycle

```text
requirements
    ↓ motivate
design + test plan
    ↓ aggregate into
implementation plan
    ↓ directs
implementation
    ↓ parse and re-index
as-built feature
    ↓ compare with prior intent
drift assessment
    ├─ implementation defect → correct implementation
    ├─ design needs iteration → update design + create scoped memory
    ├─ requirement/test issue → revise the durable artifact
    └─ consequential decision → escalate to engineer
```

### `DI-FTR-001` — Requirements motivate design

Feature work should begin with indexed requirements that explain the desired
outcome and acceptance boundaries. Design entities and decisions should be
traceable to the requirements that motivate them.

### `DI-FTR-002` — Design and test intent develop together

The feature workflow should create a design and a test plan before
implementation planning. The test plan describes how the intended behavior and
important design constraints will be demonstrated, including relevant negative
and failure cases.

### `DI-FTR-003` — Implementation plans aggregate durable intent

An implementation plan is an ephemeral coordination view that gathers the
approved requirements, design, test plan, applicable memories, and current
as-built context into sequenced work. It does not become a new source of truth.

### `DI-FTR-004` — Implementation retains motivation

Implementation work should preserve traceability to the plan inputs so the
result can later be assessed against the particular requirements, design
entities, constraints, and tests it was intended to realize.

### `DI-FTR-005` — Re-index before declaring completion

After implementation, the feature's as-built code and tests shall be parsed and
re-indexed. The workflow should use observed artifacts and relationships—not
only the LLM's account of what it changed—as the basis for reconciliation.

### `DI-FTR-006` — Internal drift assessment

The re-indexed as-built feature shall be compared with its motivating
requirements, approved design, test plan, and implementation plan. Missing,
unexpected, changed, ambiguous, and unverified realizations should be reported
as structured findings.

### `DI-FTR-007` — Drift is not automatically a defect

A difference between intended and as-built state may indicate:

- implementation failed to realize an otherwise valid design;
- the design was incomplete, invalid, or impractical;
- a requirement or test assumption needs clarification or revision;
- implementation uncovered a consequential tradeoff not previously decided;
- indexing or round-trip fidelity is insufficient to establish correspondence.

The workflow should classify the finding before choosing which artifact to
change.

### `DI-FTR-008` — Consequential decisions reach the engineer

When drift exposes a choice that changes behavior, architecture, requirements,
risk, scope, or an established constraint, the decision should be presented to
the engineer with the affected artifacts, evidence, alternatives, and likely
consequences. The LLM should not silently normalize the design to match its
implementation.

### `DI-FTR-009` — Design iteration creates memory

When drift demonstrates that an aspect of the design must be iterated, the
workflow should capture the learned constraint, failed assumption, correction,
or rationale as a memory scoped to the affected design entity. The design and
related artifacts should then be updated deliberately.

### `DI-FTR-010` — Reconcile again after iteration

If drift causes requirements, design, tests, or implementation to change, the
affected portion of the lifecycle should repeat until the accepted artifacts
and current as-built evidence reach an explicit reconciled state.

## Drift review output

A drift review should provide the engineer with:

- the intended and observed entities and relationships;
- the requirements and test intent involved;
- relevant test results and other evidence;
- the proposed classification of each difference;
- memories and prior decisions that constrain resolution;
- the recommended artifact to update;
- decisions that require explicit engineer input.

The review should remain bounded to the feature and its materially affected
neighbors so that the engineer can understand the decision without loading the
entire system into working memory.

