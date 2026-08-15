# Requirements and Verification

**Status:** Living intent  
**Established:** 2026-08-15

## Canonical requirements

### `DI-REQ-001` — Requirements are repository artifacts

The canonical human-reviewable form of requirements should live in a dedicated
requirements folder in the codebase. Requirements should be versioned, indexed
as part of normal codebase indexing, and addressable by durable identity.

### `DI-REQ-002` — Structured without losing readability

Requirement documents should remain useful to engineers as Markdown while
providing enough consistent structure for identities, relationships, status,
and acceptance criteria to be indexed reliably.

### `DI-REQ-003` — Requirements enter normal indexing

Requirement indexing should be part of the same repeatable workflow that
indexes code and tests. A requirement should not depend on a separate manual
database-entry process to become visible to the workspace.

### `DI-REQ-004` — Requirements connect to realization

Requirements should map to the components, design entities, implementation
symbols, tests, and evidence that claim to satisfy them. Missing links are
actionable findings rather than implicitly acceptable gaps.

## Verification

### `DI-VER-001` — Tests carry intent

Tests should record what behavior or constraint they verify, not only which
source symbols they execute. That intent should be traceable to requirements
and design decisions where applicable.

### `DI-VER-002` — Test existence is not test evidence

The model should distinguish a mapped test from a test execution result. Result
status, environment, relevant artifact version, and time are necessary to make
a meaningful verification claim.

### `DI-VER-003` — Staleness is observable

Verification evidence should become stale when relevant requirements, design,
implementation, test logic, or generation inputs change beyond the evidence's
known scope.

### `DI-VER-004` — Coverage is semantic

Coverage should include requirement and design coverage, not only executed
source lines. A component may have high line coverage while important intent
remains unverified.

### `DI-VER-005` — Verification informs next work

Missing, failed, ambiguous, and stale verification should be presented as
candidate work alongside unimplemented requirements and synchronization gaps.

