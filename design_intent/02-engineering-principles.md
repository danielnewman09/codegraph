# Engineering Principles

**Status:** Living intent  
**Established:** 2026-08-15

### `DI-PRN-001` — Identity before text

Artifacts and symbols should have durable identities independent of their
rendered format. Textual similarity may assist reconciliation, but should not
replace explicit identity where deterministic identity is possible.

Canonical identities should be transparent and inspectable. A deterministic
hash of an identity tuple does not provide stronger semantics than the tuple
itself and should not be the default representation when a canonical string key
can be stored directly.

### `DI-PRN-002` — Relationships are first-class

The value of an artifact includes how it satisfies, realizes, verifies,
depends on, supersedes, or conflicts with other artifacts. These relationships
should be queryable rather than buried only in prose.

### `DI-PRN-003` — Provenance is preserved

The system should distinguish intended design, observed implementation,
dependencies, generated output, human-authored material, and verification
evidence. Merging views must not erase their origins.

### `DI-PRN-004` — Differences are evidence

Design/as-built differences, failed tests, unmatched symbols, and stale
relationships are useful findings. The system should report and retain them
rather than silently normalizing them away.

### `DI-PRN-005` — Derived views remain reproducible

Diagrams, dashboards, summaries, generation contexts, and coverage reports
should be reproducible from canonical artifacts and indexed relationships.

### `DI-PRN-006` — Context is selected, not accumulated

LLM and human context should be assembled according to the target component,
task, and relationship graph. More context is not automatically better.

### `DI-PRN-007` — Automation closes its own loop

An automated change should emit enough provenance and verification information
for the result to be re-indexed, compared with its inputs, and reviewed.

### `DI-PRN-008` — Uncertainty is explicit

Missing relationships, ambiguous matches, inferred intent, and unverified
claims should be represented as such. The system should not manufacture
certainty to complete a workflow.

### `DI-PRN-009` — Human-scale projections

The system should favor focused, navigable projections over exhaustive output.
Every generated artifact should earn its maintenance and comprehension cost.

### `DI-PRN-010` — Backend independence

Core identities, artifact semantics, and traceability behavior should not
depend on a particular datastore. Storage backends may optimize traversal and
querying without becoming the definition of the engineering model.
